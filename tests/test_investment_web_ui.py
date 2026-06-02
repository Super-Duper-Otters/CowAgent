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


def test_investment_table_like_views_use_wide_containers():
    html = CHAT_HTML.read_text(encoding="utf-8")

    users_start = html.index('id="view-invest-users"')
    users_end = html.index('id="view-invest-rate"')
    users_body = html[users_start:users_end]
    rate_start = html.index('id="view-invest-rate"')
    rate_end = html.index('id="view-invest-cb"')
    rate_body = html[rate_start:rate_end]
    cb_start = html.index('id="view-invest-cb"')
    cb_end = html.index('id="view-invest-content"')
    cb_body = html[cb_start:cb_end]
    content_start = html.index('id="view-invest-content"')
    content_end = html.index('id="view-invest-records"')
    content_body = html[content_start:content_end]
    records_start = html.index('id="view-invest-records"')
    records_end = html.index('id="view-invest-config"')
    records_body = html[records_start:records_end]

    assert "w-full max-w-[1600px] mx-auto" in users_body
    assert "w-full max-w-[1600px] mx-auto" in rate_body
    assert "w-full max-w-[1600px] mx-auto" in cb_body
    assert "w-full max-w-[1600px] mx-auto" in content_body
    assert "w-full max-w-[1600px] mx-auto" in records_body
    assert "max-w-6xl mx-auto" not in users_body
    assert "max-w-6xl mx-auto" not in rate_body
    assert "max-w-6xl mx-auto" not in cb_body
    assert "max-w-6xl mx-auto" not in content_body
    assert "max-w-6xl mx-auto" not in records_body


def test_investment_content_is_a_top_level_view():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'data-view="invest-content"' in html
    assert 'id="view-invest-content"' in html
    assert 'id="invest-content-content"' in html
    assert "'invest-content':" in js
    assert "if (viewId === 'invest-content') return renderInvestmentGeneratedContent();" in js
    assert "'invest-content': 'cache.read'" in js


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
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")

    assert "investment-user-toolbar-heading" in body
    assert "investment-user-actionbar" in body
    assert "investment-toolbar-section search" in body
    assert "investment-toolbar-section export" in body
    assert body.index("investment-user-toolbar-heading") < body.index("investment-user-actionbar")

    assert ".investment-user-actionbar" in css
    assert ".investment-toolbar-section" in css
    assert ".investment-toolbar-section.export" in css


def test_investment_customer_import_uses_dialog_with_template_and_result():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")
    import_body = _js_function_body(js, "openInvestmentUsersImportDialog")

    assert "openInvestmentUsersImportDialog()" in body
    assert "invest-users-import-file" not in body
    assert "showInvestmentModal('导入客户名单'" in import_body
    assert "存在用户名单示例模板" in import_body
    assert "/api/investment/users/import-template.xlsx" in import_body
    assert "invest-users-import-result" in import_body
    assert "parseInvestmentUsersImport()" in import_body
    assert "confirmInvestmentUsersImport()" in js
    assert "解析文件" in import_body
    assert "确认导入" in js
    assert "commit" in js
    assert "解析中" in js
    assert "new_users" in js
    assert "function renderInvestmentImportResult(data, committed = false)" in js
    assert "renderInvestmentImportResult(data, false)" in js
    assert "renderInvestmentImportResult(data, true)" in js
    assert "window.openInvestmentUsersImportDialog = openInvestmentUsersImportDialog" in js


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
    assert "investment-tabs investment-config-tabs" in shell_body
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
    assert ".investment-config-tabs" in css
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
    assert "const saveHandler = escapeHtml(`saveInvestmentConfigKey(${keyArg}, ${typeArg})`);" in config_field_body
    assert "const dirtyHandler = escapeHtml(`markInvestmentConfigDirty(${keyArg})`);" in config_field_body
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
    assert "investmentButtonIfCan('records.export', 'fa-download'" in js
    assert "investmentButtonIfCan('records.export', 'fa-calendar-days'" in js
    assert "investmentButtonIfCan('records.export', 'fa-chart-pie'" in js


