"""The main application window.

`App` used to be one ~7,150-line class (~300 methods). It is now composed
from focused mixins below, split by feature area (core, dialogs, settings,
settings diagnostics, settings-tab UI, keywords-tab UI, accounts-tab UI,
dashboard-tab UI, tables, webhook UI, autoitem tab, logging, stats,
runtime management, HTTP automation core, login flow, keyword
flow, window/tray chrome, run control). Each mixin still relies on
`self.xxx` shared state set up in `AppCoreMixin.__init__` / `_build_ui` —
that coupling is why this is a mixin split rather than fully independent
classes; see README.md for the reasoning.
"""

import logging
import sys

# --- UI tab mixins ---
from .ui.app_accounts_tab import AppAccountsTabMixin
from .ui.app_autoitem_ui import AppAutoitemUIMixin
from .ui.app_autoitem_webhook import AppAutoitemWebhookMixin
from .ui.app_dailykey_tab import AppDailyKeyTabMixin
from .ui.app_dashboard_tab import AppDashboardTabMixin
from .ui.app_dialogs import AppDialogsMixin
from .ui.app_inventory_tab import AppInventoryUIMixin

from .ui.app_keywords_tab import AppKeywordsTabMixin
from .ui.app_settings_tab import AppSettingsTabMixin
from .ui.app_tables import AppTablesMixin
from .ui.app_webhook_ui import AppWebhookUiMixin

# --- Engine mixins (core + automation + run control) ---
from .engine.app_core import AppCoreMixin
from .engine.app_runtime import AppRuntimeMixin
from .engine.app_window import AppWindowMixin
from .engine.app_automation import AppAutomationMixin
from .engine.app_login_flow_core import AppLoginFlowCoreMixin
from .engine.app_keyword_flow_core import AppKeywordFlowCoreMixin
from .engine.app_autoitem_engine import AppAutoitemEngineMixin
from .engine.app_inventory_engine import AppInventoryEngineMixin
from .engine.app_settings import AppSettingsMixin
from .engine.app_settings_diagnostics import AppSettingsDiagnosticsMixin
from .engine.app_run_control_flows import AppRunControlFlowsMixin
from .engine.app_run_control_session import AppRunControlSessionMixin
from .engine.app_run_control_helpers import AppRunControlHelpersMixin
from .engine.app_logging import AppLoggingMixin
from .engine.app_stats import AppStatsMixin

# --- Feature mixins ---
from .features.app_coupon_picker import AppCouponPickerMixin
from .features.app_manual_key_sender import AppManualKeySenderMixin
from .features.app_daily_key_watcher import AppDailyKeyWatcherMixin
from .features.app_webhook_history import AppWebhookHistoryMixin

# --- Core imports ---
from .core.log_system import setup_logging

_logger = logging.getLogger(__name__)

# ต้อง setup ก่อนสร้าง App/UI ใดๆ เพื่อให้ _logger ของทุกโมดูลใน sfkeyword_lib
# (รวมถึงตัวนี้เอง) เขียนลงไฟล์ได้ตั้งแต่บรรทัดแรกที่ import แพ็กเกจนี้
setup_logging()


class App(
    AppCoreMixin,
    AppDialogsMixin,
    AppSettingsMixin,
    AppSettingsDiagnosticsMixin,
    AppSettingsTabMixin,
    AppKeywordsTabMixin,
    AppAccountsTabMixin,
    AppDashboardTabMixin,
    AppDailyKeyTabMixin,
    AppTablesMixin,
    AppWebhookUiMixin,
    AppCouponPickerMixin,
    AppManualKeySenderMixin,
    AppDailyKeyWatcherMixin,
    AppWebhookHistoryMixin,
    AppAutoitemUIMixin,
    AppAutoitemWebhookMixin,
    AppAutoitemEngineMixin,
    AppInventoryUIMixin,
    AppInventoryEngineMixin,
    AppLoggingMixin,
    AppStatsMixin,
    AppRuntimeMixin,
    AppAutomationMixin,
    AppLoginFlowCoreMixin,
    AppKeywordFlowCoreMixin,
    AppWindowMixin,
    AppRunControlSessionMixin,
    AppRunControlHelpersMixin,
    AppRunControlFlowsMixin,
):
    pass


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception as _e:
        _logger.debug("ignored error at app.py:54: %s", _e)
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as _e:
        _logger.debug("ignored error at app.py:59: %s", _e)

__all__ = ["App"]
