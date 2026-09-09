"""Load/save settings to disk (config-file split, atomic write, legacy
migration), autosave scheduling, factory reset, and settings-backup restore.

เดิมไฟล์นี้ยาว 936 บรรทัด รวม 3 ความรับผิดชอบที่ไม่เกี่ยวกันไว้ในไฟล์เดียว
(save/load settings, diagnostics, และ dialog helpers ที่ใช้ทั้งแอป) — แยกออก
เป็น 3 ไฟล์แล้ว: ไฟล์นี้เหลือแค่ save/load/autosave/reset/restore-backup
(ยังอยู่ที่นี่เพราะใช้ตัวช่วย private ระดับโมดูลของไฟล์นี้โดยตรง เช่น
_split_config_data/_atomic_write_json/_CONFIG_FILE_KEYS) ดู
app_settings_diagnostics.py (preflight check/system health/copy diagnostics)
และ app_dialogs.py (alert/confirm/toast ที่ใช้ร่วมกันทั้งแอป) สำหรับอีก 2
ไฟล์ที่เหลือจากการแยกครั้งนี้ — ไม่มีการเปลี่ยน logic ใดๆ เลย แค่ย้ายโค้ดออก
ไปไฟล์อื่น (ยืนยันด้วย diff ว่าตรงกับต้นฉบับ 100%)"""

import logging

from ..core.constants import FG, MAX_CONCURRENCY, UNIT_MAP
from ..core.deps import datetime, json, os, re, shutil
from ..core.rows import AccountRow
from ..core.paths import CONFIG_ACCOUNT_FILE, CONFIG_AUTOMATION_FILE, CONFIG_SYSTEM_FILE, CONFIG_UI_FILE, CONFIG_WEBHOOK_FILE, SAVE_FILE, SETTINGS_BACKUP_DIR, set_startup_enabled
from ..core.security import decrypt_pwd, encrypt_pwd
from .app_logging import DEFAULT_ID_PALETTE, DEFAULT_LOG_COLORS, normalize_hex_color

_logger = logging.getLogger(__name__)


# Legacy keys จากฟีเจอร์ที่ถูกลบไปแล้ว (batch login / test mode) — ไม่มีโค้ดไหน
# Config split (Priority 3): key ไหนอยู่ไฟล์ไหน — key ที่ไม่อยู่ในแมปนี้เลย
# (ไม่ควรมี แต่กันเผื่อ schema เปลี่ยนในอนาคตแล้วลืมแก้แมป) จะตกไปอยู่
# automation.json เป็นค่า default ที่ปลอดภัยที่สุด (ไม่ใช่ไฟล์ที่มีรหัสผ่าน)
_CONFIG_FILE_KEYS = {
    CONFIG_UI_FILE: {
        "geometry",
        "log_colors",
        "log_id_palette",
        "color_by_category",
    },
    CONFIG_ACCOUNT_FILE: {
        "accounts",
        "keywords",
        "autoitem_accounts",
        "inventory_accounts",
        "completed_pairs",
        "recent_keyword_files",
        "recent_account_files",
        "recent_autoitem_files",
        "recent_inventory_files",
        "last_loaded_keyword_file",
        "last_loaded_account_file",
        "last_loaded_autoitem_file",
        "last_loaded_inventory_file",
    },
    CONFIG_WEBHOOK_FILE: {
        "discord_webhooks",
        "discord_webhook",
        "discord_quick_webhooks",
        "discord_avatar_url",
        "discord_quick_avatar_url",
        "discord_bot_name",
        "autoitem_avatar_url",
        "autoitem_bot_name",
        "autoitem_webhooks",
    },
    CONFIG_SYSTEM_FILE: {"start_with_windows"},
    # ที่เหลือทั้งหมด (version, auto_apply_delay, max_concurrent, notify,
    # resume, auto_daily_key, autoitem_enabled) → automation.json
}


def _config_file_for_key(key):
    for path, keys in _CONFIG_FILE_KEYS.items():
        if key in keys:
            return path
    return CONFIG_AUTOMATION_FILE


def _split_config_data(data):
    """แบ่ง dict settings ก้อนเดียว (schema เดิมทุกประการ) ออกเป็น dict ย่อย
    ตามไฟล์ปลายทาง — ไม่แตะ/ตีความค่าใดๆ เลย แค่จัดกลุ่ม key"""
    buckets = {path: {} for path in _CONFIG_FILE_KEYS}
    buckets[CONFIG_AUTOMATION_FILE] = {}
    for key, value in data.items():
        buckets[_config_file_for_key(key)][key] = value
    return buckets


