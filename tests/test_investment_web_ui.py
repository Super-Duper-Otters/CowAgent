# encoding:utf-8
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_JS = ROOT / "channel" / "web" / "static" / "js" / "console.js"
CONSOLE_CSS = ROOT / "channel" / "web" / "static" / "css" / "console.css"
LOGIN_HTML = ROOT / "channel" / "web" / "login.html"
CHAT_HTML = ROOT / "channel" / "web" / "chat.html"
WEB_CHANNEL = ROOT / "channel" / "web" / "web_channel.py"


def _js_function_body(js: str, name: str) -> str:
    match = re.search(rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*{{", js)
    assert match, f"{name} function not found"
    depth = 1
    index = match.end()
    while index < len(js) and depth:
        char = js[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    assert depth == 0, f"{name} function body not closed"
    return js[match.end():index - 1]


def test_investment_tables_are_bounded_and_have_sticky_headers():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert ".investment-table-scroll" in css
    assert "max-height: min(560px, calc(100vh - 320px));" in css
    assert ".investment-table-scroll .investment-table th" in css
    assert "position: sticky;" in css
    assert ".investment-table-wrap::after" in css
    assert ".investment-table tbody tr:hover td" in css
    assert ".investment-table td.investment-row-actions" in css
    assert "position: sticky;" in css
    assert "@media (max-width: 640px)" in css


def test_investment_table_wrappers_expose_scroll_regions():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    table_wrap_body = _js_function_body(js, "investmentTableWrap")
    record_shell_body = _js_function_body(js, "investmentRecordTableShell")

    assert 'role="region"' in table_wrap_body
    assert 'aria-label="' in table_wrap_body
    assert 'data-scroll-hint="左右滑动查看完整表格"' in table_wrap_body
    assert 'investmentTableWrap(tableHtml, true, \'业务记录表格\')' in record_shell_body


def test_investment_selects_reuse_cowagent_dropdown_ui():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    dropdown_body = _js_function_body(js, "investmentDropdown")
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    skill_row_body = _js_function_body(js, "renderInvestmentSkillConfigRow")

    assert "cfg-dropdown-selected" in dropdown_body
    assert "cfg-dropdown-menu" in dropdown_body
    assert "cfg-dropdown-item" in dropdown_body
    assert "data-investment-dropdown" in dropdown_body
    assert "handleInvestmentDropdownClick" in js
    click_body = _js_function_body(js, "handleInvestmentDropdownClick")
    assert "classList.toggle('open', willOpen)" in click_body
    assert "resetInvestmentDropdownMenu(item)" in click_body
    assert "positionInvestmentDropdownMenu(dropdown)" in click_body
    assert "dataset.value" in click_body
    assert "input.value = value" in click_body
    assert "stopImmediatePropagation()" in click_body
    assert "function positionInvestmentDropdownMenu(" in js
    position_body = _js_function_body(js, "positionInvestmentDropdownMenu")
    assert "getBoundingClientRect()" in position_body
    assert "position = 'fixed'" in position_body
    assert "zIndex = '9999'" in position_body
    assert "spaceAbove > spaceBelow" in position_body
    assert "querySelector('.cfg-dropdown-selected')" in position_body
    assert "minWidth = `${menuWidth}px`" in position_body
    assert "maxWidth = `${menuWidth}px`" in position_body
    assert "initInvestmentDropdowns" in js
    init_body = _js_function_body(js, "initInvestmentDropdowns")
    assert "root.matches('.cfg-dropdown[data-investment-dropdown]')" in init_body
    assert "initDropdown(" not in init_body
    assert "data-investment-dropdown-options" not in dropdown_body
    assert "investmentDropdown(`investment-records-filter-${key}`" in filters_body
    assert "<select" not in filters_body
    assert "investmentDropdown(`invest-skill-version-${escapeHtml(skillKey)}`" in skill_row_body
    assert "<select" not in skill_row_body
    assert ".investment-cow-dropdown" in css
    assert ".investment-cow-dropdown .cfg-dropdown-menu" in css
    assert "min-width: 0;" in css


def test_investment_date_inputs_have_visible_calendar_controls():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "input[type=\"date\"]" in css
    assert "::-webkit-calendar-picker-indicator" in css
    assert "color-scheme: dark;" in css


def test_investment_table_like_views_use_wide_containers():
    html = CHAT_HTML.read_text(encoding="utf-8")

    users_start = html.index('id="view-invest-users"')
    users_end = html.index('id="view-invest-daily-content"')
    users_body = html[users_start:users_end]
    daily_start = html.index('id="view-invest-daily-content"')
    daily_end = html.index('id="view-invest-content"')
    daily_body = html[daily_start:daily_end]
    content_start = html.index('id="view-invest-content"')
    content_end = html.index('id="view-invest-records"')
    content_body = html[content_start:content_end]
    records_start = html.index('id="view-invest-records"')
    records_end = html.index('id="view-invest-config"')
    records_body = html[records_start:records_end]

    assert "w-full max-w-[1600px] mx-auto" in users_body
    assert "w-full max-w-[1600px] mx-auto" in daily_body
    assert "w-full max-w-[1600px] mx-auto" in content_body
    assert "w-full max-w-[1600px] mx-auto" in records_body
    assert "max-w-6xl mx-auto" not in users_body
    assert "max-w-6xl mx-auto" not in daily_body
    assert "max-w-6xl mx-auto" not in content_body
    assert "max-w-6xl mx-auto" not in records_body


def test_investment_content_is_a_top_level_view():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'data-view="invest-content"' in html
    assert "<span>历史内容</span>" in html
    assert '<h2 class="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">历史内容</h2>' in html
    assert 'id="view-invest-content"' in html
    assert 'id="invest-content-content"' in html
    assert "'invest-content':" in js
    assert "if (viewId === 'invest-content') return renderInvestmentGeneratedContent();" in js
    assert "'invest-content': 'content.read'" in js


def test_investment_generated_content_uses_shared_artifact_file_tree():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderInvestmentGeneratedContent")
    load_body = _js_function_body(js, "loadInvestmentGeneratedContent")
    category_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")

    assert "/api/investment/artifacts" in load_body
    assert "/api/investment/cache" not in load_body
    assert "investment-artifact-browser" in category_body
    assert "investment-artifact-tree" in category_body
    assert "renderInvestmentArtifactTree(" in category_body
    assert "openInvestmentArtifactFile(" in js
    assert "renderInvestmentArtifactViewer(" in js
    assert "virtual_path" in js
    assert "raw_input.txt" in js
    assert "output" in js
    assert "intermediate" in js
    assert "investment-artifact-date open" in js
    assert "investment-artifact-package open" not in js
    assert "investment-artifact-folder open" not in js
    assert "investment-artifact-package-btn" in js
    assert "investment-artifact-folder-btn" in js
    assert "investment-artifact-file-btn" in js
    assert ".investment-artifact-package-btn" in css
    assert ".investment-artifact-folder-btn" in css
    assert ".investment-artifact-file-btn" in css
    assert "padding-left: 22px;" in css
    assert "padding-left: 40px;" in css
    assert "padding-left: 58px;" in css
    assert "investment-content-list" in render_body
    assert ".investment-artifact-browser" in css
    assert ".investment-artifact-tree" in css
    assert ".investment-artifact-viewer" in css


def test_rate_and_convertible_bond_content_are_merged_under_investment_content_page():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    sidebar_start = html.index("<!-- Investment Group -->")
    sidebar_end = html.index("</div>\n                </div>", sidebar_start)
    sidebar_body = html[sidebar_start:sidebar_end]
    daily_view_start = html.index('id="view-invest-daily-content"')
    daily_view_end = html.index('id="view-invest-content"')
    daily_view_body = html[daily_view_start:daily_view_end]
    daily_render_body = _js_function_body(js, "renderInvestmentDailyContent")

    assert 'data-view="invest-daily-content"' in sidebar_body
    assert "<span>投资内容</span>" in sidebar_body
    assert 'data-view="invest-rate"' not in sidebar_body
    assert 'data-view="invest-cb"' not in sidebar_body
    assert 'id="view-invest-rate"' not in html
    assert 'id="view-invest-cb"' not in html

    assert '<h2 class="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">投资内容</h2>' in daily_view_body
    assert 'id="invest-daily-content-content"' in daily_view_body
    assert "let currentInvestmentContentPanel = 'rate';" in js
    assert "function switchInvestmentContentPanel(" in js
    assert "async function renderInvestmentDailyContent(" in js
    assert "if (viewId === 'invest-daily-content') return renderInvestmentDailyContent();" in js
    assert "'invest-daily-content': 'content.read'" in js
    assert "investment-tab" in daily_render_body
    assert "利率内容" in daily_render_body
    assert "转债内容" in daily_render_body
    assert "renderInvestmentContent(currentInvestmentContentPanel)" in daily_render_body


def test_backend_login_page_matches_console_auth_flow():
    html = LOGIN_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'id="login-page"' in html
    assert 'src="assets/logo.jpg"' in html
    assert "fetch('/auth/login'" in html
    assert "URLSearchParams(window.location.search)" in html
    assert "redirectToLogin(" in js
    assert "next=${encodeURIComponent(nextPath)}" in js


def test_console_js_and_css_assets_are_not_browser_cached():
    source = WEB_CHANNEL.read_text(encoding="utf-8")
    assets_start = source.index("class AssetsHandler:")
    assets_end = source.index("class KnowledgeListHandler:")
    assets_body = source[assets_start:assets_end]

    assert "file_path in ('js/console.js', 'css/console.css')" in assets_body
    assert "web.header('Cache-Control', 'no-cache, no-store, must-revalidate')" in assets_body
    assert "web.header('Pragma', 'no-cache')" in assets_body


def test_chat_console_exposes_current_admin_and_logout():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'id="auth-user-summary"' in html
    assert 'id="auth-user-name"' in html
    assert 'id="auth-user-role"' in html
    assert 'id="auth-logout-btn"' in html
    assert "function updateAuthUserSummary(" in js
    assert "async function logoutConsole(" in js
    assert "fetch('/auth/logout'" in js
    assert "window.logoutConsole = logoutConsole" in js


def test_chat_header_omits_external_nav_buttons():
    html = CHAT_HTML.read_text(encoding="utf-8")

    assert 'title="Documentation"' not in html
    assert 'title="Website"' not in html
    assert 'title="GitHub"' not in html
    assert "https://docs.cowagent.ai" not in html
    assert "https://cowagent.ai" not in html


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
    assert "showInvestmentToast(action === 'enable' ? '用户已启用' : '用户已停用')" in js
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


def test_investment_skill_has_own_navigation_page():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")

    assert "技术分析与渲染" not in js
    assert 'data-view="invest-skills"' in html
    assert 'id="view-invest-skills"' in html
    assert "menu_invest_skills" in js
    assert "'invest-skills':" in js
    assert "renderInvestmentSkills()" in js
    assert "invest-skills-content" in js
    assert "renderInvestmentSkillManager(" in js
    assert "loadInvestmentSkillVersions(" in js
    assert "renderInvestmentSkillConfigTable(" in js
    assert "uploadInvestmentSkill(" in js
    assert "uploadInvestmentSkillPackage(" in js
    assert "saveInvestmentSkillSettings(" in js
    assert "activateInvestmentSkillVersion(" in js
    assert "deleteInvestmentSkillVersion(" in js
    assert "skill配置" in js
    assert "technical-analysis" in js
    assert "signal-card-renderer" in js
    assert "/api/investment/skills/versions" in js
    assert "/api/investment/skills/packages/upload" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/settings" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/upload" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/activate" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/delete" in js
    assert "/api/investment/renderer-skill/" not in js
    assert "investment-skill-card" not in js


def test_investment_skill_actions_are_moved_into_edit_dialog():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    row_start = js.index("function renderInvestmentSkillConfigRow(")
    row_end = js.index("function investmentSkillDialogItem(")
    row_body = js[row_start:row_end]

    assert "openInvestmentSkillDialog(" in row_body
    assert "fa-pen" in row_body
    assert "保存设置" not in row_body
    assert "切换版本" not in row_body
    assert "删除版本" not in row_body
    assert "invest-skill-file-${escapeHtml(skillKey)}" not in row_body

    assert "function openInvestmentSkillDialog(" in js
    assert "showInvestmentModal('编辑投资Skill'" in js
    assert "function saveInvestmentSkillDialog(" in js
    assert "saveInvestmentSkillDialog('${escapeHtml(skillKey)}')" in js
    assert "saveInvestmentSkillSettings(" in js
    assert "uploadInvestmentSkill(" in js
    assert "activateInvestmentSkillVersion(" in js
    assert "deleteInvestmentSkillVersion(" in js
    dialog_start = js.index("function renderInvestmentSkillDialogBody(")
    dialog_end = js.index("function openInvestmentSkillDialog(")
    dialog_body = js[dialog_start:dialog_end]
    assert "关闭', 'hideInvestmentModal()')" not in dialog_body
    assert "保存', `saveInvestmentSkillDialog" in dialog_body
    assert "切换版本" not in dialog_body


def test_investment_user_and_skill_edit_buttons_call_write_apis():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "setInvestmentUserStatus('${encodeURIComponent(user.openid)}'" in js
    assert "await investmentFetchJson(`/api/investment/users/${encodeURIComponent(openid)}/status/${action}`, {method: 'POST'})" in js
    assert "saveInvestmentUser('invest-user-modal')" in js
    assert "await investmentFetchJson('/api/investment/users', {" in js
    assert "openInvestmentSkillDialog('${escapeHtml(skillKey)}')" in js
    assert "await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/settings`, {" in js
    assert "await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(selectedVersion)}/activate`, {" in js


def test_investment_users_page_splits_customers_and_admin_staff():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "let currentInvestmentUserPanel = 'customers';" in js
    assert "function switchInvestmentUserPanel(" in js
    assert "renderInvestmentCustomerUsers(" in js
    assert "renderInvestmentAdminUsers(" in js
    assert "/api/investment/admin-users" in js
    assert "/api/investment/admin-users/${encodeURIComponent(username)}/status/${action}" in js
    assert "/api/investment/admin-users/${encodeURIComponent(username)}/password" in js
    assert "investmentCan('admin_users.read')" in js
    assert "investmentButtonIfCan('admin_users.write'" in js
    assert "investmentButtonIfCan('admin_users.reset_password'" in js
    assert "content_operator" in js
    assert "technical_operator" in js
    assert "role_uploader" not in js
    assert "role_poster" not in js


def test_investment_users_page_is_list_first_with_dialog_forms():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    customer_body = _js_function_body(js, "renderInvestmentCustomerUsers")
    admin_body = _js_function_body(js, "renderInvestmentAdminUsers")

    assert "investment-user-page" in customer_body
    assert "investment-user-toolbar" in customer_body
    assert "openInvestmentUserDialog()" in customer_body
    assert "invest-user-openid" not in customer_body
    assert "用户维护" not in customer_body

    assert "investment-user-page" in admin_body
    assert "investment-user-toolbar" in admin_body
    assert "openInvestmentAdminUserDialog()" in admin_body
    assert "invest-admin-username" not in admin_body
    assert "后台人员维护" not in admin_body

    assert "function openInvestmentAdminUserDialog(" in js
    assert "showInvestmentModal('后台人员信息'" in js
    assert ".investment-user-page" in css
    assert ".investment-user-toolbar" in css


def test_investment_boolean_controls_use_green_switches():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")

    config_field_body = _js_function_body(js, "renderInvestmentConfigField")
    service_checks_body = _js_function_body(js, "investmentUserServiceChecks")
    channel_fields_body = _js_function_body(js, "buildChannelFieldsHtml")

    assert "function investmentSwitch(" in js
    assert "class=\"investment-switch" in js
    assert "investment-switch-track" in js
    assert "investmentSwitch('启用', 'invest-admin-enabled'" in js
    assert "investmentSwitch('启用', 'invest-user-modal-enabled'" in js
    assert "investmentSwitch('直接上传最终 PNG', 'invest-content-direct-output-mode'" not in js
    assert "investmentSwitch(label, id, checked" in config_field_body
    assert "investmentSwitch(label, `${prefix}-service-${index}`" in service_checks_body
    assert "investmentSwitch('', inputId, Boolean(f.value)" in channel_fields_body
    assert "class=\"investment-check" not in js
    assert "<label><input" not in js
    assert '<label class="investment-switch">' in html
    assert '<input id="cfg-enable-thinking" type="checkbox">' in html
    assert "log-filter-switch" in html
    assert "peer-checked" not in html

    assert ".investment-switch" in css
    assert ".investment-switch-track" in css
    assert ".investment-switch-thumb" in css
    assert ".log-filter-switch" in css
    assert ".investment-switch input[type=\"checkbox\"]:checked + .investment-switch-track" in css
    assert "background: #35A85B;" in css


def test_investment_user_service_switches_normalize_all_selection():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    table_body = _js_function_body(js, "renderInvestmentUsersTable")
    service_checks_body = _js_function_body(js, "investmentUserServiceChecks")
    toggle_body = _js_function_body(js, "handleInvestmentUserServiceToggle")
    save_user_body = _js_function_body(js, "saveInvestmentUser")

    assert "const INVEST_CUSTOMER_SERVICE_OPTIONS" in js
    assert "function investmentNormalizeCustomerServices(" in js
    assert "function investmentExpandCustomerServicesForUi(" in js
    assert "function handleInvestmentUserServiceToggle(" in js
    assert "investmentExpandCustomerServicesForUi(user.allowed_services || ['all'])" in service_checks_body
    assert "data-service-value=\"${escapeHtml(value)}\"" in service_checks_body
    assert "['all', '全部']" in js
    assert "onchange=\"handleInvestmentUserServiceToggle" in service_checks_body
    assert "businessItems.forEach(item => { item.checked = true; })" in toggle_body
    assert "if (allItem && !businessItems.every(item => item.checked)) allItem.checked = false;" in toggle_body
    assert "investmentNormalizeCustomerServices(selectedServices)" in save_user_body
    assert "investmentCustomerServicesDisplay(user.allowed_services || [])" in table_body
    assert "join(', ')" not in table_body


def test_investment_users_toolbar_is_grouped_and_paginated():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "investmentUserState" in js
    assert "pagination:" in js
    assert "customers: {page: 1, page_size: 20" in js
    assert "renderInvestmentUserPagination('customers'" in js
    assert "function changeInvestmentUserPage(" in js
    assert "onclick=\"changeInvestmentUserPage('${panel}'" in js
    assert "applyInvestmentCustomerSearch()" in js
    assert "applyInvestmentAdminSearch()" in js
    assert "investment-user-toolbar-grid" in js
    assert "investment-toolbar-group primary" in js

    assert ".investment-user-toolbar-grid" in css
    assert ".investment-toolbar-group" in css
    assert ".investment-user-pagination" in css


def test_investment_customer_toolbar_has_separate_action_bar():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")

    assert "investment-user-toolbar-heading" in body
    assert "investment-user-actionbar" in body
    assert "investment-toolbar-section search" in body
    assert "investment-toolbar-section actions" in body
    assert "invest-users-keyword" in body
    assert "invest-users-keyword-field" in body
    assert "keyword_field" in body
    assert "['all', '全部']" in body
    assert "['openid', 'OpenID']" in body
    assert "['name', '姓名']" in body
    assert "['institution', '机构']" in body
    assert "['mobile', '手机号']" in body
    assert "['service', '服务']" in body
    assert "invest-users-export-enabled" not in body
    assert "openInvestmentCustomerExportDialog()" in body
    assert "openInvestmentUsersImportDialog()" in body
    assert "clearInvestmentCustomerSearch()" in body
    assert "清除搜索" in body
    assert body.index("applyInvestmentCustomerSearch()") < body.index("clearInvestmentCustomerSearch()")
    assert body.index("openInvestmentUserDialog()") < body.index("openInvestmentUsersImportDialog()")
    assert body.index("openInvestmentUsersImportDialog()") < body.index("openInvestmentCustomerExportDialog()")
    assert body.index("investment-user-toolbar-heading") < body.index("investment-user-actionbar")
    assert "keyword_field: 'all'" in js
    assert "keyword_field: document.getElementById('invest-users-keyword-field')?.value || 'all'" in js
    clear_body = _js_function_body(js, "clearInvestmentCustomerSearch")
    assert "keyword: ''" in clear_body
    assert "keyword_field: 'all'" in clear_body
    assert "page: '1'" in clear_body
    assert "renderInvestmentCustomerUsers()" in clear_body
    assert "window.clearInvestmentCustomerSearch = clearInvestmentCustomerSearch" in js


def test_investment_admin_toolbar_and_table_spacing_are_polished():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentAdminUsers")

    assert "investment-user-toolbar-heading" in body
    assert "investment-user-actionbar" in body
    assert "investment-toolbar-section search" in body
    assert "investment-toolbar-section actions" in body
    assert body.index("investment-toolbar-section search") < body.index("investment-toolbar-section actions")
    assert "openInvestmentAdminUserDialog()" in body

    assert "investment-user-toolbar-grid" in js
    assert "grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_auto]" in js
    assert "investment-toolbar-section" in js
    assert "investment-toolbar-group" in js
    assert "investment-user-pagination" in js
    assert "gap-3" in js
    assert "mt-4" in js
    assert "min-h-10" in js
    assert "bg-primary-500" in js
    assert "new Set([...tokens, ...mapped])" in js
    assert "replace(/<th\\b" in js
    assert "replace(/<td\\b" in js
    assert "replace(/<th(?![^>]*class=)" not in js

    assert ".investment-table-wrap::before" in css
    assert "content: none;" in css
    assert ".investment-btn.primary" in css
    assert "background: #35A85B;" in css
    assert "width: 100%;" in css
    assert "table-layout: fixed;" in css
    assert ".investment-table-wrap {\n    overflow: hidden;\n    border: 1px solid #e2e8f0;\n    border-radius: 8px;\n    background: #f8fafc;" in css
    assert "border-collapse: separate;" in css
    assert ".investment-table thead,\n.investment-table thead tr {\n    background: #f8fafc;" in css
    assert ".investment-table thead tr:first-child th:first-child" in css
    assert ".investment-table thead tr:first-child th:last-child" in css
    assert ".investment-user-page .investment-table th" in css
    assert "position: static !important;" in css
    assert ".investment-user-page .investment-table thead,\n.investment-user-page .investment-table thead tr,\n.investment-user-page .investment-table thead th" in css
    assert ".investment-user-page .investment-table > tbody:first-child > tr:first-child > *" in css
    assert ".investment-user-page .investment-table > tbody:first-child > tr:first-child > *:first-child" in css
    assert ".investment-user-page .investment-table > tbody:first-child > tr:first-child > *:last-child" in css
    assert ".investment-user-page .investment-table-scroll" in css
    assert "max-height: min(560px, calc(100vh - 360px));" in css
    assert "overflow: auto;" in css
    assert ".investment-user-page .investment-table th,\n.investment-user-page .investment-table td" in css
    assert "text-overflow: ellipsis;" in css
    assert "white-space: nowrap;" in css
    assert ".investment-user-page .investment-table th:first-child,\n.investment-user-page .investment-table td:first-child" in css
    assert "width: 24%;" in css
    assert ".investment-table-wrap > .investment-table:first-child" in css

    customer_table_body = _js_function_body(js, "renderInvestmentUsersTable")
    admin_table_body = _js_function_body(js, "renderInvestmentAdminUsersTable")
    assert "function investmentMiddleEllipsis(" in js
    assert "function investmentFormatBeijingDate(" in js
    assert '<td title="${escapeHtml(user.openid)}">${escapeHtml(investmentMiddleEllipsis(user.openid, 10, 8))}</td>' in customer_table_body
    assert "investmentFormatBeijingDate(user.auth_end_at || '')" in customer_table_body
    assert "investmentFormatBeijingTime(user.auth_end_at || '')" not in customer_table_body
    assert '<td title="${escapeHtml(user.username || \'\')}">${escapeHtml(user.username || \'\')}</td>' in admin_table_body


def test_investment_customer_import_uses_dialog_with_template_and_result():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")
    user_dialog_body = _js_function_body(js, "openInvestmentUserDialog")
    import_body = _js_function_body(js, "openInvestmentUsersImportDialog")
    import_section_body = _js_function_body(js, "renderInvestmentUserImportSection")

    assert "openInvestmentUsersImportDialog()" in body
    assert "renderInvestmentUserImportSection()" not in user_dialog_body
    assert "invest-users-import-file" not in body
    assert "批量导入客户" in import_body
    assert "renderInvestmentUserImportSection()" in import_body
    assert "存在用户名单示例模板" in import_section_body
    assert "/api/investment/users/import-template.xlsx" in import_section_body
    assert "invest-users-import-result" in import_section_body
    assert "parseInvestmentUsersImport()" in import_section_body
    assert "confirmInvestmentUsersImport()" in js
    assert "解析文件" in import_section_body
    assert "确认导入" in js
    assert "commit" in js
    assert "解析中" in js
    assert "new_users" in js
    assert "function renderInvestmentImportResult(data, committed = false)" in js
    assert "renderInvestmentImportResult(data, false)" in js
    assert "renderInvestmentImportResult(data, true)" in js
    assert "window.openInvestmentUsersImportDialog = openInvestmentUsersImportDialog" in js


def test_investment_customer_export_uses_dedicated_dialog():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    toolbar_body = _js_function_body(js, "renderInvestmentCustomerUsers")
    export_body = _js_function_body(js, "openInvestmentCustomerExportDialog")
    download_body = _js_function_body(js, "downloadInvestmentUsersExport")
    legacy_body = _js_function_body(js, "exportInvestmentUsers")

    assert "openInvestmentCustomerExportDialog()" in toolbar_body
    assert "showInvestmentModal('导出客户名单'" in export_body
    assert "invest-users-export-enabled" in export_body
    assert "downloadInvestmentUsersExport()" in export_body
    assert "investmentDownload('/api/investment/export/users.xlsx'" in download_body
    assert "openInvestmentCustomerExportDialog()" in legacy_body


def test_investment_customer_render_uses_response_rows_with_response_pagination():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")

    users_pos = body.index("const users = data.users || [];")
    pagination_pos = body.index("investmentUserApplyPagination('customers', data.pagination);")
    table_pos = body.index("${renderInvestmentUsersTable(users)}")
    assert users_pos < pagination_pos < table_pos
    assert "${renderInvestmentUserPagination('customers', data.pagination)}" in body


def test_investment_config_no_longer_embeds_skill_manager():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    config_start = js.index("async function renderInvestmentConfig()")
    config_end = js.index("function renderInvestmentSkillManager()")
    config_body = js[config_start:config_end]

    assert "renderInvestmentSkillManager()" not in config_body
    assert "loadInvestmentSkillVersions()" not in config_body


def test_daily_content_ui_exposes_effective_date_and_audits_without_direct_png():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "invest-content-effective-date" in js
    assert "invest-content-direct-output-mode" not in js
    assert "direct_output_mode" not in js
    assert "直接上传最终 PNG" not in js
    assert "直传 PNG" not in js
    assert "直接 PNG" not in js
    assert "effective_date" in js
    assert "renderInvestmentContentHistoryGroups(" in js
    assert "renderInvestmentOperationAudits(" in js
    assert "/api/investment/audits" in js
    assert ".investment-audit-list" in css


def test_daily_content_layout_places_current_and_upload_side_by_side_above_history():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    content_body = _js_function_body(js, "renderInvestmentContent")
    current_body = _js_function_body(js, "renderInvestmentCurrentEffective")
    upload_body = _js_function_body(js, "renderInvestmentContentUploadPanel")
    history_body = _js_function_body(js, "renderInvestmentContentHistoryGroups")

    assert "investment-daily-content-page" in content_body
    assert "investment-workbench investment-daily-content-workbench" not in content_body
    assert "investment-daily-content-workbench" not in content_body
    assert "investment-content-top-panel" in content_body
    assert "investment-content-top" in content_body
    assert "investment-content-history-panel" in content_body
    assert "investment-content-history-body" in content_body
    assert "investment-history-header" in content_body
    assert "investment-history-heading-row" in content_body
    assert "investment-history-filterbar" in content_body
    assert "investment-history-date-field" in content_body
    assert "investment-date-control" in js
    assert "fa-calendar-days" in js
    assert "investment-date-picker-button" in js
    assert "investmentRenderDateControl(historyDateId" in content_body
    assert "clearInvestmentContentHistoryDate" not in js
    assert "onchange=\"refreshInvestmentContentRecords('${serviceType}', {effective_date: investmentContentHistoryEffectiveDate('${serviceType}')})\"" in content_body
    assert "placeholder: '选择日期'" in content_body
    assert "当前日期：" not in content_body
    assert "展示全部历史内容" not in content_body
    assert "function investmentRenderDateControl(" in js
    assert "function investmentToggleDatePicker(" in js
    assert "function investmentRenderDatePickerPanel(" in js
    assert "function investmentSelectDate(" in js
    assert "showPicker" not in js
    assert 'type="date"' not in js
    assert "investment-daily-current-panel" in current_body
    assert "investment-daily-upload-panel" in upload_body
    assert "investment-daily-upload-stage image-mode" in upload_body
    assert "investment-upload-dropzone" in upload_body
    assert 'for="invest-content-files"' in upload_body
    assert 'type="file" accept="image/*" multiple' in upload_body
    assert 'id="invest-content-file-preview"' in upload_body
    assert "investment-upload-preview" in upload_body
    assert "investment-upload-supplement" in upload_body
    assert "补充文本（可选）" in upload_body
    assert "段子/补充文本（可选）" in upload_body
    assert "investment-upload-text-mode" in upload_body
    assert 'id="invest-content-source-text"' in upload_body
    assert 'id="invest-content-expires-mode"' not in upload_body
    assert "investmentSwitch('指定失效时间', 'invest-content-expires-enabled'" in upload_body
    assert 'id="invest-content-expires-fields"' in upload_body
    assert "investment-expires-fields disabled hidden" in upload_body
    assert "invest-content-effective-date" not in upload_body
    assert "<span>生效日期</span>" not in upload_body
    assert "investmentRenderDateControl('invest-content-expires-date'" in upload_body
    assert "investmentRenderTimeControl('invest-content-expires-time', '00:00')" in upload_body
    assert 'type="time"' not in upload_body
    assert "指定失效时间" in upload_body
    assert "不指定失效时间" in upload_body
    assert 'onchange="syncInvestmentDefaultExpiresAt()"' not in upload_body
    assert 'onchange="toggleInvestmentExpiresAt(this.checked)"' in upload_body
    assert "investment-upload-mode-bar" in upload_body
    assert "invest-content-text-mode-toggle" in upload_body
    assert "onchange=\"switchInvestmentUploadMode(this.checked ? 'text' : 'image')\"" in upload_body
    assert "纯文字生成" in upload_body
    assert "生成', 'createInvestmentContent(true)'" in upload_body
    assert "保存草稿" not in upload_body
    assert "保存并生成" not in upload_body
    assert "investment-panel investment-current-panel" not in current_body
    assert "investment-panel investment-upload-panel" not in upload_body
    assert "renderInvestmentCurrentEffective(data.current_effective, serviceType)" in content_body
    assert "renderInvestmentContentUploadPanel(serviceType)" in content_body
    assert content_body.index("investment-content-top-panel") < content_body.index("investment-content-history-panel")
    assert content_body.index("renderInvestmentCurrentEffective") < content_body.index("renderInvestmentContentUploadPanel")
    assert content_body.index("renderInvestmentContentUploadPanel") < content_body.index("investment-content-history-panel")
    assert "investmentTableWrap" in history_body
    assert "investment-history-table" in history_body
    assert "investment-history-output-preview" in history_body
    assert "const groups = new Map()" not in history_body
    assert "investment-date-group" not in history_body
    assert "content-history-current-date" in history_body
    assert "<th>ID</th><th>服务</th><th>版本</th><th>状态</th><th>模式</th><th>操作人</th><th>生成时间</th><th>原始资料</th><th>生成内容</th><th>输出</th><th>产物</th><th>操作</th>" in history_body
    assert "investment-history-card" not in history_body
    assert "investmentTextButton('刷新'" in history_body
    assert "investmentTextButtonIfCan('content.generate', '生成'" in history_body
    assert "investmentTextButtonIfCan('content.publish', '设为生效'" in history_body
    assert "investmentTextButton('详情'" in history_body
    assert "investmentIconButton(" not in history_body
    assert "investmentIconButtonIfCan(" not in history_body
    assert "record.operator || '-'" not in history_body
    assert "investmentFormatBeijingTime(record.created_at) || '-'" not in history_body
    assert "const warningText = record.status_warning || record.error_message || '';" in history_body
    assert "const warning = warningText ? investmentCompactText(warningText, 80) : '';" in history_body
    assert "investmentCompactText(record.status_warning || record.error_message || '', 80)" not in history_body
    assert "investmentHistoryHoverText(record.source_text, 24)" in history_body
    assert "investmentHistoryHoverText(record.generated_text, 24)" in history_body
    assert "function investmentHistoryHoverText(value, max = 24)" in js
    assert "data-tooltip=\"${escapeHtml(text)}\"" in js
    assert "const artifactFiles = Array.isArray(record.output_artifacts)" in history_body
    assert "const outputImage = investmentContentOutputImage(record);" in history_body
    assert "const artifactCount = artifactFiles.length;" in history_body
    assert "investmentFileLinks(artifactFiles)" in history_body
    assert "record.source_text" in history_body
    assert "record.generated_text" in history_body
    assert "record.output_artifacts" in history_body

    assert ".investment-daily-content-page" in css
    assert "display: flex;" in css
    assert "flex-direction: column;" in css
    assert ".investment-content-top-panel" in css
    assert ".investment-content-top" in css
    assert "grid-template-columns: minmax(420px, 7fr) minmax(360px, 5fr);" in css
    assert "align-items: stretch;" in css
    assert ".investment-content-top-panel .investment-daily-current-panel,\n.investment-content-top-panel .investment-daily-upload-panel" in css
    assert ".investment-content-top > .investment-daily-current-panel,\n.investment-content-top > .investment-daily-upload-panel" in css
    assert "box-shadow: none;" in css
    assert "background: transparent;" in css
    assert ".investment-content-history-panel" in css
    assert ".investment-content-history-body" in css
    assert ".investment-content-history-body > .investment-table-scroll" in css
    assert "--investment-history-header-height: 42px;" in css
    assert "--investment-history-row-height: 74px;" in css
    assert "height: calc(var(--investment-history-header-height) + var(--investment-history-row-height) * 6);" in css
    assert "max-height: calc(var(--investment-history-header-height) + var(--investment-history-row-height) * 6);" in css
    assert ".investment-history-header" in css
    assert ".investment-history-heading-row" in css
    assert ".investment-history-filterbar" in css
    assert ".investment-history-date-field" in css
    assert ".investment-date-control" in css
    assert ".investment-date-control:focus-within" in css
    assert ".investment-date-value-button" in css
    assert ".investment-date-picker-button" in css
    assert ".investment-date-picker-button:hover" in css
    assert ".investment-date-popover" in css
    assert ".investment-date-day.selected" in css
    assert ".investment-date-picker-foot" in css
    assert ".investment-time-control" in css
    assert ".investment-time-popover" in css
    assert ".investment-time-select" in css
    assert ".investment-time-picker-foot" in css
    assert ".investment-history-table" in css
    assert ".investment-history-output-preview" in css
    assert "min-width: 1280px;" in css
    assert ".investment-history-cell-summary" in css
    assert "max-width: 360px;" in css
    assert "white-space: pre-wrap;" in css
    assert ".investment-history-table th:nth-child(12)," in css
    assert "width: 260px;" in css
    assert "width: 56px;" in css
    assert "height: 56px;" in css
    assert "min-height: 0;" in css
    assert "max-height: 100%;" in css
    assert ".investment-history-table .investment-row-actions" in css
    assert "flex-wrap: nowrap;" in css
    assert ".investment-text-action" in css
    assert "white-space: nowrap;" in css
    assert ".investment-history-card" not in css
    assert ".investment-history-main" not in css
    assert ".investment-history-preview" not in css
    assert ".investment-history-text" not in css
    assert "height: auto;" in css
    assert "display: flex;" in css
    assert "flex-direction: column;" in css
    assert "grid-column: 1 / 2;" not in css
    assert "grid-column: 2 / 3;" not in css
    assert ".investment-daily-content-page .investment-current-body" in css
    assert ".investment-current-preview .investment-preview" in css
    assert "width: 100%;" in css
    assert "height: 100%;" in css
    assert "max-height: min(560px, 58vh);" in css
    assert "object-fit: contain;" in css
    assert ".investment-daily-content-page .investment-current-meta" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));" in css
    assert ".investment-daily-content-page .investment-current-meta strong" in css
    assert ".investment-daily-content-page .investment-current-meta .investment-detail-link" in css
    assert "overflow: hidden;" in css
    assert "text-overflow: ellipsis;" in css
    assert "white-space: nowrap;" in css
    assert ".investment-daily-upload-stage" in css
    assert ".investment-upload-mode-bar" in css
    assert "justify-content: flex-end;" in css
    assert ".investment-upload-mode-switch" in css
    assert ".investment-upload-dropzone" in css
    assert "border: 2px dashed #cbd5e1;" in css
    assert "min-height: 260px;" in css
    assert ".investment-upload-dropzone input[type=\"file\"]" in css
    assert "display: none;" in css
    assert ".investment-upload-plus" in css
    assert ".investment-upload-preview" in css
    assert ".investment-upload-thumb" in css
    assert ".investment-upload-thumb img" in css
    assert ".investment-upload-text-mode textarea" in css
    assert "resize: vertical;" in css
    assert ".investment-expires-toggle-row" in css
    assert ".investment-expires-fields.disabled" in css
    assert ".investment-daily-content-page .investment-daily-upload-panel .investment-actions" in css
    assert "display: grid;" in css
    assert "grid-template-columns: 1fr;" in css
    assert ".investment-daily-content-page .investment-daily-upload-panel .investment-btn" in css
    assert "white-space: normal;" in css


def test_daily_content_upload_operator_is_current_admin_without_input_field():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    upload_body = _js_function_body(js, "renderInvestmentContentUploadPanel")
    create_body = _js_function_body(js, "createInvestmentContent")

    assert "function investmentCurrentAdminUsername(" in js
    assert 'id="invest-content-operator"' not in upload_body
    assert "readonly" not in upload_body
    assert "<span>操作人</span>" not in upload_body
    assert "form.append('operator', investmentCurrentAdminUsername());" in create_body
    assert "document.getElementById('invest-content-operator').value || 'admin'" not in create_body


def test_daily_content_upload_supports_image_and_text_generation_modes():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    upload_body = _js_function_body(js, "renderInvestmentContentUploadPanel")
    switch_body = _js_function_body(js, "switchInvestmentUploadMode")
    summary_body = _js_function_body(js, "updateInvestmentUploadFileSummary")
    create_body = _js_function_body(js, "createInvestmentContent")

    assert 'id="invest-content-upload-mode" value="image"' in upload_body
    assert "investment-upload-mode-bar" in upload_body
    assert "investment-upload-image-mode" in upload_body
    assert "investment-upload-text-mode" in upload_body
    assert "点击此区域选择利率/转债资料图片" in upload_body
    assert "window.switchInvestmentUploadMode = switchInvestmentUploadMode;" in js
    assert "window.updateInvestmentUploadFileSummary = updateInvestmentUploadFileSummary;" in js
    assert "window.syncInvestmentDefaultExpiresAt = syncInvestmentDefaultExpiresAt;" in js
    assert "window.changeInvestmentExpiresMode = changeInvestmentExpiresMode;" in js
    assert "window.toggleInvestmentExpiresAt = toggleInvestmentExpiresAt;" in js
    assert "window.investmentToggleTimePicker = investmentToggleTimePicker;" in js
    assert "window.investmentSelectTime = investmentSelectTime;" in js
    assert "const toggle = document.getElementById('invest-content-text-mode-toggle');" in switch_body
    assert "if (toggle) toggle.checked = targetMode === 'text';" in switch_body
    assert "stage.classList.toggle('text-mode', targetMode === 'text');" in switch_body
    assert "stage.classList.toggle('image-mode', targetMode !== 'text');" in switch_body
    assert "files.map(file => file.name).join('、')" in summary_body
    assert "const preview = document.getElementById('invest-content-file-preview');" in summary_body
    assert "files.slice(0, 4).map(file => {" in summary_body
    assert "URL.createObjectURL(file)" in summary_body
    assert "investment-upload-thumb" in summary_body
    assert "const uploadMode = document.getElementById('invest-content-upload-mode')?.value || 'image';" in create_body
    assert "await investmentShouldAutoEffectiveAfterGenerate(serviceType)" in create_body
    assert "if (autoEffective === null) return;" in create_body
    assert "document.getElementById('invest-content-source-text')?.value || ''" in create_body
    assert "document.getElementById('invest-content-supplement-text')?.value || ''" in create_body
    assert "form.append('source_text', sourceText);" in create_body
    assert "form.append('expires_at', investmentContentExpiresAtValue());" in create_body
    assert "form.append('auto_effective_after_generate', autoEffective ? '1' : '0');" in create_body
    assert "joke_text" not in create_body


def test_daily_content_upload_confirms_auto_effective_when_today_has_no_record():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    helper_body = _js_function_body(js, "investmentShouldAutoEffectiveAfterGenerate")
    create_body = _js_function_body(js, "createInvestmentContent")

    assert "function investmentShouldAutoEffectiveAfterGenerate(serviceType)" in js
    assert "effective_date=${encodeURIComponent(investmentTodayDate())}" in helper_body
    assert "response.contents" in helper_body
    assert "records.length > 0" in helper_body
    assert "window.confirm" in helper_body
    assert "作为 ${investmentTodayDate()} 生效${label}图" in helper_body
    assert "return confirmed ? true : null;" in helper_body
    assert "await investmentShouldAutoEffectiveAfterGenerate(serviceType)" in create_body


def test_daily_content_upload_expires_at_defaults_to_next_beijing_midnight():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    add_days_body = _js_function_body(js, "investmentAddDays")
    default_body = _js_function_body(js, "investmentDefaultExpiresDate")
    sync_body = _js_function_body(js, "syncInvestmentDefaultExpiresAt")
    toggle_body = _js_function_body(js, "toggleInvestmentExpiresAt")
    value_body = _js_function_body(js, "investmentContentExpiresAtValue")
    time_body = _js_function_body(js, "investmentRenderTimeControl")
    detail_body = _js_function_body(js, "showInvestmentContentDetail")
    current_body = _js_function_body(js, "renderInvestmentCurrentEffective")

    assert "new Date(Date.UTC(parts.year, parts.month - 1, parts.day + Number(days || 0)))" in add_days_body
    assert "return investmentAddDays(effectiveDate, 1);" in default_body
    assert "if (!enabled) return;" in sync_body
    assert "investmentSetDatePickerValue('invest-content-expires-date', investmentDefaultExpiresDate());" in sync_body
    assert "investmentSetTimePickerValue('invest-content-expires-time', '00:00');" in sync_body
    assert "const disabled = !enabled;" in toggle_body
    assert "fields?.classList.toggle('hidden', disabled);" in toggle_body
    assert "hint.textContent = enabled ? '指定失效时间' : '不指定失效时间';" in toggle_body
    assert "if (!enabled) return '';" in value_body
    assert "return `${dateValue}T${timeValue}`;" in value_body
    assert 'type="hidden"' in time_body
    assert "investment-time-popover hidden" in time_body
    assert "investmentFormatBeijingTime(record.expires_at) || '不失效'" in detail_body
    assert "investmentFormatBeijingTime(record?.expires_at) || '不失效'" in current_body


def test_daily_content_effective_action_refreshes_current_preview():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    effective_body = _js_function_body(js, "effectiveInvestmentContent")

    assert "await renderInvestmentContent(targetServiceType, {effective_date: investmentContentHistoryEffectiveDate(targetServiceType)})" in effective_body
    assert "await refreshInvestmentContentRecords(targetServiceType);" not in effective_body


def test_investment_console_hides_actions_by_admin_role():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "let currentInvestmentAdmin = null;" in js
    assert "function investmentCan(" in js
    assert "async function loadInvestmentAdminSession(" in js
    assert "/api/investment/auth/me" in js
    assert "investmentButtonIfCan('customers.write'" in js
    assert "investmentButtonIfCan('customers.enable'" in js
    assert "investmentButtonIfCan('customers.import'" in js
    assert "investmentButtonIfCan('customers.export'" in js
    assert "investmentButtonIfCan('content.upload'" in js
    assert "investmentButtonIfCan('audits.read', 'fa-clock-rotate-left', '操作流水'" in js
    assert "investmentIconButtonIfCan('cache.write'" in js
    assert "investmentCanView(" in js


def test_investment_config_page_loads_sections_by_permission():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "'invest-config': ['config.read', 'stocks.read']" in js
    assert "'invest-skills': 'skills.read'" in js
    assert "router.enable_web_open_chat" in js
    assert "Web 普通开放聊天" in js
    assert "function investmentCanEditConfig(" in js
    assert "investmentCanEditConfig(key)" in js
    assert "const canReadConfig = investmentCan('config.read');" in js
    assert "const canReadStocks = investmentCan('stocks.read');" in js
    assert "canReadConfig ? investmentFetchJson('/api/investment/config')" in js
    assert "canReadStocks ? investmentFetchJson('/api/investment/stocks?limit=5')" in js
    assert "investmentStockTools(stockData.stats || {}, configs, canReadConfig, canReadStocks)" in js


def test_investment_layout_separates_table_settings_and_card_styles():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    shell_body = _js_function_body(js, "renderInvestmentConfigShell")
    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")

    assert "investment-settings-page" in shell_body
    assert "investment-settings-panel" in stock_panel_body
    assert ".investment-workbench > .investment-table-panel" in css
    assert ".investment-workbench > .investment-table-panel {\n    grid-column: 1 / -1;" in css
    assert ".investment-workbench > .investment-panel {\n    grid-column: span 6;" in css
    assert "box-shadow: 0 8px 30px -6px rgba(15, 23, 42, 0.10)" in css
    assert "padding: 20px;" in css
    assert ".investment-settings-page .investment-panel" in css


def test_investment_config_uses_dedicated_layout_instead_of_shared_workbench():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    shell_body = _js_function_body(js, "renderInvestmentConfigShell")
    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    reply_panel_body = _js_function_body(js, "renderInvestmentConfigReplyTextsPanel")
    generation_body = _js_function_body(js, "renderInvestmentConfigGenerationPanel")
    web_chat_body = _js_function_body(js, "renderInvestmentConfigWebChatPanel")

    combined_panels = "\n".join([stock_panel_body, reply_panel_body, generation_body, web_chat_body])
    assert "investment-config-grid" in combined_panels
    assert 'class="investment-workbench ' not in combined_panels
    assert ".investment-config-grid" in css
    assert ".investment-config-grid > .investment-panel" in css
    assert ".investment-config-grid > .investment-workbench-full" in css
    assert "#investment-config-panel-content" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "id=\"investment-config-panel-content\"" in shell_body
    assert "investment-config-summary" not in shell_body
    assert "investment-config-nav" in shell_body
    assert '<section class="investment-config-summary">' not in shell_body
    assert "investment-panel investment-workbench-full" not in shell_body
    assert "investment-tabs investment-config-tabs" not in shell_body
    assert ".investment-config-nav" in css
    assert ".investment-config-nav {\n    display: flex;" in css
    assert "position: sticky;" not in css[css.index(".investment-config-nav {"):css.index(".investment-config-tab {")]


def test_investment_config_inline_handlers_are_not_html_escaped():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    config_field_body = _js_function_body(js, "renderInvestmentConfigField")

    assert "const saveHandler = `saveInvestmentConfigKey(${keyArg}, ${typeArg})`;" in config_field_body
    assert "const dirtyHandler = `markInvestmentConfigDirty(${keyArg})`;" in config_field_body
    assert "escapeHtml(`saveInvestmentConfigKey" not in config_field_body
    assert "escapeHtml(`markInvestmentConfigDirty" not in config_field_body


def test_investment_config_page_uses_task_based_tabs():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    config_body = _js_function_body(js, "renderInvestmentConfig")
    shell_body = _js_function_body(js, "renderInvestmentConfigShell")
    stock_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    generation_body = _js_function_body(js, "renderInvestmentConfigGenerationPanel")

    assert "let currentInvestmentConfigPanel = 'stock-data';" in js
    assert "function switchInvestmentConfigPanel(" in js
    assert "renderInvestmentConfigShell(data, stockData)" in config_body
    assert "investment-config-nav" in shell_body
    assert "investment-config-tab" in shell_body
    assert "function investmentConfigTabDefinitions(" in js
    assert "key: 'stock-data'" in js
    assert "key: 'reply-texts'" in js
    assert "key: 'generation'" in js
    assert "key: 'web-chat'" in js
    assert "switchInvestmentConfigPanel('${escapeHtml(tab.key)}')" in shell_body
    assert "股票数据" in js
    assert "公众号回复词" in js
    assert "业务生成配置" in js
    assert "后台 Web 对话" in js

    assert "renderInvestmentConfigGroupByTitle('股票字典'" not in stock_body
    assert "investmentStockTools(stockData.stats || {}, configs, canReadConfig, canReadStocks)" in stock_body
    assert "renderInvestmentConfigGroupByTitle('技术分析参数', configs, {sectionClass: 'investment-config-section'})" in generation_body
    assert "renderInvestmentConfigGroupByTitle('图片生成模板', configs, {sectionClass: 'investment-config-section'})" in generation_body
    assert "renderInvestmentConfigGroupByTitle('存储与提示词', configs, {sectionClass: 'investment-config-section'})" in generation_body
    assert ".investment-config-page" in css
    assert ".investment-config-nav" in css
    assert ".investment-config-tab" in css
    assert "flex-wrap: wrap;" in css


def test_investment_config_subpages_use_aligned_section_layouts():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    stock_body = _js_function_body(js, "investmentStockTools")
    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    generation_body = _js_function_body(js, "renderInvestmentConfigGenerationPanel")
    web_chat_body = _js_function_body(js, "renderInvestmentConfigWebChatPanel")

    assert "investment-config-panel" in stock_panel_body
    assert "investment-stock-data-panel" in stock_panel_body
    assert "investment-config-section" in stock_body
    assert "investment-config-panel" in generation_body
    assert "investment-config-section" in generation_body
    assert "investment-config-panel" in web_chat_body
    assert "investment-config-section" in web_chat_body

    assert "investment-config-toolbar investment-stock-toolbar" in stock_body
    assert "investment-config-tool" in stock_body
    assert "investment-stock-refresh-tool" in stock_body
    assert "investment-stock-query-tool" in stock_body
    assert stock_body.count("investment-inline-form investment-stock-actions") == 0
    assert "investment-panel-heading" in stock_body
    assert "investment-subtitle" in stock_body

    assert ".investment-config-panel" in css
    assert ".investment-config-section" in css
    assert ".investment-config-toolbar" in css
    assert ".investment-config-tool" in css
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert "align-items: end;" in css
    assert "align-self: end;" in css


def test_investment_stock_data_page_combines_dictionary_config_and_tools():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    stock_tools_body = _js_function_body(js, "investmentStockTools")

    assert "renderInvestmentConfigGroupByTitle('股票字典'" not in stock_panel_body
    assert "investmentStockTools(stockData.stats || {}, configs, canReadConfig, canReadStocks)" in stock_panel_body
    assert "investment-stock-data-panel" in stock_panel_body
    assert "investment-stock-data-card" in stock_tools_body
    assert "renderInvestmentConfigField('tushare.token', 'Tushare Token', 'text', configs['tushare.token'])" in stock_tools_body
    assert "股票数据" in stock_tools_body
    assert "股票字典维护" not in stock_tools_body


def test_investment_config_page_renders_reply_text_section():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    reply_panel_body = _js_function_body(js, "renderInvestmentConfigReplyTextsPanel")
    groups_body = _js_function_body(js, "renderInvestmentReplyConfigGroups")

    assert "renderInvestmentReplyConfigGroups(data.reply_texts || {}, configs)" in reply_panel_body
    assert "const groups = replyTexts.groups || [];" in groups_body
    assert "const definitions = replyTexts.definitions || {};" in groups_body
    assert "group.keys || []" in groups_body
    assert "renderInvestmentReplyConfigField(key, definitions[key] || {}, configs[key])" in groups_body
    assert "公众号回复词" in js
    assert "INVEST_REPLY_CONFIG_REFERENCE_KEYS" not in js


def test_investment_reply_config_fields_show_descriptions_and_use_textareas():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    reply_field_body = _js_function_body(js, "renderInvestmentReplyConfigField")
    config_field_body = _js_function_body(js, "renderInvestmentConfigField")

    assert "function renderInvestmentReplyConfigField(" in js
    assert "investment-config-description" in js
    assert "renderInvestmentConfigField(key, label, 'textarea', value, {showSaveButton: true})" in reply_field_body
    assert "escapeHtml(description)" in reply_field_body
    assert "escapeHtml(label)" in config_field_body
    assert "investmentJsString(key)" in config_field_body
    assert "const saveHandler = `saveInvestmentConfigKey(${keyArg}, ${typeArg})`;" in config_field_body
    assert "const dirtyHandler = `markInvestmentConfigDirty(${keyArg})`;" in config_field_body
    assert "saveInvestmentConfigKey(${keyArg}, ${typeArg})" in config_field_body
    assert "markInvestmentConfigDirty(${keyArg})" in config_field_body
    assert ".investment-config-description" in css


def test_investment_reply_config_fields_show_save_button_by_default():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    reply_field_body = _js_function_body(js, "renderInvestmentReplyConfigField")
    config_field_body = _js_function_body(js, "renderInvestmentConfigField")

    assert "renderInvestmentConfigField(key, label, 'textarea', value, {showSaveButton: true})" in reply_field_body
    assert "const showSaveButton = options.showSaveButton === true;" in config_field_body
    assert "investment-config-save${showSaveButton ? '' : ' hidden'}" in config_field_body


def test_investment_content_and_records_ui_respect_cache_and_export_permissions():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "if (viewId === 'invest-content') return renderInvestmentGeneratedContent();" in js
    assert "/api/investment/cache" in js
    assert "async function loadInvestmentGeneratedContent()" in js
    assert "investmentButtonIfCan('records.export', 'fa-file-export', '导出', 'openInvestmentRequestExportDialog()'" in js


def test_investment_records_filters_and_export_share_toolbar_without_title_topbar():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    shell_body = _js_function_body(js, "renderInvestmentRecordsShell")
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")

    assert "investment-records-topbar" not in shell_body
    assert "investment-panel-title\"><i class=\"fas fa-table-list\"></i><span>业务记录</span>" not in shell_body
    assert "investmentRecordsState.tab === 'requests' ? renderInvestmentRequestExportPanel()" not in shell_body
    assert "investment-records-export\">" not in shell_body
    assert "investment-records-export-fields" not in shell_body
    assert "investment-records-toolbar" in filters_body
    assert "investment-records-filter-grid" in filters_body
    assert "investment-records-filter-actions" in filters_body
    assert "openInvestmentRequestExportDialog()" in filters_body
    assert ".investment-records-toolbar" in css
    assert ".investment-records-topbar" not in css
    assert ".investment-records-filter-grid {\n    display: grid;" in css
    assert "grid-template-columns: minmax(240px, 2fr) repeat(4, minmax(132px, 1fr));" in css
    assert "@media (max-width: 1024px)" in css
    assert ".investment-records-filter-grid {\n        grid-template-columns: repeat(2, minmax(0, 1fr));" in css


def test_investment_request_export_dialog_is_mode_based_and_prefills_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    dialog_body = _js_function_body(js, "openInvestmentRequestExportDialog")
    panel_body = _js_function_body(js, "renderInvestmentRequestExportDialogBody")
    assert "showInvestmentModal('导出业务记录'" in dialog_body
    assert "investmentRecordsSetFilterValues('requests', {resetPage: false})" in dialog_body
    assert "initInvestmentDropdowns(document.getElementById('investment-modal-body'))" in dialog_body
    assert "公众号请求导出" in panel_body
    assert "导出当前筛选" in panel_body
    assert "全量导出" in panel_body
    assert "按时间范围导出" in panel_body
    assert "按月度导出" in panel_body
    assert "按季度导出" in panel_body
    assert "investment-request-export-fields" in panel_body
    assert "investment-request-export-dialog" in panel_body
    assert "investment-request-export-layout" in panel_body
    assert "investment-request-export-mode-grid" in panel_body
    assert "investment-request-export-form" in panel_body
    assert "investment-request-export-footer" in panel_body
    assert "renderInvestmentRequestExportCurrentSummary(values)" in panel_body
    assert "investmentRequestExportMonthOptions()" in panel_body
    assert "type=\"month\"" not in panel_body
    assert "导出会应用上方客户/输入/错误、服务、状态和日期筛选。" in panel_body
    assert "可按下方条件缩小范围。" in panel_body
    assert "不限制日期，按下方条件导出全部请求记录。" not in panel_body
    assert "投资服务" in panel_body
    assert "客户/机构" in panel_body
    assert "Excel" in panel_body

    current_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    summary_body = _js_function_body(js, "renderInvestmentRequestExportCurrentSummary")
    month_options_body = _js_function_body(js, "investmentRequestExportMonthOptions")
    assert "investmentRecordsQueryParams('requests')" in current_body
    assert "params.delete('page')" in current_body
    assert "params.delete('page_size')" in current_body
    assert "请选择导出开始和结束日期" in range_body
    assert "当前筛选条件" in summary_body
    assert "未设置筛选，将导出全部请求记录" in summary_body
    assert "investmentServiceLabel(filters.service_type)" in summary_body
    assert "investmentStatusLabel(filters.status)" in summary_body
    assert "`${value}（本月）`" in month_options_body
    assert "本月，最近18个月" not in month_options_body
    assert "function exportInvestmentRequestRecordsFull()" in js
    assert ".investment-request-export-dialog" in css
    assert ".investment-request-export-layout" in css
    assert "grid-template-columns: minmax(190px, 0.55fr) minmax(0, 1.45fr);" in css
    assert ".investment-request-export-mode-grid" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr));" in css
    assert ".investment-request-export-form" in css
    assert ".investment-request-export-fields > .investment-request-export-note" in css
    assert "grid-column: 1 / -1;" in css
    assert ".investment-request-export-footer" in css


