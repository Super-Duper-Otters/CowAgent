# encoding:utf-8
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_JS = ROOT / "channel" / "web" / "static" / "js" / "console.js"
CONSOLE_CSS = ROOT / "channel" / "web" / "static" / "css" / "console.css"
LOGIN_HTML = ROOT / "channel" / "web" / "login.html"
CHAT_HTML = ROOT / "channel" / "web" / "chat.html"


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


def test_backend_login_page_matches_console_auth_flow():
    html = LOGIN_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'id="login-page"' in html
    assert 'src="assets/logo.jpg"' in html
    assert "fetch('/auth/login'" in html
    assert "URLSearchParams(window.location.search)" in html
    assert "redirectToLogin(" in js
    assert "next=${encodeURIComponent(nextPath)}" in js


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

    assert "disableInvestmentUser('${encodeURIComponent(user.openid)}')" in js
    assert "await investmentFetchJson(`/api/investment/users/${encodeURIComponent(openid)}/disable`, {method: 'POST'})" in js
    assert "saveInvestmentUser('invest-user-modal')" in js
    assert "await investmentFetchJson('/api/investment/users', {" in js
    assert "openInvestmentSkillDialog('${escapeHtml(skillKey)}')" in js
    assert "await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/settings`, {" in js
    assert "await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(selectedVersion)}/activate`, {" in js


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
    assert "investmentButtonIfCan('users.write'" in js
    assert "investmentButtonIfCan('content.write'" in js
    assert "investmentButtonIfCan('records.read', 'fa-clock-rotate-left', '操作流水'" in js
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
    assert "${canReadStocks ? investmentStockTools(stockData.stats || {}) : ''}" in js


def test_investment_records_ui_respects_cache_and_export_permissions():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "renderInvestmentRecordsTabButton('cache'" in js
    assert "/api/investment/cache" in js
    assert "renderInvestmentRecordsCacheTab(" in js
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
    assert "按日期范围" in panel_body
    assert "按月导出" in panel_body
    assert "按季度导出" in panel_body
    assert "investment-request-export-fields" in panel_body

    current_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    assert "investmentRecordsQueryParams('requests')" in current_body
    assert "请选择导出开始和结束日期" in range_body
    assert ".investment-request-export-panel" in css
    assert ".investment-request-export-modes" in css


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


def test_investment_cache_uses_date_grouped_three_category_view():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentDailyGeneratedContent(" in js
    assert "function renderInvestmentCacheCategory(" in js
    assert "function selectInvestmentCacheCategory(" in js
    assert "function backInvestmentCacheCategoryMenu(" in js
    assert "technical_analysis" in js
    assert "rate" in js
    assert "convertible_bond" in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    cache_home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    assert "investment-generated-content-home" in cache_home_body
    assert "investment-generated-content-entry" in cache_home_body
    assert "['technical_analysis', 'rate', 'convertible_bond']" in cache_body
    assert "investment-records-cache-layout" not in js
    assert "investment-records-date-list" not in js


def test_investment_generated_content_tab_avoids_duplicate_date_controls_and_wide_three_column_lists():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "renderInvestmentRecordsTabButton('cache', '生成内容'" in js
    assert "当日生成" not in js
    assert "当日有关生成内容" not in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    assert cache_body.count("investment-records-filter-market_date") == 1
    assert "investment-generated-content-datebar" in cache_body
    assert "investment-cache-category-grid" not in cache_body
    assert '<span>生成日期</span>' in cache_body
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


def test_investment_records_tabs_use_independent_loaders_and_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentRecordsFilters(" in js
    assert "function investmentSelected(" in js
    assert "function investmentRecordsFilterValue(" in js
    assert "function loadInvestmentRecordsTab(" in js
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")
    assert "/api/investment/records/requests" in load_body
    assert "/api/investment/records/contents" in load_body
    assert "/api/investment/cache" in load_body
    assert "/api/investment/audits" in load_body
    assert "investmentRecordsState.filters[tab]" in js


def test_investment_records_tabs_keep_independent_pagination_state():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_start = js.index("let investmentRecordsState =")
    state_end = js.index("const INVEST_VIEW_PERMISSIONS")
    state_body = js[state_start:state_end]
    assert "requests: {page: '1', page_size: '80'}" in state_body
    assert "contents: {page: '1', page_size: '80'}" in state_body
    assert "cache: {page: '1', page_size: '120', market_date: ''}" in state_body
    assert "audits: {page: '1', page_size: '80'}" in state_body

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
    assert "await loadInvestmentRecordsTab('cache')" in select_body
    assert "delete investmentRecordsState.filters.cache.service_type" in back_body
    assert "investmentRecordsState.filters.cache.page = '1'" in back_body
    assert "await loadInvestmentRecordsTab('cache')" in back_body


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