def test_investment_request_export_panel_is_scoped_and_mode_based():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    shell_body = _js_function_body(js, "renderInvestmentRecordsShell")
    assert "investmentRecordsState.tab === 'requests' ? renderInvestmentRequestExportPanel()" in shell_body
    assert "investment-records-export\">" not in shell_body
    assert "investment-records-export-fields" not in shell_body

    panel_body = _js_function_body(js, "renderInvestmentRequestExportPanel")
    assert "公众号请求导出" in panel_body
    assert "导出当前筛选" in panel_body
    assert "全量导出" in panel_body
    assert "按日期范围" in panel_body
    assert "按月导出" in panel_body
    assert "按季度导出" in panel_body
    assert "investment-request-export-fields" in panel_body

    current_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    assert "investmentRecordsQueryParams('requests')" in current_body
    assert "请选择导出开始和结束日期" in range_body
    assert "function exportInvestmentRequestRecordsFull()" in js
    assert ".investment-request-export-panel" in css
    assert ".investment-request-export-modes" in css


def test_investment_request_export_exposes_unauthorized_and_customer_filter():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    panel_body = _js_function_body(js, "renderInvestmentRequestExportPanel")
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    month_body = _js_function_body(js, "exportInvestmentRequestRecordsByMonth")
    quarter_body = _js_function_body(js, "exportInvestmentRequestRecordsByQuarter")
    current_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")
    full_body = _js_function_body(js, "exportInvestmentRequestRecordsFull")

    assert "unauthorized_request: '无权限请求'" in js
    assert "['unauthorized_request', '无权限请求']" in filters_body
    assert '<option value="unauthorized_request">无权限请求</option>' in panel_body
    assert "id=\"invest-export-customer\"" in panel_body
    assert "OpenID/手机号" in panel_body
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
    assert "cache: {page: '1', page_size: '120', market_date: investmentTodayDate()}" in state_body
    assert "audits: {page: '1', page_size: '80', start_date: investmentTodayDate(), end_date: investmentTodayDate()}" in state_body
    assert "start_date: investmentTodayDate()" in default_body
    assert "end_date: investmentTodayDate()" in default_body
    assert "market_date: investmentTodayDate()" in default_body
    assert "data.market_dates[0]" not in load_body
    assert "timeZone: 'Asia/Shanghai'" in _js_function_body(js, "investmentTodayDate")


def test_investment_cache_empty_date_falls_back_to_today_before_loading():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    apply_body = _js_function_body(js, "applyInvestmentCacheDate")
    assert "?.value || investmentTodayDate()" in apply_body
    assert "await loadInvestmentGeneratedContent()" in apply_body


def test_investment_records_page_uses_tab_workspace_and_drawer():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "let investmentRecordsState =" in js
    assert "function switchInvestmentRecordsTab(" in js
    assert "function renderInvestmentRecordsShell(" in js
    assert "function openInvestmentRecordDrawer(" in js
    assert "investment-records-workspace" in js
    assert "investment-records-board" in js
    assert "investment-records-tabs" in js
    assert "investment-records-drawer" in js
    assert ".investment-records-workspace" in css
    assert ".investment-records-board" in css
    assert "border: 1px solid #d8e1ee;" in css
    assert ".investment-records-tabs" in css
    assert ".investment-records-drawer" in css
    assert ".investment-records-main" in css


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
    assert "investment-generated-content-home" in cache_home_body
    assert "investment-generated-content-entry" in cache_home_body
    assert "['technical_analysis', 'rate', 'convertible_bond']" in cache_body
    assert "investment-records-cache-layout" not in js
    assert "investment-records-date-list" not in js


def test_investment_generated_content_page_avoids_duplicate_date_controls_and_wide_three_column_lists():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    records_shell = _js_function_body(js, "renderInvestmentRecordsShell")
    assert "生成内容" not in records_shell
    assert "renderInvestmentRecordsTabButton('cache'" not in records_shell
    assert "当日生成" not in js
    assert "当日有关生成内容" not in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    assert cache_body.count("investment-records-filter-market_date") == 1
    assert "investment-generated-content-datebar" in cache_body
    assert "investment-cache-category-grid" not in cache_body
    assert '<span>生成日期</span>' in cache_body
    assert "investment-content-filter-keyword" in cache_body
    assert "investmentCacheKeyword()" in cache_body
    assert "entry.normalized_target" in cache_body
    assert "entry.output_files" in cache_body
    assert "investment-generated-content-detail" in css
    assert "investment-generated-content-entries" in css
    assert ".investment-generated-content-home {\n    display: grid;" in css
    assert "border: 1px solid #e2e8f0;" in css
    assert ".investment-generated-content-entries {\n    display: grid;\n    align-content: start;\n    min-height: 0;" in css
    assert "min-height: 44px;" in css
    assert "padding: 6px 10px;" in css
    assert ".investment-generated-content-date-actions .investment-field.compact {\n    flex-direction: row;\n    align-items: center;" in css
    assert "line-height: 40px;" in css
    assert "height: 40px;" in css
    assert "min-height: 360px;" in css
    assert "min-height: 156px;" in css
    assert "grid-template-columns: repeat(3, minmax(180px, 1fr));" in css