def test_investment_request_export_exposes_unauthorized_and_customer_filter():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    panel_body = _js_function_body(js, "renderInvestmentRequestExportDialogBody")
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    month_body = _js_function_body(js, "exportInvestmentRequestRecordsByMonth")
    quarter_body = _js_function_body(js, "exportInvestmentRequestRecordsByQuarter")
    current_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")
    full_body = _js_function_body(js, "exportInvestmentRequestRecordsFull")

    assert "unauthorized_request: '无权限请求'" in js
    assert "['unauthorized_request', '无权限请求']" in filters_body
    assert "investmentDropdown('invest-export-service-type'" in panel_body
    assert "['unauthorized_request', '无权限请求']" in panel_body
    assert "id=\"invest-export-customer\"" in panel_body
    assert "客户/机构/OpenID/手机号" in panel_body
    assert "function investmentExportCustomer()" in js
    assert "params.set('customer', customer)" in current_body
    assert "customer: investmentExportCustomer()" in full_body
    assert "customer: investmentExportCustomer()" in range_body
    assert "customer: investmentExportCustomer()" in month_body
    assert "customer: investmentExportCustomer()" in quarter_body


def test_investment_records_default_to_beijing_today_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_start = js.index("let investmentRecordsState =")
    state_end = js.index("const INVEST_VIEW_PERMISSIONS")
    state_body = js[state_start:state_end]
    default_body = _js_function_body(js, "investmentRecordsDefaultFilters")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")

    assert "requests: {page: '1', page_size: '80', start_date: investmentTodayDate(), end_date: investmentTodayDate()}" in state_body
    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: investmentTodayDate()}" in state_body
    assert "audits: {page: '1', page_size: '80', start_date: investmentTodayDate(), end_date: investmentTodayDate()}" in state_body
    assert "start_date: investmentTodayDate()" in default_body
    assert "end_date: investmentTodayDate()" in default_body
    assert "market_date: investmentTodayDate()" in default_body
    assert "data.market_dates[0]" not in load_body
    assert "timeZone: 'Asia/Shanghai'" in _js_function_body(js, "investmentTodayDate")