def _atomic_write_json(path, data, backup=False):
    """เขียน JSON แบบ atomic (tmp file + fsync + os.replace) เหมือน logic เดิม
    ของ _save_settings ทุกประการ ใช้ร่วมกันได้ทั้ง 5 ไฟล์ config ย่อย
    backup=True (ใช้กับ account.json ที่มีรหัสผ่านเข้ารหัสอยู่) จะเก็บสำเนา
    ย้อนหลังไว้ใน SETTINGS_BACKUP_DIR เหมือนพฤติกรรมเดิมของไฟล์ settings เดียว"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_file = path + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if backup and os.path.exists(path):
        try:
            os.makedirs(SETTINGS_BACKUP_DIR, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            fname = os.path.splitext(os.path.basename(path))[0]
            backup_path = os.path.join(
                SETTINGS_BACKUP_DIR, f"{fname}_{stamp}.json"
            )
            shutil.copy2(path, backup_path)
            backups = sorted(
                (
                    os.path.join(SETTINGS_BACKUP_DIR, n)
                    for n in os.listdir(SETTINGS_BACKUP_DIR)
                    if n.startswith(f"{fname}_") and n.endswith(".json")
                ),
                key=os.path.getmtime,
                reverse=True,
            )
            for stale in backups[14:]:
                try:
                    os.remove(stale)
                except OSError:
                    pass
        except Exception as _e:
            _logger.debug("ignored error backing up %s: %s", path, _e)
    os.replace(temp_file, path)


def _migrate_legacy_single_file_config():
    """Migration ครั้งเดียว: ถ้ามีไฟล์ settings เก่าไฟล์เดียว (sfkeyword_settings.json)
    อยู่ แต่ยังไม่มีไฟล์ config/ ย่อยเลยสักไฟล์ → แปลงเป็นไฟล์ย่อยให้อัตโนมัติ
    โดย**ไม่ลบไฟล์เก่าทิ้ง** (เปลี่ยนชื่อเป็น .migrated_backup ไว้เป็นเซฟตี้เน็ต
    เผื่อ migration พลาด) ถ้า config/ มีไฟล์ย่อยอยู่แล้วแม้แค่ไฟล์เดียว จะถือว่า
    migrate ไปแล้ว ข้ามไปเลย (idempotent ปลอดภัยเรียกซ้ำได้)"""
    try:
        any_new_file_exists = any(
            os.path.exists(p) for p in _CONFIG_FILE_KEYS
        ) or os.path.exists(CONFIG_AUTOMATION_FILE)
        if any_new_file_exists or not os.path.exists(SAVE_FILE):
            return
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            legacy_data = json.load(f)
        buckets = _split_config_data(legacy_data)
        for path, bucket_data in buckets.items():
            _atomic_write_json(path, bucket_data, backup=(path == CONFIG_ACCOUNT_FILE))
        os.replace(SAVE_FILE, SAVE_FILE + ".migrated_backup")
        _logger.info(
            "Migrated legacy single-file config to config/ split files "
            "(old file kept as sfkeyword_settings.json.migrated_backup)"
        )
    except Exception:
        # Migration พลาด: ห้ามลบ/แก้ไฟล์เก่าเด็ดขาด ปล่อยให้ระบบเก่ายังอยู่ครบ
        # แล้ว _merge_config_files() ด้านล่างจะ fallback ไปอ่านไฟล์เก่าแทน
        _logger.exception("Config migration to split files failed")


def _merge_config_files():
    """โหลดไฟล์ config ย่อยทั้งหมดที่มีอยู่ แล้วรวมกลับเป็น dict เดียว (schema
    เดิมทุกประการ) ให้ฟังก์ชัน _load_settings() ใช้ต่อได้โดยไม่ต้องแก้ logic
    การตีความค่าแต่ละ key เลยแม้แต่บรรทัดเดียว — ถ้าไม่มีไฟล์ย่อยเลย (migration
    ยังไม่เคยเกิด/พลาด) จะ fallback ไปอ่านไฟล์เก่าไฟล์เดียวแทนโดยตรง"""
    all_paths = list(_CONFIG_FILE_KEYS.keys()) + [CONFIG_AUTOMATION_FILE]
    if not any(os.path.exists(p) for p in all_paths):
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    merged = {}
    for path in all_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                merged.update(json.load(f))
        except Exception as _e:
            _logger.warning("ข้าม config file ที่อ่านไม่ได้ %s: %s", path, _e)
    return merged


def _sanitize_delay_config(raw):
    """กรองค่าที่อ่านจาก config สำหรับช่อง 'หน่วงระหว่างล็อกอิน (วินาที)'

    config ยุคเก่า (Selenium) เก็บค่า Chrome version ไว้ใน key 'version'
    เช่น "126.0.6478.127" — ค่าพวกนี้ float() ผ่านแต่ไม่ใช่หน่วงล็อกอินที่สมเหตุผล
    กฎ: ต้องเป็นตัวเลข (ทศนิยมได้) อยู่ในช่วง 0.1–120 แล้วคืนเป็น float
    (ขั้นต่ำ 0.1 วิ — ผู้ใช้ต้องการให้ต่ำสุดได้จริง)
    ถ้าไม่เข้าเงื่อนไขคืน None (ให้ caller ใช้ค่าเริ่มต้น)
    """
    try:
        raw = str(raw).strip()
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val < 0.1 or val > 120.0:
        return None
    return val


class AppSettingsMixin:
    @staticmethod
    def _bool_setting(var):
        """อ่าน BooleanVar ตั้งค่าแบบปลอดภัย — คืน False ถ้ายังไม่ถูกสร้าง
        (ใช้ใน _save_settings กัน getattr 2 รอบซ้ำซ้อน)"""
        if var is None:
            return False
        try:
            return bool(var.get())
        except Exception:
            return False

    def _save_settings(self):
        try:
            if self.container is self.root:
                self.root.update_idletasks()
            geo = self.root.geometry() if self.container is self.root else ""
            try:
                # ช่อง "พร้อมกัน" อนุญาตให้เว้นว่างได้ตอนพิมพ์ (validate รับ ""
                # กลางคัน) — ถ้า autosave มาถูกจังหวะตอนกำลังลบเลข จะได้ไม่ crash
                concurrency = max(1, min(MAX_CONCURRENCY, int(self._concurrency_var.get() or "5")))
            except Exception:
                concurrency = 5
            try:
                # 'พร้อมกัน' ของแท็บรับไอเทมฟรี — แยกจากแดชบอร์ด เก็บ key แยก
                # (default 8 เร็วกว่าเดิมทันที ผู้ใช้ปรับเองได้ 1–200)
                autoitem_concurrency = max(
                    1, min(MAX_CONCURRENCY, int(self._autoitem_concurrency_var.get() or "8"))
                )
            except Exception:
                autoitem_concurrency = 8
            try:
                # 'พร้อมกัน' ของแท็บฝาก/เบิก — แยกเป็น key ของตัวเอง (default 8)
                inventory_concurrency = max(
                    1, min(MAX_CONCURRENCY, int(self._inv_concurrency_var.get() or "8"))
                )
            except Exception:
                inventory_concurrency = 8
            accounts = []
            for r in self._rows:
                d = r.get_data()
                if d:
                    u, p, t, rk, un, un2 = d
                    accounts.append((u, encrypt_pwd(p), t, rk, un, un2))
            keywords = [r.get_data() for r in self._keyword_rows if r.get_data()]
            data = {
                "version": self.version_entry.get().strip(),
                "auto_apply_delay": self._auto_apply_delay_var.get(),
                "notify": self.notify_var.get(),
                "resume": self._resume_var.get(),
                "start_with_windows": self._start_with_windows_var.get(),
                "discord_webhooks": [
                    {
                        "url": encrypt_pwd(r.get_data()),
                        "enabled": r.is_enabled(),
                        "name": r.get_name(),
                    }
                    for r in self._webhook_rows
                    if r.get_data()
                ],
                "discord_avatar_url": self._get_discord_avatar_url(),
                "autoitem_avatar_url": self._get_autoitem_discord_avatar_url(),
                "discord_bot_name": self._get_discord_bot_name(),
                "autoitem_bot_name": self._get_autoitem_discord_bot_name(),
                "auto_daily_key": self._auto_daily_key_var.get(),
                "concurrency": concurrency,
                "autoitem_concurrency": autoitem_concurrency,
                "inventory_concurrency": inventory_concurrency,
                "inv_auto_close_sessions": self._bool_setting(
                    getattr(self, "_inv_auto_close_var", None)
                ),
                "autoitem_auto_close_sessions": self._bool_setting(
                    getattr(self, "_autoitem_auto_close_var", None)
                ),
                "close_on_exit": self._bool_setting(
                    getattr(self, "_close_on_exit_var", None)
                ),
                "autoitem_accounts": [
                    {
                        "user": r["user"].get(),
                        "pwd": encrypt_pwd(r["pwd"].get()),
                        "type": r["type"].get(),
                        "notify": r["notify"].get(),
                    }
                    for r in getattr(self, "_autoitem_acc_rows", [])
                    if r["user"].get().strip()
                ],
                "inventory_accounts": [
                    {
                        "user": r["user"].get(),
                        "pwd": encrypt_pwd(r["pwd"].get()),
                        "type": r["type"].get(),
                    }
                    for r in getattr(self, "_inv_rows", [])
                    if r["user"].get().strip()
                ],
                "autoitem_webhooks": [
                    {
                        "url": encrypt_pwd(r.get_data()),
                        "enabled": r.is_enabled(),
                        "name": r.get_name(),
                    }
                    for r in getattr(self, "_autoitem_wh_rows", [])
                    if r.get_data()
                ],
                "autoitem_enabled": getattr(
                    self, "_autoitem_var", type("x", (), {"get": lambda s: False})()
                ).get(),
                "completed_pairs": self._snapshot_completed_pairs(),
                "geometry": geo,
                "accounts": accounts,
                "keywords": keywords,
                "recent_keyword_files": list(
                    getattr(self, "_kw_recent_files", None) or []
                )[:10],
                "recent_account_files": list(
                    getattr(self, "_acc_recent_files", None) or []
                )[:10],
                "recent_autoitem_files": list(
                    getattr(self, "_autoitem_recent_files", None) or []
                )[:10],
                "recent_inventory_files": list(
                    getattr(self, "_inv_recent_files", None) or []
                )[:10],
                # ไฟล์ที่โหลดล่าสุดของแต่ละแท็บ — เปิดแอปครั้งหน้า dropdown จะ
                # ไฮไลต์ชื่อไฟล์นั้นเป็น "ไฟล์ปัจจุบัน" ทันที (แทน placeholder)
                "last_loaded_keyword_file": getattr(
                    self, "_kw_last_loaded_path", None
                ),
                "last_loaded_account_file": getattr(
                    self, "_acc_last_loaded_path", None
                ),
                "last_loaded_autoitem_file": getattr(
                    self, "_autoitem_last_loaded_path", None
                ),
                "last_loaded_inventory_file": getattr(
                    self, "_inv_last_loaded_path", None
                ),
                # สี log แต่ละหมวดที่ผู้ใช้ปรับในแท็บตั้งค่า (dict หมวด → hex)
                "log_colors": dict(getattr(self, "_log_colors", {})),
                # พาเล็ตสีประจำไอดี [username] (list ของ hex)
                "log_id_palette": list(
                    getattr(self, "_log_id_palette", None) or DEFAULT_ID_PALETTE
                ),
                # โหมดสี log: True = ตามหมวด / False = ไอดีทาสีทั้งบรรทัด
                "color_by_category": bool(
                    getattr(
                        self,
                        "_color_by_category_var",
                        type("x", (), {"get": lambda s: True})(),
                    ).get()
                ),
                # สถานะตัวกรอง log (หมวดสีที่เลือก) + ช่องค้นหา — จำข้ามโปรแกรม
                "log_filter_cats": sorted(
                    getattr(self, "_log_filter_cats", None) or []
                ),
                "log_search": str(getattr(self, "_log_search_var", None)
                                 and getattr(self, "_log_search_var").get() or ""),
            }
            buckets = _split_config_data(data)
            for path, bucket_data in buckets.items():
                _atomic_write_json(
                    path, bucket_data, backup=(path == CONFIG_ACCOUNT_FILE)
                )
            return True
        except Exception as e:
            for path in list(_CONFIG_FILE_KEYS.keys()) + [CONFIG_AUTOMATION_FILE]:
                try:
                    if os.path.exists(path + ".tmp"):
                        os.remove(path + ".tmp")
                except Exception as _e:
                    _logger.debug("ignored error cleaning up %s.tmp: %s", path, _e)
            try:
                self.log(f"⚠ บันทึกการตั้งค่าล้มเหลว: {e}")
            except Exception as _e:
                _logger.debug("ignored error at app_settings.py:124: %s", _e)
            return False

    def _load_settings(self):
        try:
            _migrate_legacy_single_file_config()
            data = _merge_config_files()
            if not data:
                return
            if "version" in data:
                # 'version' ใน config ยุคเก่า (Selenium) เคยเก็บค่า Chrome version
                # เช่น "126.0.6478.127" — ไม่ใช่ค่าหน่วงล็อกอิน ต้องกรองทิ้ง
                # แล้วใช้ค่าเริ่มต้นแทน กันตัวเลขเพี้ยนไปแสดงในช่องหน่วงล็อกอิน
                delay_val = _sanitize_delay_config(data["version"])
                if delay_val is None:
                    delay_val = 2
                    _logger.warning(
                        "config 'version' ไม่ใช่ค่าหน่วงล็อกอินที่ถูกต้อง "
                        "(อาจเป็น Chrome version ยุคเก่า): %r — ใช้ค่าเริ่มต้น %s",
                        data["version"],
                        delay_val,
                    )
                self.version_entry.set(f"{delay_val:g}")
                # ค่าที่บันทึกเก่าไม่อยู่ในลิสต์ dropdown → เพิ่มให้ เห็นค่าเดิมและเลือกได้
                if f"{delay_val:g}" not in getattr(self, "_login_delay_values", []):
                    try:
                        vals = list(getattr(self, "_login_delay_values", []) or [])
                        vals.append(f"{delay_val:g}")
                        self.version_entry.configure(values=vals)
                        self._login_delay_values = vals
                    except Exception:
                        pass
            if "auto_apply_delay" in data or "auto_detect_ver" in data:
                # "auto_detect_ver" คือ key เก่ายุค Chrome — อ่านทั้งสองเพื่อความเข้ากันได้
                old = data.get("auto_detect_ver", data.get("auto_apply_delay"))
                self._auto_apply_delay_var.set(bool(old))
                if getattr(self, "_tgl_autover_update", None):
                    self._tgl_autover_update()
            if "concurrency" in data or "max_concurrent" in data:
                try:
                    # "max_concurrent" คือ key เก่ายุคก่อนเปลี่ยนชื่อ — อ่านทั้งสอง
                    # เพื่อไม่ให้ผู้ใช้อัปเกรดแล้วเสียค่าจำนวนพร้อมกันที่ตั้งไว้
                    # (ใน config เก่ายังเก็บเป็น string จากช่องกรอก → ต้อง int() + clamp)
                    val = data.get("concurrency", data.get("max_concurrent"))
                    self._concurrency_var.set(max(1, min(MAX_CONCURRENCY, int(val))))
                except Exception:
                    # ค่าใน config เก่าเสีย (ไม่ใช่ตัวเลข เช่น ว่าง/ตัวอักษร)
                    # → ใช้ค่าเริ่มต้น แต่ต้องแจ้ง log กันเงียบๆ
                    _logger.warning(
                        "config 'concurrency/max_concurrent' ไม่ใช่ตัวเลขที่ถูกต้อง: %r "
                        "— ใช้ค่าเริ่มต้น %s",
                        data.get("concurrency", data.get("max_concurrent")),
                        self._concurrency_var.get(),
                    )
            if "autoitem_concurrency" in data:
                try:
                    val = data["autoitem_concurrency"]
                    self._autoitem_concurrency_var.set(max(1, min(MAX_CONCURRENCY, int(val))))
                except Exception:
                    _logger.warning(
                        "config 'autoitem_concurrency' ไม่ใช่ตัวเลขที่ถูกต้อง: %r "
                        "— ใช้ค่าเริ่มต้น %s",
                        data.get("autoitem_concurrency"),
                        self._autoitem_concurrency_var.get(),
                    )
            if "inventory_concurrency" in data:
                try:
                    val = data["inventory_concurrency"]
                    self._inv_concurrency_var.set(max(1, min(MAX_CONCURRENCY, int(val))))
                except Exception:
                    _logger.warning(
                        "config 'inventory_concurrency' ไม่ใช่ตัวเลขที่ถูกต้อง: %r "
                        "— ใช้ค่าเริ่มต้น %s",
                        data.get("inventory_concurrency"),
                        self._inv_concurrency_var.get(),
                    )
            if "notify" in data:
                self.notify_var.set(data["notify"])
                if getattr(self, "_tgl_notify_update", None):
                    self._tgl_notify_update()
            if "resume" in data:
                self._resume_var.set(data["resume"])
                if getattr(self, "_tgl_resume_update", None):
                    self._tgl_resume_update()
            if "inv_auto_close_sessions" in data:
                self._inv_auto_close_var.set(bool(data["inv_auto_close_sessions"]))
                if getattr(self, "_tgl_inv_auto_close_update", None):
                    self._tgl_inv_auto_close_update()
            if "autoitem_auto_close_sessions" in data:
                self._autoitem_auto_close_var.set(
                    bool(data["autoitem_auto_close_sessions"])
                )
                if getattr(self, "_tgl_autoitem_auto_close_update", None):
                    self._tgl_autoitem_auto_close_update()
            if "close_on_exit" in data:
                self._close_on_exit_var.set(bool(data["close_on_exit"]))
                if getattr(self, "_tgl_close_on_exit_update", None):
                    self._tgl_close_on_exit_update()
            if "start_with_windows" in data:
                self._start_with_windows_var.set(bool(data["start_with_windows"]))
                if getattr(self, "_tgl_startup_update", None):
                    self._tgl_startup_update()
                set_startup_enabled(self._start_with_windows_var.get())
            if data.get("discord_webhooks"):
                try:
                    for r in self._webhook_rows:
                        r.destroy()
                    self._webhook_rows.clear()
                    for item in data["discord_webhooks"]:
                        if isinstance(item, dict):
                            url = decrypt_pwd(item.get("url", ""))
                            enabled = item.get("enabled", True)
                            name = item.get("name", "")
                        else:
                            url = decrypt_pwd(item)
                            enabled = True
                            name = ""
                        if url:
                            self._add_webhook_row(url, enabled=enabled, name_text=name)
                    self._update_webhook_count()
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:182: %s", _e)
            elif data.get("discord_webhook"):
                try:
                    url = decrypt_pwd(data["discord_webhook"])
                    if url:
                        for r in self._webhook_rows:
                            r.destroy()
                        self._webhook_rows.clear()
                        self._add_webhook_row(url)
                        self._update_webhook_count()
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:193: %s", _e)
            if not self._webhook_rows and data.get("discord_quick_webhooks"):
                try:
                    for item in data["discord_quick_webhooks"]:
                        if isinstance(item, dict):
                            url = decrypt_pwd(item.get("url", ""))
                            enabled = item.get("enabled", True)
                            name = item.get("name", "")
                        else:
                            url = decrypt_pwd(item)
                            enabled = True
                            name = ""
                        if url:
                            self._add_webhook_row(url, enabled=enabled, name_text=name)
                    self._update_webhook_count()
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:209: %s", _e)
            if data.get("discord_avatar_url"):
                url = data["discord_avatar_url"]
                if url.startswith("http"):
                    self.discord_avatar_entry.delete(0, "end")
                    self.discord_avatar_entry.configure(fg=FG)
                    self.discord_avatar_entry.insert(0, url)
                    self._avatar_placeholder_shown = False
            elif data.get("discord_quick_avatar_url"):
                url = data["discord_quick_avatar_url"]
                if url.startswith("http"):
                    self.discord_avatar_entry.delete(0, "end")
                    self.discord_avatar_entry.configure(fg=FG)
                    self.discord_avatar_entry.insert(0, url)
                    self._avatar_placeholder_shown = False
            if data.get("discord_bot_name"):
                try:
                    name = data["discord_bot_name"].strip()
                    if name:
                        self.discord_botname_entry.delete(0, "end")
                        self.discord_botname_entry.configure(fg=FG)
                        self.discord_botname_entry.insert(0, name)
                        self._botname_placeholder_shown = False
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:235: %s", _e)
            if data.get("auto_daily_key"):
                self._auto_daily_key_var.set(True)
                self.root.after(100, self._update_daily_key_toggle_visual)
                self._toggle_daily_key_watcher()
            if data.get("autoitem_accounts"):
                try:
                    self._autoitem_clear_acc(silent=True)
                    _autoitem_pwd_fail = 0
                    for item in data["autoitem_accounts"]:
                        _pwd = decrypt_pwd(item.get("pwd", ""))
                        if not _pwd and item.get("pwd"):
                            _autoitem_pwd_fail += 1
                        self._autoitem_add_acc(
                            user=item.get("user", ""),
                            pwd=_pwd,
                            login_type=item.get("type", "Game ID"),
                            notify=item.get("notify", True),
                        )
                    if _autoitem_pwd_fail:
                        self.log(
                            f"⚠ พบ {_autoitem_pwd_fail} บัญชี (โหมดรับไอเทมอัตโนมัติ) "
                            f"ที่ถอดรหัสรหัสผ่านไม่สำเร็จ — กรุณากรอกรหัสผ่านใหม่"
                        )
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:260: %s", _e)
            if data.get("inventory_accounts"):
                try:
                    self._inv_clear_acc(silent=True)
                    _inv_pwd_fail = 0
                    for item in data["inventory_accounts"]:
                        _pwd = decrypt_pwd(item.get("pwd", ""))
                        if not _pwd and item.get("pwd"):
                            _inv_pwd_fail += 1
                        self._inv_add_acc(
                            user=item.get("user", ""),
                            pwd=_pwd,
                            login_type=item.get("type", "Game ID"),
                        )
                    if _inv_pwd_fail:
                        self.log(
                            f"⚠ พบ {_inv_pwd_fail} บัญชี (แท็บฝาก/เบิก) "
                            f"ที่ถอดรหัสรหัสผ่านไม่สำเร็จ — กรุณากรอกรหัสผ่านใหม่"
                        )
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:inv_accounts: %s", _e)
            if data.get("autoitem_webhooks"):
                try:
                    self._autoitem_clear_wh(silent=True)
                    for item in data["autoitem_webhooks"]:
                        self._autoitem_add_wh(
                            url=decrypt_pwd(item.get("url", "")),
                            enabled=item.get("enabled", True),
                            name_text=item.get("name", ""),
                        )
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:271: %s", _e)
            if data.get("autoitem_avatar_url"):
                try:
                    url = data["autoitem_avatar_url"]
                    if url.startswith("http"):
                        self._autoitem_avatar_entry.delete(0, "end")
                        self._autoitem_avatar_entry.configure(fg=FG)
                        self._autoitem_avatar_entry.insert(0, url)
                        self._autoitem_avatar_placeholder_shown = False
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:288: %s", _e)
            if data.get("autoitem_bot_name"):
                try:
                    name = data["autoitem_bot_name"].strip()
                    if name:
                        self._autoitem_botname_entry.delete(0, "end")
                        self._autoitem_botname_entry.configure(fg=FG)
                        self._autoitem_botname_entry.insert(0, name)
                        self._autoitem_botname_placeholder_shown = False
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:298: %s", _e)
            if data.get("autoitem_enabled"):
                try:
                    accs = self._autoitem_valid_accounts()
                    if accs:
                        self.root.after(200, self._autoitem_auto_resume)
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:305: %s", _e)
            if data.get("log_colors"):
                try:
                    merged = dict(DEFAULT_LOG_COLORS)
                    for cat, val in data["log_colors"].items():
                        if cat in merged:
                            merged[cat] = normalize_hex_color(val, merged[cat])
                    self._log_colors = merged
                    if hasattr(self, "_apply_log_colors"):
                        self._apply_log_colors()
                    if hasattr(self, "_refresh_log_color_row"):
                        for cat in list(getattr(self, "_log_color_rows", {})):
                            self._refresh_log_color_row(cat)
                except Exception as _e:
                    _logger.debug(
                        "ignored error at app_settings.py log_colors: %s", _e
                    )
            # ตัวกรอง log + ช่องค้นหา — dashboard สร้างเสร็จแล้วตอนนี้ (build มาก่อน
            # load ใน __init__) ใช้ตัวกรอง/คำค้นที่บันทึกไว้กับ widget ที่มีอยู่จริงทันที
            try:
                self._saved_log_filter = [
                    c for c in (data.get("log_filter_cats") or [])
                    if c in {"error", "warn", "success", "login", "keyword", "cookie"}
                ]
            except Exception:
                self._saved_log_filter = []
            try:
                self._saved_log_search = str(data.get("log_search") or "")
            except Exception:
                self._saved_log_search = ""
            try:
                self._log_filter_cats = set(self._saved_log_filter)
                if hasattr(self, "_refresh_log_filter_chips"):
                    self._refresh_log_filter_chips()
                # log ที่วาดไปแล้วก่อน load settings (drain รันก่อน load ใน
                # __init__) ต้องวาดใหม่ให้ตรงกับตัวกรองที่เพิ่งโหลด — กัน log
                # แรกๆ หลุดมาแสดงทั้งที่ควรถูกกรองทิ้ง
                if hasattr(self, "_render_log_lines"):
                    self._render_log_lines()
            except Exception as _e:
                _logger.debug("ignored error applying saved log filter: %s", _e)
            try:
                if self._saved_log_search and hasattr(self, "_log_search_var"):
                    self._log_search_var.set(self._saved_log_search)
            except Exception as _e:
                _logger.debug("ignored error applying saved log search: %s", _e)
            if data.get("log_id_palette"):
                try:
                    palette = []
                    for i, val in enumerate(data["log_id_palette"]):
                        palette.append(
                            normalize_hex_color(
                                val,
                                DEFAULT_ID_PALETTE[i % len(DEFAULT_ID_PALETTE)],
                            )
                        )
                    if len(palette) >= 1:
                        self._log_id_palette = palette[:24]
                        if hasattr(self, "_apply_id_palette"):
                            self._apply_id_palette()
                        if hasattr(self, "_rebuild_id_color_rows"):
                            self._rebuild_id_color_rows()
                except Exception as _e:
                    _logger.debug(
                        "ignored error at app_settings.py id palette: %s", _e
                    )
            if "color_by_category" in data:
                try:
                    self._color_by_category_var.set(bool(data["color_by_category"]))
                    if getattr(self, "_tgl_color_mode_update", None):
                        self._tgl_color_mode_update()
                except Exception as _e:
                    _logger.debug(
                        "ignored error at app_settings.py color mode: %s", _e
                    )
            if data.get("completed_pairs"):
                try:
                    self._completed_pairs_restore(
                        tuple(p)
                        for p in data["completed_pairs"]
                        if isinstance(p, (list, tuple)) and len(p) == 2
                    )
                except Exception as _e:
                    _logger.debug("ignored error at app_settings.py:314: %s", _e)
            if "geometry" in data and self.container is self.root:
                geo = data["geometry"]
                if isinstance(geo, str) and re.match(
                    r"^\d+x\d+([+-]\d+[+-]\d+)?$", geo.strip()
                ):
                    try:
                        self.root.geometry(self._clamp_geometry_to_screen(geo.strip()))
                        self.root.update_idletasks()
                    except Exception as _e:
                        _logger.debug("ignored error at app_settings.py:324: %s", _e)
            if data.get("accounts"):
                for r in self._rows:
                    r.destroy()
                self._rows.clear()
                rev_type = {"gameid": "Game ID", "ggpassport": "GG Passport"}
                rev_rank = {"rank1": "แรงค์ 1", "rank2": "แรงค์ 2", "skip": "ไม่เลือก"}
                rev_unit = {v: k for k, v in UNIT_MAP.items()}  # suppress_log during batch load
                # backward compat: ชื่อหน่วยเก่าที่เปลี่ยนไป → map ไปชื่อใหม่
                _UNIT_OLD_TO_NEW = {
                    "Delta Force": "DELTA",
                    "Force Recon": "FORCERECOX",
                    "Spetsnaz": "SpetSnaz",
                }
                for old_name, new_name in _UNIT_OLD_TO_NEW.items():
                    if old_name in rev_unit:
                        rev_unit[new_name] = rev_unit.pop(old_name)
                _pwd_decrypt_failed = [0]

                prepared = []
                for acc in data["accounts"]:
                    u, p = acc[0], decrypt_pwd(acc[1])
                    if not p and acc[1]:
                        _pwd_decrypt_failed[0] += 1
                    t = rev_type.get(acc[2], "Game ID") if len(acc) > 2 else "Game ID"
                    r = rev_rank.get(acc[3], "แรงค์ 1") if len(acc) > 3 else "แรงค์ 1"
                    un = rev_unit.get(acc[4], "ไม่เลือก") if len(acc) > 4 else "ไม่เลือก"
                    un2 = rev_unit.get(acc[5], "ไม่เลือก") if len(acc) > 5 else "ไม่เลือก"
                    prepared.append((u, p, t, r, un, un2))

                # Batch-create rows to prevent UI freeze with 100-500 accounts
                BATCH_SIZE = 50
                def _batch_install(idx=0):
                    end = min(idx + BATCH_SIZE, len(prepared))
                    for i in range(idx, end):
                        u, p, t, r, un, un2 = prepared[i]
                        self._add_row(u, p, t)
                        row = self._rows[-1]
                        row.rank_var.set(r)
                        row._update_rank_color()
                        row.unit_var.set(un)
                        row._update_unit_color()
                        row.unit2_var.set(un2)
                        row._update_unit2_color()
                    self._update_count()
                    if end < len(prepared):
                        self.root.after_idle(lambda: _batch_install(end))
                    else:
                        AccountRow._suppress_log = False
                        if _pwd_decrypt_failed[0]:
                            self.log(
                                f"⚠ พบ {_pwd_decrypt_failed[0]} บัญชีที่ถอดรหัสรหัสผ่านไม่สำเร็จ "
                                f"(ช่องรหัสผ่านจะว่างเปล่า) — อาจเกิดจากไลบรารี cryptography ไม่ได้ติดตั้ง "
                                f"หรือไฟล์กุญแจเข้ารหัสถูกย้าย/ลบ กรุณากรอกรหัสผ่านใหม่ให้บัญชีเหล่านั้น"
                            )
                AccountRow._suppress_log = True
                if len(prepared) > BATCH_SIZE:
                    self._batch_install = _batch_install
                    self.root.after_idle(_batch_install)
                else:
                    # Small list — just create directly
                    for u, p, t, r, un, un2 in prepared:
                        self._add_row(u, p, t)
                        row = self._rows[-1]
                        row.rank_var.set(r)
                        row._update_rank_color()
                        row.unit_var.set(un)
                        row._update_unit_color()
                        row.unit2_var.set(un2)
                        row._update_unit2_color()
                    self._update_count()
                    AccountRow._suppress_log = False
                    if _pwd_decrypt_failed[0]:
                        self.log(
                            f"⚠ พบ {_pwd_decrypt_failed[0]} บัญชีที่ถอดรหัสรหัสผ่านไม่สำเร็จ "
                            f"(ช่องรหัสผ่านจะว่างเปล่า) — อาจเกิดจากไลบรารี cryptography ไม่ได้ติดตั้ง "
                            f"หรือไฟล์กุญแจเข้ารหัสถูกย้าย/ลบ กรุณากรอกรหัสผ่านใหม่ให้บัญชีเหล่านั้น"
                        )
            if data.get("keywords"):
                for r in self._keyword_rows:
                    r.destroy()
                self._keyword_rows.clear()
                for kw in data["keywords"]:
                    self._add_keyword_row(kw)
                self._update_keyword_count()
            # กู้รายชื่อไฟล์ .txt ที่เคยโหลดกลับมาให้ dropdown เลือกไฟล์
            # (แท็บคีย์เวิร์ด/บัญชี/รับไอเทมฟรี) — กรองเฉพาะไฟล์ที่ยังอยู่จริง
            # บนดิสก์ แล้วไฮไลต์ไฟล์ที่โหลดล่าสุด (last_loaded_*) เป็นไฟล์ปัจจุบัน
            for key, last_key, recent_attr, last_attr, cb_attr, paths_attr in (
                (
                    "recent_keyword_files",
                    "last_loaded_keyword_file",
                    "_kw_recent_files",
                    "_kw_last_loaded_path",
                    "kw_file_cb",
                    "_kw_file_cb_paths",
                ),
                (
                    "recent_account_files",
                    "last_loaded_account_file",
                    "_acc_recent_files",
                    "_acc_last_loaded_path",
                    "acc_file_cb",
                    "_acc_file_cb_paths",
                ),
                (
                    "recent_autoitem_files",
                    "last_loaded_autoitem_file",
                    "_autoitem_recent_files",
                    "_autoitem_last_loaded_path",
                    "autoitem_file_cb",
                    "_autoitem_file_cb_paths",
                ),
                (
                    "recent_inventory_files",
                    "last_loaded_inventory_file",
                    "_inv_recent_files",
                    "_inv_last_loaded_path",
                    "inv_file_cb",
                    "_inv_file_cb_paths",
                ),
            ):
                recent = data.get(key)
                if isinstance(recent, list):
                    setattr(
                        self,
                        recent_attr,
                        [
                            p
                            for p in recent[:10]
                            if isinstance(p, str)
                            and p.strip()
                            and os.path.exists(p)
                        ],
                    )
                last = data.get(last_key)
                if isinstance(last, str) and last in (
                    getattr(self, recent_attr, None) or []
                ):
                    setattr(self, last_attr, last)
                self._refresh_file_combobox(
                    getattr(self, recent_attr, None) or [],
                    cb_attr,
                    paths_attr,
                    selected_path=getattr(self, last_attr, None),
                )
        except Exception as e:
            self.log(f"⚠ โหลดการตั้งค่าบางส่วนไม่สำเร็จ: {e}")

    def _schedule_autosave(self):

        # หลังเลือกกู้คืน ห้าม autosave ของหน้าจอเก่าเขียนทับไฟล์ที่กู้คืนไว้
        if not getattr(self, "_settings_restore_pending", False):
            self._save_settings()
        self.root.after(30_000, self._schedule_autosave)

    def manual_save(self):
        ok = self._save_settings()
        self._flash_save_lbl("✅ บันทึกแล้ว" if ok else "❌ บันทึกไม่สำเร็จ (ดู Log)")
        if ok:
            self.log("💾 บันทึกการตั้งค่าแล้ว")
            self._log_settings_summary()

    def _log_settings_summary(self):
        """สรุปภาพรวมค่าตั้งค่าหลักที่เพิ่งบันทึก (เฉพาะตอนกดปุ่ม 💾 — autosave 30 วิ
        ไม่เรียก เพื่อกัน log ถี่เกินไป) แสดงเป็นบรรทัดย่อยใต้ 'บันทึกการตั้งค่าแล้ว'"""
        try:
            def _b(v):
                return "✅ เปิด" if v else "⬜ ปิด"

            try:
                delay = float(self.version_entry.get().strip() or 2.0)
            except Exception:
                delay = 2.0
            accs = sum(1 for r in self._rows if r.get_data())
            kws = sum(1 for r in self._keyword_rows if r.get_data())
            wh_all = [r for r in self._webhook_rows if r.get_data()]
            wh_on = sum(1 for r in wh_all if r.is_enabled())
            ai_accs = len(getattr(self, "_autoitem_acc_rows", []))
            ai_wh_all = [
                r for r in getattr(self, "_autoitem_wh_rows", []) if r.get_data()
            ]
            ai_wh_on = sum(1 for r in ai_wh_all if r.is_enabled())
            ai_on = bool(
                getattr(
                    self, "_autoitem_var", type("x", (), {"get": lambda s: False})()
                ).get()
            )
            daily = bool(
                getattr(
                    self,
                    "_auto_daily_key_var",
                    type("x", (), {"get": lambda s: False})(),
                ).get()
            )

            self.log(
                f"   ⚙ ภาพรวม: หน่วงล็อกอิน {delay:.0f} วิ · พร้อมกัน {self._concurrency_var.get()} · "
                f"แจ้งเตือน {_b(self.notify_var.get())} · ข้ามสำเร็จ {_b(self._resume_var.get())} · "
                f"เปิดพร้อมวินโดวส์ {_b(self._start_with_windows_var.get())}"
            )
            self.log(
                f"   📋 บัญชี {accs} · คีย์เวิร์ด {kws} · Webhook หลัก {wh_on}/{len(wh_all)} ช่อง · "
                f"รับไอเทม {'✅' if ai_on else '⬜'} ({ai_accs} บัญชี, {ai_wh_on}/{len(ai_wh_all)} ช่อง) · "
                f"คีย์ประจำวัน {'✅' if daily else '⬜'}"
            )
        except Exception as e:
            _logger.debug("settings summary log failed: %s", e)