def test_investment_generated_content_category_detail_is_compact():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")
    category_body = _js_function_body(js, "renderInvestmentCacheCategory")
    row_body = _js_function_body(js, "renderInvestmentCacheCompactRows")
    assert "investment-generated-content-detail-count" in detail_body
    assert "investment-cache-category-title" not in category_body
    assert "renderInvestmentCacheCompactRows(entries)" in category_body
    assert "investment-generated-content-header" in row_body
    assert "<span>标的</span>" in row_body
    assert "align-content: start;" in css
    assert ".investment-generated-content-header,\n.investment-generated-content-row" in css
    assert "min-height: 44px;" in css
    assert "padding: 0 10px;" in css
    assert "grid-template-columns: minmax(140px, 1.4fr) 72px 82px 148px 92px 44px;" in css
    assert "grid-column: 1 / 6;" in css
    assert "investmentIconButtonIfCan('cache.write'" in row_body


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


def test_investment_request_drawer_keeps_error_details_and_audit_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    request_table = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    drawer_body = _js_function_body(js, "renderInvestmentRequestDrawer")

    assert "function investmentDeliveryStatusClass(" in js
    assert "record.delivery_status" in request_table
    assert "<th>生成</th><th>交付</th><th>提示摘要</th>" in request_table
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
    assert "产物审计" in drawer_body
    assert "investmentArtifactTable(record.output_artifacts || [])" in drawer_body


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
    assert "investmentFormatBeijingTime(user.auth_end_at || '')" in users_body
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
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")
    content_load_body = _js_function_body(js, "loadInvestmentGeneratedContent")
    assert "/api/investment/records/requests" in load_body
    assert "/api/investment/records/contents" in load_body
    assert "/api/investment/cache" in content_load_body
    assert "/api/investment/audits" in load_body
    assert "investmentRecordsState.filters[tab]" in js


def test_investment_records_tabs_keep_independent_pagination_state():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_start = js.index("let investmentRecordsState =")
    state_end = js.index("const INVEST_VIEW_PERMISSIONS")
    state_body = js[state_start:state_end]
    assert "requests: {page: '1', page_size: '80', start_date: investmentTodayDate(), end_date: investmentTodayDate()}" in state_body
    assert "contents: {page: '1', page_size: '80'}" in state_body
    assert "cache: {page: '1', page_size: '120', market_date: investmentTodayDate()}" in state_body
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
    assert "await loadInvestmentGeneratedContent()" in select_body
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
    assert "investmentFetchJson(query.toString() ? `/api/investment/cache?${query.toString()}` : '/api/investment/cache')" in js
    assert "investmentGeneratedOutputState(entry)" in js
    assert "investmentRecordFileSummary(entry.output_files || [])" not in js


def test_investment_content_history_date_filters_are_scoped_by_service_type():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    effective_date_body = _js_function_body(js, "investmentContentHistoryEffectiveDate")
    render_content_body = _js_function_body(js, "renderInvestmentContent")
    refresh_records_body = _js_function_body(js, "refreshInvestmentContentRecords")

    assert "const historyDateId = investmentContentHistoryEffectiveDateId(serviceType);" in js
    assert 'id="${historyDateId}"' in js
    assert "function investmentContentHistoryEffectiveDateId(serviceType)" in js
    assert "return `invest-content-history-effective-date-${normalizedServiceType}`;" in js
    assert "document.getElementById(investmentContentHistoryEffectiveDateId(serviceType))" in js
    assert "document.getElementById('invest-content-history-effective-date')" not in js
    assert "investmentContentHistoryEffectiveDateId(serviceType)" in effective_date_body
    assert "document.getElementById(investmentContentHistoryEffectiveDateId(serviceType))" in effective_date_body
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