def test_investment_cache_empty_date_falls_back_to_today_before_loading():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    apply_body = _js_function_body(js, "applyInvestmentCacheDate")
    normalize_body = _js_function_body(js, "investmentNormalizeCacheDateFilters")
    assert "investmentTodayDate()" in normalize_body
    assert "await loadInvestmentGeneratedContent()" in apply_body


def test_investment_records_page_uses_tab_workspace_without_side_drawer():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "let investmentRecordsState =" in js
    assert "function switchInvestmentRecordsTab(" in js
    assert "function renderInvestmentRecordsShell(" in js
    assert "function openInvestmentRecordDrawer(" in js
    assert "investment-records-workspace" in js
    assert "investment-records-board" in js
    assert "investment-records-tabs" in js
    assert 'id="investment-records-drawer"' not in js
    assert "选择记录查看详情" not in _js_function_body(js, "renderInvestmentRecordsShell")
    assert "选择内容查看详情" not in _js_function_body(js, "renderInvestmentGeneratedContent")
    assert ".investment-records-workspace" in css
    assert ".investment-records-board" in css
    assert "border: 1px solid #d8e1ee;" in css
    assert ".investment-records-tabs" in css
    assert ".investment-records-main" in css
    assert ".investment-content-shell" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);" not in css
    assert "grid-template-columns: minmax(0, 1fr);" in css


