# encoding:utf-8
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_JS = ROOT / "channel" / "web" / "static" / "js" / "console.js"
CONSOLE_CSS = ROOT / "channel" / "web" / "static" / "css" / "console.css"
LOGIN_HTML = ROOT / "channel" / "web" / "login.html"


def test_investment_tables_are_bounded_and_have_sticky_headers():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert ".investment-table-scroll" in css
    assert "max-height: min(560px, calc(100vh - 320px));" in css
    assert ".investment-table-scroll .investment-table th" in css
    assert "position: sticky;" in css


def test_backend_login_page_matches_console_auth_flow():
    html = LOGIN_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'id="login-page"' in html
    assert 'src="assets/logo.jpg"' in html
    assert "fetch('/auth/login'" in html
    assert "URLSearchParams(window.location.search)" in html
    assert "redirectToLogin(" in js
    assert "next=${encodeURIComponent(nextPath)}" in js


def test_investment_user_edit_and_record_details_use_modal_dialogs():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "function showInvestmentModal(" in js
    assert "function hideInvestmentModal(" in js
    assert "function openInvestmentUserDialog(" in js
    assert "showInvestmentModal('用户信息'" in js
    assert "showInvestmentModal('请求详情" in js
    assert "showInvestmentModal('内容详情" in js
    assert ".investment-modal-overlay" in css
    assert ".investment-modal" in css


def test_investment_config_fields_save_individually_after_change():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentConfigField(" in js
    assert "function markInvestmentConfigDirty(" in js
    assert "async function saveInvestmentConfigKey(" in js
    assert "data-config-key=" in js
    assert "investment-config-save" in js
    assert "保存全部配置" not in js


def test_investment_operations_show_unified_feedback_toasts():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "function showInvestmentToast(" in js
    assert "showInvestmentToast('用户已保存')" in js
    assert "showInvestmentToast('用户已停用')" in js
    assert "showInvestmentToast('已启动生成')" in js
    assert "showInvestmentToast('已设为生效')" in js
    assert ".investment-toast-container" in css
    assert ".investment-toast.success" in css
    assert ".investment-toast.error" in css


def test_investment_config_actions_align_with_controls():
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "investment-config-field textarea-config" in js
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert ".investment-config-field.textarea-config" in css
    assert ".investment-config-field.textarea-config .investment-config-actions" in css


def test_investment_config_exposes_unified_business_skill_version_management():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "技术分析与渲染" not in js
    assert "renderInvestmentSkillManager(" in js
    assert "loadInvestmentSkillVersions(" in js
    assert "renderInvestmentSkillConfigTable(" in js
    assert "uploadInvestmentSkill(" in js
    assert "activateInvestmentSkillVersion(" in js
    assert "deleteInvestmentSkillVersion(" in js
    assert "skill配置" in js
    assert "technical-analysis" in js
    assert "signal-card-renderer" in js
    assert "/api/investment/skills/versions" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/upload" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/activate" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/delete" in js
    assert "/api/investment/renderer-skill/" not in js
    assert "investment-skill-card" not in js


def test_daily_content_ui_exposes_effective_date_direct_png_and_audits():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "invest-content-effective-date" in js
    assert "invest-content-direct-output-mode" in js
    assert "direct_output_mode" in js
    assert "effective_date" in js
    assert "renderInvestmentContentHistoryGroups(" in js
    assert "renderInvestmentOperationAudits(" in js
    assert "/api/investment/audits" in js
    assert ".investment-date-group" in css
    assert ".investment-audit-list" in css


def test_investment_console_hides_actions_by_admin_role():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "let currentInvestmentAdmin = null;" in js
    assert "function investmentCan(" in js
    assert "async function loadInvestmentAdminSession(" in js
    assert "/api/investment/auth/me" in js
    assert "investmentButtonIfCan('users.write'" in js
    assert "investmentButtonIfCan('content.write'" in js
    assert "investmentIconButtonIfCan('cache.write'" in js
    assert "investmentCanView(" in js


def test_investment_records_ui_respects_cache_and_export_permissions():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "const cacheRequest = investmentCan('cache.read')" in js
    assert "investmentFetchJson('/api/investment/cache')" in js
    assert "const cacheSection = investmentCan('cache.read')" in js
    assert "renderInvestmentCacheTable(caches.entries || [])" in js
    assert "investmentButtonIfCan('records.export', 'fa-download'" in js
    assert "investmentButtonIfCan('records.export', 'fa-calendar-days'" in js
    assert "investmentButtonIfCan('records.export', 'fa-chart-pie'" in js


def test_investment_health_ui_exposes_manual_full_check_and_levels():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "async function renderInvestmentHealth(runSmoke = false)" in js
    assert "/api/investment/health?smoke=1" in js
    assert "运行完整检查" in js
    assert "window.runInvestmentFullHealthCheck" in js
    assert "check.level" in js
    assert "warning" in js
    assert "不可上线" in js
    assert ".investment-health-summary.warning" in css
    assert ".investment-badge.warning" in css