def test_investment_records_page_uses_human_filters_customer_display_and_compact_tables():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "function investmentRecordClamp(" in js
    assert "function investmentRecordFileSummary(" in js
    assert "field('keyword', '客户/输入/错误')" in js
    assert "select('status', '状态'" in js
    assert "select('service_type', '服务'" in js
    assert "customer_display" in js
    request_table = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    content_table = _js_function_body(js, "renderInvestmentContentRecordsTable")
    cache_table = _js_function_body(js, "renderInvestmentCacheCompactRows")
    audit_table = _js_function_body(js, "renderInvestmentOperationAuditsTable")
    assert "record.customer_display" in request_table
    assert "<th>ID</th>" not in request_table
    assert "renderInvestmentFilePreview(" not in request_table
    assert "renderInvestmentFilePreview(" not in content_table
    assert "renderInvestmentFilePreview(" not in cache_table
    assert "renderInvestmentFilePreview(" not in audit_table
    assert "investmentRecordClamp(" in request_table
    assert "investmentRecordClamp(" in audit_table
    assert ".investment-records-table-shell" in css
    assert "--investment-records-list-max-height: min(620px, calc(100vh - 300px));" in css
    assert ".investment-generated-content" in css
    assert "height: var(--investment-records-list-max-height);" in css
    assert ".investment-record-clamp" in css
    assert "-webkit-line-clamp" in css
    assert ".investment-records-list {\n    height: var(--investment-records-list-max-height);" in css
    assert ".investment-records-table-shell {\n    height: 100%;" in css
    assert "field('keyword', '关键字')" in js
    assert "field('action', '动作')" in js
    assert "field('operator', '操作人')" in js


def test_investment_content_page_uses_date_grouped_category_view():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentDailyGeneratedContent(" in js
    assert "function renderInvestmentCacheCategory(" in js
    assert "function selectInvestmentCacheCategory(" in js
    assert "function backInvestmentCacheCategoryMenu(" in js
    assert "technical_analysis" in js
    assert "rate" in js
    assert "convertible_bond" in js
    assert "async function renderInvestmentGeneratedContent(" in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    cache_home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    category_cards_body = _js_function_body(js, "renderInvestmentGeneratedCategoryCards")
    assert "investment-generated-content-home" in cache_home_body
    assert "investment-generated-content-entry" in category_cards_body
    assert "['technical_analysis', 'rate', 'convertible_bond']" in cache_body
    assert "investment-records-cache-layout" not in js
    assert "investment-records-date-list" not in js


def test_investment_content_page_defaults_to_history_overview():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    load_body = _js_function_body(js, "loadInvestmentGeneratedContent")
    apply_body = _js_function_body(js, "applyInvestmentCacheDate")

    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: investmentTodayDate()}" in js
    assert "const dateRange = investmentNormalizeCacheDateFilters();" in cache_body
    assert "const selectedDate = dateRange.marketDate;" in cache_body
    assert "const visibleEntries = selectedDate ? values.filter" in cache_body
    assert "haystack.includes(keyword)" not in cache_body
    assert "renderInvestmentGeneratedContentHome(categories, visibleEntries)" in cache_body
    assert "selectedCategory ? renderInvestmentRecordsPagination('cache') : ''" in cache_body
    assert "renderInvestmentDailyGeneratedContent(investmentRecordsState.data.cache)}${renderInvestmentRecordsPagination('cache')" not in load_body
    assert "investment-generated-category-strip" in home_body
    assert "investment-generated-table-panel" not in home_body
    assert "renderInvestmentGeneratedCategoryCards(categories, entries)" in home_body
    assert "renderInvestmentGeneratedCategoryCards(categories, entriesForDate)" not in home_body
    assert "investment-generated-date-section" not in home_body
    assert "investmentGroupCacheEntriesByDate(entries)" not in home_body
    assert "暂无历史内容" not in home_body
    assert "当前日期" in cache_body
    assert "investmentRenderDateControl('investment-records-filter-market_date'" in cache_body
    assert "placeholder: '当前日期'" in cache_body
    assert "investmentRecordsState.filters.cache.period_mode = investmentCachePeriodMode();" in apply_body
    assert "investmentRecordsState.filters.cache.start_date = range.startDate;" in apply_body
    assert "query.delete('market_date')" in load_body


def test_investment_content_page_removes_redundant_topbar_and_uses_compact_history_layout():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderInvestmentGeneratedContent")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    rows_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    category_body = _js_function_body(js, "renderInvestmentCacheCategory")

    assert "investment-content-workspace" in render_body
    assert "investment-records-topbar" not in render_body
    assert "集中查看生成后的图片、文档和缓存产物" not in render_body
    assert "investment-content-list" in render_body
    assert "investment-generated-content-title" in cache_body
    assert "investment-generated-history-empty" not in home_body
    assert "暂无历史内容" not in home_body
    assert "investment-generated-history-empty" in category_body
    assert "暂无历史内容" in category_body
    assert ".investment-content-workspace" in css
    assert ".investment-content-shell" in css
    assert ".investment-content-list" in css
    assert ".investment-generated-content-toolbar" in css
    assert "min-height: 48px;" in css
    assert ".investment-generated-content-title" in css
    assert ".investment-generated-history-empty" in css


def test_daily_content_history_panel_does_not_overlap_top_cards():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert ".investment-daily-content-page {\n    display: flex;" in css
    assert ".investment-content-top-panel" in css
    assert ".investment-daily-content-page > .investment-content-history-panel" in css
    assert "width: 100%;" in css
    assert "position: relative;" in css
    assert "z-index: 0;" in css



def test_investment_generated_content_page_avoids_duplicate_date_controls_and_wide_three_column_lists():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    records_shell = _js_function_body(js, "renderInvestmentRecordsShell")
    assert "生成内容" not in records_shell
    assert "renderInvestmentRecordsTabButton('cache'" not in records_shell
    assert "当日生成" not in js
    assert "当日有关生成内容" not in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    rows_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    assert cache_body.count("investment-records-filter-market_date") == 1
    assert "investment-generated-content-toolbar" in cache_body
    assert "investment-cache-category-grid" not in cache_body
    assert '<span>日期范围</span>' in cache_body
    assert "investment-content-period-mode" in cache_body
    assert "investment-content-period-value" in cache_body
    assert "investmentNormalizeCacheDateFilters()" in cache_body
    assert "investment-content-filter-keyword" in cache_body
    assert "investmentCacheKeyword()" in cache_body
    assert "entry.normalized_target" in rows_body
    assert "entry.output_files" in _js_function_body(js, "investmentGeneratedOutputState")
    assert "investment-generated-library" in home_body
    assert "investment-generated-category-strip" in home_body
    assert "investment-generated-table-panel" not in home_body
    assert "investment-generated-date-section" not in home_body
    assert "investment-generated-content-detail" in css
    assert "investment-generated-content-entries" in css
    assert ".investment-generated-content-home {\n    display: flex;" in css
    assert "border: 1px solid #e2e8f0;" in css
    assert ".investment-generated-content-entries {\n    display: grid;\n    align-content: start;\n    min-height: 0;" in css
    assert "min-height: 48px;" in css
    assert "padding: 6px 10px;" in css
    assert ".investment-generated-content-toolbar {\n    width: 100%;" in css
    assert "line-height: 40px;" in css
    assert "height: 40px;" in css
    assert "min-height: 360px;" in css
    assert ".investment-generated-category-strip {\n    display: flex;" in css
    assert "min-height: min(520px, calc(100vh - 260px));" in css
    assert ".investment-generated-content-home {\n    display: flex;" in css
    assert "align-content: flex-start;" in css
    assert "justify-content: flex-start;" in css
    assert "overflow-y: auto;" in css
    assert "flex: 1 1 auto;" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));" not in css
    assert "width: 168px;" in css
    assert "height: 164px;" in css
    assert "overflow: hidden;" in css
    assert "grid-template-columns: 1fr;" in css
    assert "justify-items: center;" in css
    assert ".investment-generated-entry-meta {\n    display: none;" in css
    assert "minmax(120px, auto)" not in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" not in css
    assert "grid-template-columns: repeat(3, minmax(180px, 1fr));" not in css


def test_investment_generated_content_page_uses_file_explorer_layout_and_range_query():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderInvestmentGeneratedContent")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    cards_body = _js_function_body(js, "renderInvestmentGeneratedCategoryCards")
    rows_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    actions_body = _js_function_body(js, "investmentGeneratedEntryActions")
    load_body = _js_function_body(js, "loadInvestmentGeneratedContent")
    normalize_body = _js_function_body(js, "investmentNormalizeCacheDateFilters")

    assert "investment-content-workspace" in render_body
    assert "investment-content-shell" in render_body
    assert "investment-records-main" not in render_body
    assert "investment-generated-library" in _js_function_body(js, "renderInvestmentGeneratedContentHome")
    assert "investment-generated-category-strip" in _js_function_body(js, "renderInvestmentGeneratedContentHome")
    assert "investment-generated-table-panel" not in _js_function_body(js, "renderInvestmentGeneratedContentHome")
    assert "investment-generated-date-section" not in _js_function_body(js, "renderInvestmentGeneratedContentHome")
    assert "'investment-generated-content-home': ''" in js
    assert "'investment-generated-content-entry': ''" in js
    assert "'investment-generated-content-home': 'grid grid-cols-1 md:grid-cols-3 gap-3'" not in js
    assert "investment-generated-limit" not in cards_body
    assert "investmentGeneratedCategoryLimit(serviceType)" not in cards_body
    assert "分类上限" not in cards_body
    assert "条有效" not in cards_body
    assert "investmentGeneratedEntryIsActive(entry)).length" not in cards_body
    assert "invalidated: '已失效'" in js
    assert "status === 'invalidated'" in _js_function_body(js, "investmentStatusClass")
    assert "<span>产物</span>" in rows_body
    assert "<span>操作</span>" in rows_body
    assert "investmentGeneratedEntryActions(entry)" in rows_body
    assert "investmentTextButtonIfCan('cache.write', '失效'" in actions_body
    assert "query.delete('market_date')" in load_body
    assert "query.set('start_date', range.startDate)" in load_body
    assert "query.set('end_date', range.endDate)" in load_body
    assert "periodMode === 'month'" in normalize_body
    assert "periodMode === 'year'" in normalize_body
    assert ".investment-content-workspace {\n    width: 100%;" in css
    assert ".investment-content-shell {\n    width: 100%;" in css
    assert ".investment-generated-library {\n    display: flex;" in css
    assert ".investment-generated-category-strip" in css
    assert ".investment-generated-table-panel" not in css
    assert ".investment-generated-date-section" not in css
    assert ".investment-generated-limit" not in css
    assert "@media (max-width: 900px)" in css


def test_investment_generated_content_filters_use_month_and_year_dropdowns_with_delayed_refresh():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    normalize_body = _js_function_body(js, "investmentNormalizeCacheDateFilters")
    sync_body = _js_function_body(js, "syncInvestmentCachePeriodMode")
    schedule_body = _js_function_body(js, "scheduleInvestmentCacheFilterRefresh")
    select_body = _js_function_body(js, "selectInvestmentCacheCategory")
    value_control_body = _js_function_body(js, "renderInvestmentGeneratedPeriodValueControl")

    assert "investmentChangeCachePeriodMode(value)" in cache_body
    assert "renderInvestmentGeneratedPeriodValueControl(dateRange.mode, marketDates, values)" in cache_body
    assert "investmentGeneratedPeriodOptions(normalized, marketDates, entries)" in value_control_body
    assert "investmentDropdown('investment-content-period-value'" in value_control_body
    assert 'type="text" value="${escapeHtml(investmentCachePeriodValue())}"' not in cache_body
    assert "function investmentGeneratedPeriodOptions(" in js
    assert "function investmentChangeCachePeriodMode(" in js
    assert "function renderInvestmentGeneratedPeriodValueControl(" in js
    assert "function scheduleInvestmentCacheFilterRefresh(" in js
    assert "clearTimeout(investmentCacheFilterRefreshTimer)" in schedule_body
    assert "setTimeout(() => {" in schedule_body
    assert "applyInvestmentCacheDate()" in schedule_body
    assert "investmentGeneratedDefaultPeriodValue(normalized)" in sync_body
    assert "investmentSetDatePickerValue('investment-records-filter-market_date', investmentTodayDate())" in sync_body
    assert "valueField.innerHTML = renderInvestmentGeneratedPeriodValueControl(" in sync_body
    assert "initInvestmentDropdowns(valueField)" in sync_body
    assert "investmentCachePeriodValue().trim()" in normalize_body
    assert "scheduleInvestmentCacheFilterRefresh()" in select_body
    assert "await loadInvestmentGeneratedContent()" not in select_body


def test_investment_generated_content_category_detail_is_compact():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")
    category_body = _js_function_body(js, "renderInvestmentCacheCategory")
    row_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    actions_body = _js_function_body(js, "investmentGeneratedEntryActions")
    assert "investment-generated-content-detail-count" in detail_body
    assert "investment-cache-category-title" not in category_body
    assert "renderInvestmentCacheCompactRows(entries)" in category_body
    assert "investment-generated-content-header" in row_body
    assert "<span>标的</span>" in row_body
    assert "align-content: start;" in css
    assert ".investment-generated-content-header,\n.investment-generated-content-row" in css
    assert "min-height: 44px;" in css
    assert "padding: 0 10px;" in css
    assert "grid-template-columns: minmax(180px, 1.45fr) 84px 82px 156px 110px 86px;" in css
    assert "grid-column: 1 / 6;" in css
    assert "investmentGeneratedEntryActions(entry)" in row_body
    assert "investmentTextButtonIfCan('cache.write'" in actions_body


def test_investment_generated_content_rows_treat_daily_content_as_content_records():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    row_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    assert "investmentGeneratedRecordDrawerType(entry)" in row_body
    assert "investmentGeneratedEntryActions(entry)" in row_body
    assert "source_type === 'cache'" in js
    assert "source_type === 'content'" in js
    assert "invalidateInvestmentCache" in _js_function_body(js, "investmentGeneratedEntryActions")
    assert "openInvestmentRecordDrawer('content'" not in row_body
    assert "const drawerType = investmentGeneratedRecordDrawerType(entry);" in row_body
    assert "openInvestmentRecordDrawer('${drawerType}'" in row_body


def test_investment_generated_content_drawer_hides_low_value_long_cache_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "选择记录查看详情" in js
    assert "选择一条记录查看完整详情" not in js
    drawer_body = _js_function_body(js, "renderInvestmentCacheDrawer")
    assert "缓存 Key" not in drawer_body
    assert "缓存字段" not in drawer_body
    assert "record.cache_key" not in drawer_body
    assert "record.output_files" not in drawer_body
    assert "生成内容详情" in js


def test_investment_content_drawer_shows_source_images_like_output_image():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    drawer_body = _js_function_body(js, "renderInvestmentContentDrawer")

    assert "输入图片" in drawer_body
    assert "renderInvestmentSourcePreviews(investmentContentSourceFiles(record))" in drawer_body
    assert "输出图片" in drawer_body
    assert "investmentContentOutputImage(record)" in drawer_body
    assert drawer_body.index("输入图片") < drawer_body.index("输出图片")


def test_investment_file_links_prefer_file_id_urls_over_absolute_paths():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    file_url_body = _js_function_body(js, "investmentFileUrl")
    links_body = _js_function_body(js, "investmentFileLinks")

    assert "if (file.file_url) return file.file_url;" in file_url_body
    assert "file.file_id || file.id" in file_url_body
    assert "`/api/file?id=${encodeURIComponent(file.file_id || file.id)}`" in file_url_body
    assert "investmentFileUrl(file)" in links_body
    assert "investmentImageUrl(path)" not in links_body


def test_investment_request_drawer_keeps_error_details_and_audit_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    request_table = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    drawer_body = _js_function_body(js, "renderInvestmentRequestDrawer")

    assert "function investmentDeliveryStatusClass(" in js
    assert "record.delivery_status" in request_table
    assert "<th>生成</th><th>交付</th><th>提示摘要</th>" in request_table
    assert "<th>时间</th><th>详情</th>" in request_table
    assert "<th>北京时间</th>" not in request_table
    assert "<th>操作</th>" not in request_table
    assert "record.user_prompt || record.delivery_status || '正常'), 1, 54)" in request_table
    assert "record.user_prompt || record.delivery_status || '正常'), 2, 54)" not in request_table
    assert "record.status_warning === '未完成/可能超时' ? 'generating' : record.status" in request_table
    assert "record.user_prompt || record.delivery_status || '正常'" in request_table
    assert "record.delivery_detail || record.error_message" not in request_table
    assert "生成状态" in drawer_body
    assert "交付状态" in drawer_body
    assert "用户提示" in drawer_body
    assert "错误/警告详情" in drawer_body
    assert "审计字段" in drawer_body
    assert "record.normalized_target" in drawer_body
    assert "record.cache_key" in drawer_body
    assert "输出文件" in drawer_body
    assert "产物审计" not in drawer_body
    assert "investmentArtifactTable(record.output_artifacts || [])" not in drawer_body
    artifact_body = _js_function_body(js, "investmentArtifactTable")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    assert "investment-artifact-table" in artifact_body
    assert "investment-artifact-role" in artifact_body
    assert "investment-artifact-file" in artifact_body
    assert ".investment-artifact-table" in css
    assert ".investment-artifact-role" in css
    assert ".investment-artifact-file" in css
    assert ".investment-artifact-role," in css
    assert "text-overflow: ellipsis;" in css


def test_investment_records_times_are_formatted_as_beijing_time():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function investmentFormatBeijingTime(" in js
    assert "Asia/Shanghai" in js
    request_body = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    cache_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    audit_body = _js_function_body(js, "renderInvestmentOperationAuditsTable")
    assert "investmentFormatBeijingTime(record.created_at)" in request_body
    assert "investmentFormatBeijingTime(entry.updated_at)" in cache_body
    assert "investmentFormatBeijingTime(audit.created_at)" in audit_body


def test_investment_console_uses_beijing_time_for_all_backend_timestamps():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    stock_stats_body = _js_function_body(js, "investmentStockStats")
    stock_rows_body = _js_function_body(js, "renderInvestmentStockRows")
    users_body = _js_function_body(js, "renderInvestmentUsersTable")
    user_dialog_body = _js_function_body(js, "openInvestmentUserDialog")
    fill_user_body = _js_function_body(js, "fillInvestmentUserForm")
    save_user_body = _js_function_body(js, "saveInvestmentUser")
    import_result_body = _js_function_body(js, "renderInvestmentImportResult")
    current_content_body = _js_function_body(js, "renderInvestmentCurrentEffective")
    content_table_body = _js_function_body(js, "renderInvestmentContentTable")
    content_detail_body = _js_function_body(js, "showInvestmentContentDetail")
    content_audits_body = _js_function_body(js, "renderInvestmentOperationAudits")
    skill_row_body = _js_function_body(js, "renderInvestmentSkillConfigRow")

    assert "investmentFormatBeijingTime(stats.latest_updated_at || '')" in stock_stats_body
    assert "investmentFormatBeijingTime(stock.updated_at || '')" in stock_rows_body
    assert "investmentFormatBeijingDate(user.auth_end_at || '')" in users_body
    assert "investmentUtcToBeijingDatetimeLocal(user.auth_start_at || '')" in user_dialog_body
    assert "investmentUtcToBeijingDatetimeLocal(user.auth_end_at || '')" in user_dialog_body
    assert "investmentUtcToBeijingDatetimeLocal(user.auth_start_at || '')" in fill_user_body
    assert "investmentUtcToBeijingDatetimeLocal(user.auth_end_at || '')" in fill_user_body
    assert "investmentBeijingDatetimeLocalToUtc(document.getElementById(`${prefix}-auth-start`).value)" in save_user_body
    assert "investmentBeijingDatetimeLocalToUtc(document.getElementById(`${prefix}-auth-end`).value)" in save_user_body
    assert "investmentFormatBeijingTime(row.auth_end_at || '')" in import_result_body
    assert "investmentFormatBeijingTime(record?.effective_at)" in current_content_body
    assert "investmentFormatBeijingTime(record.created_at)" in content_table_body
    assert "investmentFormatBeijingTime(record.created_at)" in content_detail_body
    assert "investmentFormatBeijingTime(record.effective_at)" in content_detail_body
    assert "investmentFormatBeijingTime(record.archived_at)" in content_detail_body
    assert "investmentFormatBeijingTime(audit.created_at)" in content_audits_body
    assert "investmentFormatBeijingTime(active.uploaded_at)" in skill_row_body


def test_investment_records_tabs_use_independent_loaders_and_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentRecordsFilters(" in js
    assert "function investmentSelected(" in js
    assert "function investmentRecordsFilterValue(" in js
    assert "function loadInvestmentRecordsTab(" in js
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")
    content_load_body = _js_function_body(js, "loadInvestmentGeneratedContent")
    assert "/api/investment/records/requests" in load_body
    assert "/api/investment/records/contents" in load_body
    assert "/api/investment/artifacts" in content_load_body
    assert "/api/investment/audits" in load_body
    assert "investmentRecordsState.filters[tab]" in js
    assert "['invalidated', '已失效']" in filters_body


def test_investment_records_tabs_keep_independent_pagination_state():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_start = js.index("let investmentRecordsState =")
    state_end = js.index("const INVEST_VIEW_PERMISSIONS")
    state_body = js[state_start:state_end]
    assert "requests: {page: '1', page_size: '80', start_date: investmentTodayDate(), end_date: investmentTodayDate()}" in state_body
    assert "contents: {page: '1', page_size: '80'}" in state_body
    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: investmentTodayDate()}" in state_body
    assert "audits: {page: '1', page_size: '80', start_date: investmentTodayDate(), end_date: investmentTodayDate()}" in state_body

    switch_body = _js_function_body(js, "switchInvestmentRecordsTab")
    assert "investmentRecordsState.filters[tab]" in switch_body
    assert "page: '1'" not in switch_body


def test_investment_records_filters_reset_page_and_queries_page_size():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    query_body = _js_function_body(js, "investmentRecordsQueryParams")
    set_filter_body = _js_function_body(js, "investmentRecordsSetFilterValues")
    apply_body = _js_function_body(js, "applyInvestmentRecordsFilters")
    reset_body = _js_function_body(js, "resetInvestmentRecordsFilters")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")

    assert "params.set('page', filters.page || '1')" in query_body
    assert "params.set('page_size', filters.page_size || investmentRecordsDefaultPageSize(tab))" in query_body
    assert "filters.page = '1';" in set_filter_body
    assert "investmentRecordsSetFilterValues(tab, {resetPage: true})" in apply_body
    assert "investmentRecordsDefaultFilters(tab)" in reset_body
    assert "data.pagination" in load_body
    assert "investmentRecordsState.pagination[tab]" in load_body
    assert "renderInvestmentRecordsPagination(tab)" in load_body


def test_generated_content_keyword_search_is_backend_query_not_page_filter():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    apply_body = _js_function_body(js, "applyInvestmentCacheDate")
    render_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")

    assert "investmentRecordsState.filters.cache.keyword" in apply_body
    assert "investmentRecordsQueryParams('cache')" in _js_function_body(js, "loadInvestmentGeneratedContent")
    assert "haystack.includes(keyword)" not in render_body
    assert "values.filter(entry => {" not in render_body


def test_investment_records_pagination_controls_are_rendered():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "function renderInvestmentRecordsPagination(" in js
    pagination_body = _js_function_body(js, "renderInvestmentRecordsPagination")
    assert "investment-records-pagination" in pagination_body
    assert "共 ${escapeHtml(total)} 条" in pagination_body
    assert "第 ${escapeHtml(page)} / ${escapeHtml(totalPages)} 页" in pagination_body
    assert "上一页" in pagination_body
    assert "下一页" in pagination_body
    assert "investment-records-page-size" in pagination_body
    assert "[50, 80, 120, 200]" in pagination_body
    assert "function changeInvestmentRecordsPage(" in js
    assert "function changeInvestmentRecordsPageSize(" in js
    assert ".investment-records-pagination" in css
    assert ".investment-records-page-size" in css


def test_investment_cache_category_selection_uses_server_side_filtering():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    select_body = _js_function_body(js, "selectInvestmentCacheCategory")
    back_body = _js_function_body(js, "backInvestmentCacheCategoryMenu")

    assert "investmentRecordsState.filters.cache.service_type = serviceType" in select_body
    assert "investmentRecordsState.filters.cache.page = '1'" in select_body
    assert "scheduleInvestmentCacheFilterRefresh()" in select_body
    assert "await loadInvestmentGeneratedContent()" not in select_body
    assert "delete investmentRecordsState.filters.cache.service_type" in back_body
    assert "investmentRecordsState.filters.cache.page = '1'" in back_body
    assert "await loadInvestmentGeneratedContent()" in back_body


def test_investment_content_and_cache_date_filters_are_exposed():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "invest-content-history-effective-date-rate" in js
    assert "invest-content-history-effective-date-convertible_bond" in js
    assert "function investmentContentHistoryEffectiveDate(serviceType)" in js
    assert "investmentContentHistoryEffectiveDate(serviceType)" in js
    assert "refreshInvestmentContentRecords(serviceType, {effective_date: investmentContentHistoryEffectiveDate(serviceType)})" in js
    assert "investment-records-filter-market_date" in js
    assert "investmentCacheMarketDate()" in js
    assert "investmentFetchJson(query.toString() ? `/api/investment/artifacts?${query.toString()}` : '/api/investment/artifacts')" in js
    assert "investmentGeneratedOutputState(entry)" in js
    assert "investmentRecordFileSummary(entry.output_files || [])" not in js


def test_investment_content_history_date_filters_are_scoped_by_service_type():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    effective_date_body = _js_function_body(js, "investmentContentHistoryEffectiveDate")
    render_content_body = _js_function_body(js, "renderInvestmentContent")
    refresh_records_body = _js_function_body(js, "refreshInvestmentContentRecords")

    assert "const historyDateId = investmentContentHistoryEffectiveDateId(serviceType);" in js
    assert "investmentRenderDateControl(historyDateId" in render_content_body
    assert "function investmentContentHistoryEffectiveDateId(serviceType)" in js
    assert "return `invest-content-history-effective-date-${normalizedServiceType}`;" in js
    assert "document.getElementById(historyDateId)" in js
    assert "document.getElementById('invest-content-history-effective-date')" not in js
    assert "investmentContentHistoryEffectiveDateId(serviceType)" in effective_date_body
    assert "document.getElementById(historyDateId)" in effective_date_body
    assert "investmentTodayDate()" in effective_date_body
    assert "query.set('effective_date', effectiveDate || investmentTodayDate());" in js
    assert "investmentContentHistoryEffectiveDate()" not in render_content_body
    assert "investmentContentHistoryEffectiveDate(serviceType)" in render_content_body
    assert "investmentContentHistoryEffectiveDate()" not in refresh_records_body
    assert "investmentContentHistoryEffectiveDate(serviceType)" in refresh_records_body


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
