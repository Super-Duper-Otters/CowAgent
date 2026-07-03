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


def _python_class_body(source: str, name: str) -> str:
    match = re.search(rf"^class\s+{re.escape(name)}\b.*?:\n", source, re.MULTILINE)
    assert match, f"{name} class not found"
    next_class = re.search(r"^class\s+\w+\b.*?:\n", source[match.end():], re.MULTILINE)
    end = match.end() + next_class.start() if next_class else len(source)
    return source[match.end():end]


def test_web_console_uses_business_assistant_branding():
    html = CHAT_HTML.read_text(encoding="utf-8")
    login_html = LOGIN_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")
    web_channel = WEB_CHANNEL.read_text(encoding="utf-8")

    assert "智能投研辅助系统" in html
    assert "智能投研辅助系统" in login_html
    assert "智能投研辅助系统" in js
    assert '"智能投研辅助系统"' in web_channel
    assert "CowAgent" not in html
    assert "CowAgent" not in login_html
    assert "CowAgent" not in js
    assert '"CowAgent" if use_agent else "AI Assistant"' not in web_channel
    assert "sidebar-version" not in html
    assert "chatgpt-on-wechat/releases" not in html


def test_chat_handler_static_assets_are_busted_by_file_hash():
    web_channel = WEB_CHANNEL.read_text(encoding="utf-8")
    chat_handler = _python_class_body(web_channel, "ChatHandler")

    assert "hashlib.sha256(f.read()).hexdigest()[:12]" in chat_handler
    assert "js_cache_bust" in chat_handler
    assert "css_cache_bust" in chat_handler
    assert "int(time.time())" not in chat_handler


def test_non_business_management_pages_are_removed_from_frontend_navigation():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")
    removed_views = ("memory", "knowledge", "tasks")

    for view in removed_views:
        assert f'data-view="{view}"' not in html
        assert f'id="view-{view}"' not in html
        assert f"{view}:" not in js

    for key in ("menu_memory", "menu_knowledge", "menu_tasks", "nav_investment"):
        assert key not in js

    manage_group_start = html.index('data-group="manage"')
    monitor_group_start = html.index('data-group="monitor"')
    manage_group = html[manage_group_start:monitor_group_start]
    assert 'data-group="investment"' not in html
    assert 'data-view="config"' not in html
    assert 'id="view-config"' not in html
    assert "config:   { group: 'nav_manage',  page: 'menu_config' }" not in js
    assert "if (viewId === 'config') loadConfigView();" not in js
    assert 'data-view="channels"' not in html
    assert 'id="view-channels"' not in html
    assert "channels: { group: 'nav_manage',  page: 'menu_channels' }" not in js
    assert "else if (viewId === 'channels') loadChannelsView();" not in js
    assert 'data-view="invest-users"' in manage_group
    assert 'data-view="invest-health"' in manage_group


def test_session_history_panel_is_limited_to_chat_view():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    navigate_body = _js_function_body(js, "navigateTo")
    toggle_body = _js_function_body(js, "toggleSessionPanel")
    open_body = _js_function_body(js, "openSessionPanel")
    restore_body = _js_function_body(js, "_restoreSessionPanel")
    availability_body = _js_function_body(js, "updateSessionPanelAvailability")

    assert "function isChatViewActive()" in js
    assert "return currentView === 'chat';" in js
    assert "updateSessionPanelAvailability();" in navigate_body
    assert "toggleBtn.classList.toggle('hidden', !isChatViewActive());" in availability_body
    assert "closeSessionPanel();" in availability_body
    assert "if (!isChatViewActive()) return;" in toggle_body
    assert "if (!isChatViewActive()) return;" in open_body
    assert "if (!isChatViewActive()) {" in restore_body


def test_chat_message_images_are_scaled_inside_reply_bubbles():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert ".msg-content img" in css
    assert "max-width: min(100%, 360px);" in css
    assert "max-height: 420px;" in css
    assert "object-fit: contain;" in css


def test_user_chat_messages_render_as_plain_text_not_markdown():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "createUserMessageEl")

    assert "function renderUserPlainText" in js
    assert "renderUserPlainText(content)" in body
    assert "renderMarkdown(content)" not in body


def test_channels_page_defines_wechatmp_service_for_configured_service_accounts():
    web_channel = WEB_CHANNEL.read_text(encoding="utf-8")
    defs_start = web_channel.index("CHANNEL_DEFS = OrderedDict([")
    defs_end = web_channel.index("    @staticmethod", defs_start)
    channel_defs = web_channel[defs_start:defs_end]

    assert '("wechatmp_service",' in channel_defs
    assert '"wechatmp_app_id"' in channel_defs
    assert '"wechatmp_app_secret"' in channel_defs
    assert '"wechatmp_token"' in channel_defs
    assert '"wechatmp_aes_key"' in channel_defs
    assert '"wechatmp_port"' in channel_defs


def test_channel_disconnect_action_is_next_to_save_with_cancel_copy():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderActiveChannels")

    assert "channels_disconnect: '取消接入'" in js

    footer_start = render_body.index('<div class="flex items-center justify-end gap-3 pt-1">')
    footer_end = render_body.index('</div>', footer_start)
    footer = render_body[footer_start:footer_end]

    assert "disconnectChannel('${ch.name}')" in footer
    assert "saveChannelConfig('${ch.name}')" in footer
    assert footer.index("disconnectChannel('${ch.name}')") < footer.index("saveChannelConfig('${ch.name}')")


def test_channel_management_is_system_config_subpage():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")
    config_body = _js_function_body(js, "renderInvestmentConfig")
    tabs_body = _js_function_body(js, "investmentConfigTabDefinitions")
    panel_body = _js_function_body(js, "renderInvestmentConfigPanel")
    switch_body = _js_function_body(js, "switchInvestmentConfigPanel")

    assert "key: 'channels'" in tabs_body
    assert "label: '通道管理'" in tabs_body
    assert "renderInvestmentConfigChannelsPanel()" in panel_body
    assert "'channels'" in switch_body
    assert "currentInvestmentConfigPanel === 'channels'" in config_body
    assert "loadChannelsView();" in config_body
    assert "function renderInvestmentConfigChannelsPanel(" in js
    assert 'id="channels-content"' not in html
    assert 'id="channels-add-panel"' not in html


def test_ai_model_config_is_system_config_subpage():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")
    config_body = _js_function_body(js, "renderInvestmentConfig")
    tabs_body = _js_function_body(js, "investmentConfigTabDefinitions")
    panel_body = _js_function_body(js, "renderInvestmentConfigPanel")
    switch_body = _js_function_body(js, "switchInvestmentConfigPanel")
    ai_panel_body = _js_function_body(js, "renderInvestmentConfigAiModelPanel")

    assert "key: 'ai-model'" in tabs_body
    assert "label: 'AI模型配置'" in tabs_body
    assert "renderInvestmentConfigAiModelPanel()" in panel_body
    assert "'ai-model'" in switch_body
    assert "currentInvestmentConfigPanel === 'ai-model'" in config_body
    assert "loadConfigView();" in config_body
    assert "cfg-provider" in ai_panel_body
    assert "cfg-agent-save" in ai_panel_body
    assert "cfg-password-save" not in ai_panel_body
    assert "cfg-password" not in ai_panel_body
    assert "config_security" not in ai_panel_body
    assert 'id="cfg-provider"' not in html


def test_cache_update_management_is_system_config_subpage():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    tabs_body = _js_function_body(js, "investmentConfigTabDefinitions")
    panel_body = _js_function_body(js, "renderInvestmentConfigPanel")
    switch_body = _js_function_body(js, "switchInvestmentConfigPanel")
    cache_panel_body = _js_function_body(js, "renderInvestmentConfigCacheUpdatePanel")
    cache_content_body = _js_function_body(js, "renderInvestmentCacheUpdateContent")
    status_body = _js_function_body(js, "investmentCacheUpdateStatusBadge")
    load_body = _js_function_body(js, "loadInvestmentCacheUpdate")
    probe_body = _js_function_body(js, "runInvestmentCacheUpdateProbe")

    assert "key: 'cache-update'" in tabs_body
    assert "label: '缓存更新'" in tabs_body
    assert "renderInvestmentConfigCacheUpdatePanel()" in panel_body
    assert "'cache-update'" in switch_body
    assert "/api/investment/cache-update" in js
    assert "function loadInvestmentCacheUpdate(" in js
    assert "function runInvestmentCacheUpdateProbe(" in js
    assert "function saveInvestmentCacheUpdateConfig(" in js
    assert "function clearInvestmentAllTechnicalAnalysisCache(" in js
    assert "标的类型" in cache_content_body
    assert "当前数据日期" in cache_content_body
    assert "手动探测" in cache_panel_body
    assert "全部技术分析缓存失效" in cache_panel_body
    assert "管理技术分析缓存更新探测标的" not in cache_panel_body
    assert "probe_start" in cache_content_body
    assert "probe_end" in cache_content_body
    assert "probe_interval_minutes" in cache_content_body
    assert "probing" in cache_content_body
    assert "investment-cache-update-spinner" in status_body
    assert "检测中" in status_body
    assert "renderInvestmentCacheUpdateContent()" in cache_panel_body
    assert "renderInvestmentCacheUpdateContent({probing: true})" not in load_body
    assert "renderInvestmentCacheUpdateContent({" in probe_body
    assert "probing: true" in probe_body
    assert "products_invalidated" in probe_body
    assert "已自动失效" in probe_body
    assert "未发现新的数据日期" in probe_body
    assert ".investment-cache-update-spinner" in css
    assert "@keyframes investment-cache-update-spin" in css


def test_business_tables_are_bounded_and_have_sticky_headers():
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


def test_business_table_wrappers_expose_scroll_regions():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    table_wrap_body = _js_function_body(js, "investmentTableWrap")
    record_shell_body = _js_function_body(js, "investmentRecordTableShell")

    assert 'role="region"' in table_wrap_body
    assert 'aria-label="' in table_wrap_body
    assert 'data-scroll-hint="左右滑动查看完整表格"' in table_wrap_body
    assert 'investmentTableWrap(tableHtml, true, \'业务记录表格\')' in record_shell_body


def test_business_selects_reuse_cowagent_dropdown_ui():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    dropdown_body = _js_function_body(js, "investmentDropdown")
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    component_card_body = _js_function_body(js, "renderInvestmentComponentCard")
    skill_dialog_body = _js_function_body(js, "renderInvestmentSkillDialogBody")

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
    assert "investmentDropdown('invest-skill-dialog-version'" in skill_dialog_body
    assert "initInvestmentDropdowns" in js
    init_body = _js_function_body(js, "initInvestmentDropdowns")
    assert "root.matches('.cfg-dropdown[data-investment-dropdown]')" in init_body
    assert "initDropdown(" not in init_body
    assert "data-investment-dropdown-options" not in dropdown_body
    assert "investmentDropdown(`investment-records-filter-${key}`" in filters_body
    assert "<select" not in filters_body
    assert "<select" not in component_card_body
    assert ".investment-cow-dropdown" in css
    assert ".investment-cow-dropdown .cfg-dropdown-menu" in css
    assert "min-width: 0;" in css


def test_business_date_inputs_have_visible_calendar_controls():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "input[type=\"date\"]" in css
    assert "::-webkit-calendar-picker-indicator" in css
    assert "color-scheme: dark;" in css


def test_business_table_like_views_use_wide_containers():
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
    config_start = html.index('id="view-invest-config"')
    config_end = html.index('id="view-invest-skills"')
    config_body = html[config_start:config_end]

    assert "w-full max-w-[1600px] mx-auto" in users_body
    assert "w-full max-w-[1600px] mx-auto" in daily_body
    assert "w-full max-w-[1600px] mx-auto" in content_body
    assert "w-full max-w-[1600px] mx-auto" in records_body
    assert "w-full max-w-[1600px] mx-auto" in config_body
    assert "max-w-6xl mx-auto" not in users_body
    assert "max-w-6xl mx-auto" not in daily_body
    assert "max-w-6xl mx-auto" not in content_body
    assert "max-w-6xl mx-auto" not in records_body
    assert "max-w-6xl mx-auto" not in config_body


def test_business_content_is_a_top_level_view():
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


def test_business_generated_content_uses_shared_artifact_file_tree():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderInvestmentGeneratedContent")
    load_body = _js_function_body(js, "loadInvestmentProducts")
    category_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")

    assert "/api/investment/products" in load_body
    assert "/api/investment/cache" not in load_body
    assert "investment-artifact-browser" in category_body
    assert "investment-artifact-tree" in category_body
    assert "renderInvestmentArtifactLazyTree(" in category_body
    assert "loadInvestmentArtifactRootNodes(" in js
    assert "toggleInvestmentArtifactNode(" in js
    assert "loadInvestmentArtifactPackage(" in js
    assert "query.set('level', 'month')" in js
    assert "query.set('level', 'date')" in js
    assert "query.set('level', 'package')" in js
    assert "package_id" in js
    assert "renderInvestmentArtifactTree(" not in js
    assert "openInvestmentArtifactFile(" in js
    assert "renderInvestmentArtifactViewer(" in js
    assert "virtual_path" in js
    assert "raw_input.txt" in js
    assert "output" in js
    assert "intermediate" in js
    assert "data-artifact-level" in js
    assert "data-artifact-loaded" in js
    assert "data-artifact-depth" in js
    assert "investmentArtifactDepthClass(" in js
    assert "investment-artifact-package open" not in js
    assert "investment-artifact-folder open" not in js
    assert "investment-artifact-package-btn" in js
    assert "investment-artifact-folder-btn" in js
    assert "investment-artifact-file-btn" in js
    assert ".investment-artifact-package-btn" in css
    assert ".investment-artifact-folder-btn" in css
    assert ".investment-artifact-file-btn" in css
    assert ".investment-artifact-depth-0-btn" in css
    assert ".investment-artifact-depth-1-btn" in css
    assert ".investment-artifact-depth-2-btn" in css
    assert ".investment-artifact-depth-3-btn" in css
    assert ".investment-artifact-depth-4-btn" in css
    assert "padding-left: 22px;" in css
    assert "padding-left: 40px;" in css
    assert "padding-left: 58px;" in css
    assert "padding-left: 76px;" in css
    assert "padding-left: 94px;" in css
    assert "investment-content-list" in render_body
    assert ".investment-artifact-browser" in css
    assert ".investment-artifact-tree" in css
    assert ".investment-artifact-viewer" in css


def test_generated_history_category_detail_hydrates_artifact_tree_after_render():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    load_body = _js_function_body(js, "loadInvestmentProducts")
    select_body = _js_function_body(js, "selectInvestmentCacheCategory")
    hydrate_body = _js_function_body(js, "hydrateInvestmentGeneratedArtifactTree")

    assert "list.innerHTML = renderInvestmentDailyGeneratedContent(investmentRecordsState.data.products);" in load_body
    assert "if (investmentRecordsState.cacheCategory) await hydrateInvestmentGeneratedArtifactTree();" in load_body
    assert "loadInvestmentArtifactRootNodes(investmentRecordsState.cacheCategory)" in hydrate_body
    assert "scheduleInvestmentCacheFilterRefresh()" in select_body
    assert "await loadInvestmentGeneratedContent()" not in select_body


def test_generated_history_toolbar_controls_status_category_and_shows_validity_metadata():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    state_body = js[js.index("let investmentRecordsState ="):js.index("const INVEST_VIEW_PERMISSIONS")]
    toolbar_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    status_body = _js_function_body(js, "changeInvestmentGeneratedStatusCategory")
    cards_body = _js_function_body(js, "renderInvestmentGeneratedCategoryCards")
    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")
    meta_body = _js_function_body(js, "investmentGeneratedEntryValidityMeta")

    assert "products: {page: '1', page_size: '120', period_mode: 'day', business_date: '', keyword: '', status_category: 'all'}" in state_body
    assert "include_invalidated: '1'" not in state_body[state_body.index("products: {"):state_body.index("cache: {")]
    assert "investment-generated-status-category" in toolbar_body
    assert "[['all', '全部'], ['active', '有效'], ['unused', '未使用'], ['invalid', '失效']]" in toolbar_body
    assert "investmentRecordsState.filters.products.status_category = value || 'all';" in status_body
    assert "await loadInvestmentProducts();" in status_body
    assert "investmentGeneratedEntryValidityMeta(entries)" in cards_body
    assert "investmentGeneratedEntryValidityMeta(entries)" in detail_body
    assert "entry.display_status || entry.status || ''" in meta_body
    assert "entry.display_status_label || investmentProductStatusLabel(status)" in meta_body
    assert "investmentFormatBeijingTime(entry.expires_at)" not in meta_body
    assert "<span>失效" not in meta_body


def test_daily_content_tabs_are_built_from_content_components():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "content_enabled" in js
    assert "renderInvestmentContentModuleTabs" in js
    assert "currentInvestmentContentModuleKey" in js


def test_rate_and_convertible_bond_content_are_merged_under_business_content_page():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    sidebar_start = html.index('data-view="invest-users"')
    sidebar_end = html.index('data-view="invest-skills"', sidebar_start)
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
    assert "let currentInvestmentContentModuleKey = '';" in js
    assert "function switchInvestmentContentPanel(" in js
    assert "async function renderInvestmentDailyContent(" in js
    assert "if (viewId === 'invest-daily-content') return renderInvestmentDailyContent();" in js
    assert "'invest-daily-content': 'content.read'" in js
    assert "investment-tab" in _js_function_body(js, "renderInvestmentContentModuleTabs")
    assert "renderInvestmentContentModuleTabs" in daily_render_body
    assert "renderInvestmentContent(currentInvestmentContentModuleKey)" in daily_render_body


def test_general_skills_page_is_hidden_from_sidebar():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert 'data-view="skills"' not in html
    assert 'data-view="invest-skills"' in html
    assert "new Set(['memory', 'knowledge', 'tasks', 'skills'])" in js


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


def test_business_user_edit_and_record_details_use_modal_dialogs():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    show_body = _js_function_body(js, "showInvestmentModal")

    assert "function showInvestmentModal(" in js
    assert "function hideInvestmentModal(" in js
    assert "function openInvestmentUserDialog(" in js
    assert "showInvestmentModal('用户信息'" in js
    assert "showInvestmentModal('请求详情" in js
    assert "showInvestmentModal('内容详情" in js
    assert ".investment-modal-overlay" in css
    assert ".investment-modal" in css
    assert "let overlayPointerStartedOnBackdrop = false;" in show_body
    assert "overlay.addEventListener('pointerdown'" in show_body
    assert "overlay.addEventListener('pointerup'" in show_body
    assert "event.target === overlay && overlayPointerStartedOnBackdrop" in show_body
    assert "overlayPointerStartedOnBackdrop = false;" in show_body
    assert "function investmentMarkModalSurfaceInteraction(" in js
    assert "investmentShouldIgnoreBackdropClose(event)" in show_body


def test_business_modal_date_picker_month_navigation_does_not_close_modal():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    panel_body = _js_function_body(js, "investmentRenderDatePickerPanel")
    move_body = _js_function_body(js, "investmentMoveDatePickerMonth")

    assert 'onpointerdown="investmentMarkModalSurfaceInteraction(event)"' in panel_body
    assert "investmentMarkModalSurfaceInteraction();" in move_body


def test_business_config_fields_save_individually_after_change():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentConfigField(" in js
    assert "function markInvestmentConfigDirty(" in js
    assert "async function saveInvestmentConfigKey(" in js
    assert "data-config-key=" in js
    assert "investment-config-save" in js
    assert "保存全部配置" not in js


def test_business_operations_show_unified_feedback_toasts():
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


def test_business_config_actions_align_with_controls():
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "investment-config-field textarea-config" in js
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert ".investment-config-field.textarea-config" in css
    assert ".investment-config-field.textarea-config .investment-config-actions" in css


def test_business_skill_has_own_navigation_page():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")

    assert "技术分析与渲染" not in js
    assert 'data-view="invest-skills"' in html
    assert 'id="view-invest-skills"' in html
    assert "menu_invest_skills" in js
    assert "'invest-skills':" in js
    assert "renderInvestmentSkills()" in js
    assert "invest-skills-content" in js
    assert "renderInvestmentComponentManager(" in js
    assert "loadInvestmentComponents(" in js
    assert "renderInvestmentComponentCard(" in js
    assert "uploadInvestmentSkill(" in js
    assert "uploadInvestmentSkillPackage(" in js
    assert "saveInvestmentComponentSettings(" in js
    assert "activateInvestmentSkillVersion(" in js
    assert "deleteInvestmentSkillVersion(" in js
    assert "组件配置" in js
    assert "/api/investment/components" in js
    assert "/api/investment/components/${encodeURIComponent(componentKey)}/delete" in js
    assert "/api/investment/skills/packages/upload" in js
    assert "/api/investment/components/${encodeURIComponent(componentKey)}/settings" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/upload" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/activate" in js
    assert "/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/delete" in js
    assert "/api/investment/renderer-skill/" not in js
    assert "investment-skill-card" not in js


def test_business_components_page_uses_wide_container():
    html = CHAT_HTML.read_text(encoding="utf-8")
    start = html.index('id="view-invest-skills"')
    end = html.index('id="view-invest-health"')
    body = html[start:end]

    assert "w-full max-w-[1600px] mx-auto" in body
    assert "max-w-6xl mx-auto" not in body


def test_business_components_page_groups_component_types():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "/api/investment/components" in js
    assert "active_script" in js
    assert "active_prompt" in js
    assert "passive_script" in js
    assert "renderInvestmentComponentCard" in js
    assert "investment-component-board" in js
    assert "renderInvestmentSkillConfigTable" not in js


def test_business_component_cards_scope_controls_by_type():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    card_body = _js_function_body(js, "renderInvestmentComponentCard")
    config_dialog_body = _js_function_body(js, "renderInvestmentComponentConfigDialogBody")
    settings_body = _js_function_body(js, "investmentComponentSettingsBody")
    tag_body = _js_function_body(js, "investmentComponentTags")

    assert "component.uses_triggers" in tag_body
    assert "component.versioned" in card_body
    assert "被动组件" in js
    assert "主动组件" in js
    assert "包含脚本" in js
    assert "settings.prompt_key" in config_dialog_body
    assert "settings.prompt_configured === false" in config_dialog_body
    assert "settings.prompt_blocks" in config_dialog_body
    assert "invest-component-modal-prompt-block" in config_dialog_body
    assert "component.runtime" in card_body
    assert "deleteInvestmentRuntimeComponent" in card_body
    assert "invest-component-modal-triggers" in config_dialog_body
    assert "invest-component-modal-prompt" in config_dialog_body
    assert "invest-component-modal-card-footer-risk" in config_dialog_body
    assert "invest-component-modal-card-footer-auth" not in config_dialog_body
    assert "invest-component-modal-card-footer-data-source" in config_dialog_body
    assert "invest-component-modal-card-footer-contact" in config_dialog_body
    assert "恢复默认配置" in config_dialog_body
    assert "resetInvestmentComponentDefaults" in config_dialog_body
    assert "body.prompt_blocks" in settings_body
    assert "body.card_footer" in settings_body
    assert "resetInvestmentComponentDefaults" in js
    assert "reset_defaults: true" in js


def test_business_component_cards_hide_business_details():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    card_body = _js_function_body(js, "renderInvestmentComponentCard")

    assert "触发词" not in card_body
    assert "提示词" not in card_body
    assert "运行方式" not in card_body
    assert "输出" not in card_body
    assert "上传时间" not in card_body
    assert "调用方" not in card_body
    assert "openInvestmentComponentConfigDialog" in card_body
    assert "openInvestmentComponentVersionDialog" in card_body


def test_business_component_upload_copy_uses_component_wording():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    upload_body = _js_function_body(js, "uploadInvestmentSkill")
    activate_body = _js_function_body(js, "activateInvestmentSkillVersion")
    delete_body = _js_function_body(js, "deleteInvestmentSkillVersion")

    combined = "\n".join((upload_body, activate_body, delete_body))
    assert "组件版本已上传并设为生效" in combined
    assert "组件版本已生效" in combined
    assert "组件版本已删除" in combined
    assert "Skill 已上传" not in combined
    assert "Skill 版本" not in combined


def test_business_component_import_dialog_uses_minimal_skill_flow():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    handlers = (ROOT / "channel" / "web" / "investment_handlers.py").read_text(encoding="utf-8")
    dialog_body = _js_function_body(js, "renderInvestmentComponentImportDialogBody")

    assert "/api/investment/component-imports/preview" in handlers
    assert "/api/investment/component-imports/(.*)/create" in handlers
    assert "openInvestmentComponentImportDialog" in js
    assert "previewInvestmentComponentImport" in js
    assert "createInvestmentComponentFromImport" in js
    assert "从 ZIP 创建组件" in js
    assert "手动创建提示词组件" in js
    assert "/api/investment/component-imports/preview" in js
    assert "/api/investment/component-imports/${encodeURIComponent(importId)}/create" in js
    assert "/api/investment/components/prompt" in handlers
    assert "/api/investment/components/prompt" in js
    assert "主动脚本组件" in js
    assert "被动脚本组件" in js
    assert "主动提示词组件" in js
    assert "postprocess" in js
    assert "default_output" in js
    assert "prompt" in _js_function_body(js, "investmentComponentImportPayload")
    assert "investmentImportInfo" in js
    assert "investment-component-import-info" in js
    assert '<select id="invest-component' not in js
    assert "invest-component-import-match" in dialog_body
    assert "investmentDropdown('invest-component-import-match'" in dialog_body
    assert "investmentSetDropdownValue" in js
    assert "cfg-dropdown investment-cow-dropdown" in _js_function_body(js, "investmentDropdown")
    assert "investmentFilePicker('invest-component-import-file', '.zip')" in dialog_body
    assert "updateInvestmentFilePickerLabel" in js
    assert "investment-file-picker-button" in css
    assert "investment-file-picker-input" in css
    assert ".investment-field select" in css
    assert "appearance: none" in css
    assert "background-image: url(\"data:image/svg+xml" in css
    assert "请先上传并预览 Skill ZIP" in dialog_body
    assert "disabled" in dialog_body
    assert 'value="technical-analysis"' not in dialog_body
    assert "DAG" not in js
    assert "工作流编辑器" not in js


def test_prompt_component_create_and_config_ui_are_separate_from_zip_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    manager_body = _js_function_body(js, "renderInvestmentComponentManager")
    manual_body = _js_function_body(js, "renderInvestmentPromptComponentDialogBody")
    import_payload_body = _js_function_body(js, "investmentComponentImportPayload")
    config_body = _js_function_body(js, "renderInvestmentComponentConfigDialogBody")
    prompt_config_body = _js_function_body(js, "renderInvestmentPromptComponentConfigFields")
    settings_body = _js_function_body(js, "investmentComponentSettingsBody")

    assert "openInvestmentComponentImportDialog()" in manager_body
    assert "openInvestmentPromptComponentDialog()" in manager_body
    assert "invest-component-prompt-file" not in manual_body
    assert "invest-component-prompt-template" in manual_body
    assert "createInvestmentPromptComponent" in js
    assert "active_prompt" in import_payload_body
    assert "execution" in import_payload_body
    assert "component.handler_type === 'prompt_component'" in config_body
    assert "renderInvestmentPromptComponentConfigFields" in config_body
    assert "invest-component-modal-prompt-template" in prompt_config_body
    assert "invest-component-modal-command" not in prompt_config_body
    assert "component_config.prompt" in settings_body


def test_command_component_config_dialog_edits_execution_fields_and_tooltips():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    config_body = _js_function_body(js, "renderInvestmentComponentConfigDialogBody")
    command_config_body = _js_function_body(js, "renderInvestmentCommandComponentConfigFields")
    settings_body = _js_function_body(js, "investmentComponentSettingsBody")

    assert "renderInvestmentCommandComponentConfigFields" in js
    assert "component.handler_type === 'command_script'" in config_body
    assert "invest-component-modal-command" in js
    assert "invest-component-modal-default-output" in js
    assert "invest-component-modal-outputs-json" in js
    assert "invest-component-modal-postprocess-component" in js
    assert "component_config" in settings_body
    assert "investmentImportInfo" in command_config_body
    assert "data-tooltip" in js
    assert ".investment-component-import-info:hover::after" in css
    assert "title=" not in _js_function_body(js, "investmentImportInfo")


def test_only_versioned_components_show_upload_controls():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    card_body = _js_function_body(js, "renderInvestmentComponentCard")
    skill_dialog_body = _js_function_body(js, "renderInvestmentSkillDialogBody")

    assert "component.versioned" in card_body
    assert "openInvestmentComponentVersionDialog" in card_body
    assert "uploadInvestmentSkill" in js
    assert "activateInvestmentSkillVersion" in js
    assert "当前版本" in skill_dialog_body
    assert "该组件无脚本版本" not in card_body


def test_business_user_and_skill_edit_buttons_call_write_apis():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "setInvestmentUserStatus('${encodeURIComponent(user.openid)}'" in js
    assert "await investmentFetchJson(`/api/investment/users/${encodeURIComponent(openid)}/status/${action}`, {method: 'POST'})" in js
    assert "saveInvestmentUser('invest-user-modal')" in js
    assert "await investmentFetchJson('/api/investment/users', {" in js
    assert "saveInvestmentComponentSettings('${escapeHtml(componentKey)}', 'modal')" in js
    assert "saveInvestmentComponentEnabled('${escapeHtml(componentKey)}')" in js
    assert "await investmentFetchJson(`/api/investment/components/${encodeURIComponent(componentKey)}/settings`, {" in js
    assert "await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(selectedVersion)}/activate`, {" in js


def test_business_user_save_requires_authorization_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    save_user_body = _js_function_body(js, "saveInvestmentUser")
    user_dialog_body = _js_function_body(js, "openInvestmentUserDialog")

    assert "investmentRenderDateControl('invest-user-modal-auth-start-date'" in user_dialog_body
    assert "investmentRenderDateControl('invest-user-modal-auth-end-date'" in user_dialog_body
    assert "investmentRenderTimeControl('invest-user-modal-auth-start-time'" not in user_dialog_body
    assert "investmentRenderTimeControl('invest-user-modal-auth-end-time'" not in user_dialog_body
    assert "'datetime-local'" not in user_dialog_body
    assert "请选择授权服务" in save_user_body
    assert "请填写授权开始日期" in save_user_body
    assert "请填写授权结束日期" in save_user_body
    assert "auth_start_at: investmentBeijingDateTimeToUtc(authStartDate, '00:00')" in save_user_body
    assert "auth_end_at: investmentBeijingDateTimeToUtc(authEndDate, '00:00')" in save_user_body


def test_business_users_page_splits_customers_and_admin_staff():
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


def test_business_users_page_is_list_first_with_dialog_forms():
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


def test_business_boolean_controls_use_green_switches():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")

    config_field_body = _js_function_body(js, "renderInvestmentConfigField")
    service_checks_body = _js_function_body(js, "investmentUserServiceChecks")
    channel_fields_body = _js_function_body(js, "buildChannelFieldsHtml")
    ai_model_panel_body = _js_function_body(js, "renderInvestmentConfigAiModelPanel")

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
    assert '<label class="investment-switch">' in ai_model_panel_body
    assert '<input id="cfg-enable-thinking" type="checkbox">' in ai_model_panel_body
    assert "log-filter-switch" in html
    assert "peer-checked" not in html

    assert ".investment-switch" in css
    assert ".investment-switch-track" in css
    assert ".investment-switch-thumb" in css
    assert ".log-filter-switch" in css
    assert ".investment-switch input[type=\"checkbox\"]:checked + .investment-switch-track" in css
    assert "background: #35A85B;" in css


def test_business_user_service_switches_normalize_all_selection():
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


def test_business_users_toolbar_is_grouped_and_paginated():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "investmentUserState" in js
    assert "pagination:" in js
    assert "customers: {page: 1, page_size: 20" in js
    assert "renderInvestmentUserPagination('customers'" in js
    assert "function changeInvestmentUserPage(" in js
    assert "function changeInvestmentUserPageSize(" in js
    assert "onclick=\"changeInvestmentUserPage('${panel}'" in js
    assert "changeInvestmentUserPageSize('${panel}', value)" in js
    assert "investment-user-page-size-${panel}" in js
    assert "[20, 50, 80, 120, 200]" in js
    assert "applyInvestmentCustomerSearch()" in js
    assert "applyInvestmentAdminSearch()" in js
    assert "investment-user-toolbar-grid" in js
    assert "investment-toolbar-group primary" in js

    assert ".investment-user-toolbar-grid" in css
    assert ".investment-toolbar-group" in css
    assert ".investment-customer-toolbar" in css
    assert ".investment-user-pagination" in css


def test_business_customer_toolbar_has_separate_action_bar():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")

    assert "investment-user-toolbar-heading" in body
    assert "investment-user-actionbar" in body
    assert "investment-toolbar-section search" in body
    assert "investment-toolbar-section actions" in body
    assert "investment-customer-toolbar" in body
    assert "investment-customer-toolbar-actions" in body
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


def test_business_admin_toolbar_and_table_spacing_are_polished():
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
    assert "width: 112px;" in css
    assert "width: 344px;" in css
    assert ".investment-row-action-list" in css
    assert ".investment-table-wrap > .investment-table:first-child" in css

    customer_table_body = _js_function_body(js, "renderInvestmentUsersTable")
    admin_table_body = _js_function_body(js, "renderInvestmentAdminUsersTable")
    assert "function investmentMiddleEllipsis(" in js
    assert "function investmentFormatBeijingDate(" in js
    assert "const isUnbound = user.bind_status === 'unbound' || !user.openid;" in customer_table_body
    assert "待绑定" in customer_table_body
    assert "investment-table investment-customer-table" in customer_table_body
    assert "investment-customer-col-openid" in customer_table_body
    assert "investment-customer-col-actions" in customer_table_body
    assert "investmentMiddleEllipsis(user.openid, 6, 4)" in customer_table_body
    assert "investment-row-action-list" in customer_table_body
    assert "unbindInvestmentUserOpenid" in customer_table_body
    assert "deleteInvestmentUser(${Number(user.id || 0)})" in customer_table_body
    assert "isUnbound ? investmentButtonIfCan('customers.write', 'fa-trash'" not in customer_table_body
    assert "investmentFormatBeijingDate(user.auth_end_at || '')" in customer_table_body
    assert "investmentFormatBeijingTime(user.auth_end_at || '')" not in customer_table_body
    assert '<td title="${escapeHtml(user.username || \'\')}">${escapeHtml(user.username || \'\')}</td>' in admin_table_body


def test_business_customer_import_uses_dialog_with_template_and_result():
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


def test_business_customer_export_uses_dedicated_dialog():
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


def test_activation_code_api_routes_are_registered():
    from channel.web.investment_handlers import INVESTMENT_API_URLS

    urls = "\n".join(INVESTMENT_API_URLS)
    assert "/api/investment/activation-codes" in urls
    assert "/api/investment/activation-codes/(.*)/disable" in urls
    assert "/api/investment/export/activation-codes.xlsx" in urls


def test_activation_codes_panel_is_available_in_user_management():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "activation_codes.read" in js
    assert "activation-codes" in js
    assert "renderInvestmentActivationCodes" in js
    assert "openInvestmentActivationCodeDialog" in js
    assert "generateInvestmentActivationCodes" in js
    assert "disableInvestmentActivationCode" in js
    assert "window.renderInvestmentActivationCodes = renderInvestmentActivationCodes" in js
    assert "window.openInvestmentActivationCodeDialog = openInvestmentActivationCodeDialog" in js
    assert "window.generateInvestmentActivationCodes = generateInvestmentActivationCodes" in js
    assert "window.disableInvestmentActivationCode = disableInvestmentActivationCode" in js
    assert "window.applyInvestmentActivationCodeSearch = applyInvestmentActivationCodeSearch" in js
    assert "window.clearInvestmentActivationCodeSearch = clearInvestmentActivationCodeSearch" in js
    assert "window.exportInvestmentActivationCodes = exportInvestmentActivationCodes" in js
    assert "/api/investment/activation-codes" in js
    assert "/api/investment/export/activation-codes.xlsx" in js
    assert "ANAL-" in js

    render_body = _js_function_body(js, "renderInvestmentActivationCodes")
    assert "investmentFetchJson(`/api/investment/activation-codes?${investmentUserQuery('activation_codes')}`)" in render_body
    assert "openInvestmentActivationCodeDialog(1)" in render_body
    assert "openInvestmentActivationCodeDialog(10)" in render_body

    table_body = _js_function_body(js, "renderInvestmentActivationCodesTable")
    assert "row.code || row.code_prefix" in table_body
    assert "investment-table investment-activation-table" in table_body
    assert "investment-activation-col-code" in table_body
    assert "investment-activation-code" in table_body
    assert "investment-activation-date" in table_body
    assert "<th>激活码</th>" in table_body
    assert "<th>有效期</th>" in table_body
    assert "investmentFormatBeijingDate(row.code_expires_at || '')" in table_body
    assert "investmentMiddleEllipsis(row.batch_id || '', 10, 8)" in table_body
    assert "row.code_hash" not in table_body

    css = CONSOLE_CSS.read_text(encoding="utf-8")
    assert ".investment-user-page .investment-activation-table" in css
    assert ".investment-activation-col-code" in css
    assert ".investment-activation-col-batch" in css
    assert ".investment-user-page .investment-activation-table .investment-activation-code" in css


def test_business_customer_render_uses_response_rows_with_response_pagination():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    body = _js_function_body(js, "renderInvestmentCustomerUsers")

    users_pos = body.index("const users = data.users || [];")
    pagination_pos = body.index("investmentUserApplyPagination('customers', data.pagination);")
    table_pos = body.index("${renderInvestmentUsersTable(users)}")
    assert users_pos < pagination_pos < table_pos
    assert "${renderInvestmentUserPagination('customers', data.pagination)}" in body


def test_business_config_no_longer_embeds_skill_manager():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    config_start = js.index("async function renderInvestmentConfig()")
    config_end = js.index("async function renderInvestmentSkills()")
    config_body = js[config_start:config_end]

    assert "renderInvestmentComponentManager()" not in config_body
    assert "loadInvestmentComponents()" not in config_body


def test_component_prompts_are_not_in_system_config_page():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    config_groups = js[js.index("const INVEST_CONFIG_GROUPS"):js.index("const INVEST_ADMIN_ONLY_CONFIG_KEYS")]

    assert "prompt.technical_analysis" not in config_groups
    assert "prompt.rate" not in config_groups
    assert "prompt.convertible_bond" not in config_groups


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
    assert "onchange=\"refreshInvestmentContentRecords('${displayKey}', {effective_date: investmentContentHistoryEffectiveDate('${serviceType}')})\"" in content_body
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
    assert "长期有效" in upload_body
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
    assert "renderInvestmentCurrentEffective(data.current_effective, serviceType, moduleLabel, moduleKey)" in content_body
    assert "renderInvestmentContentUploadPanel(serviceType, moduleLabel, moduleKey)" in content_body
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
    assert ".investment-time-option-button" in css
    assert ".investment-time-options" in css
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


def test_daily_content_time_picker_uses_custom_option_buttons():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    panel_body = _js_function_body(js, "investmentRenderTimePickerPanel")
    options_body = _js_function_body(js, "investmentRenderTimeOptions")
    select_body = _js_function_body(js, "investmentSelectTime")

    assert "<select" not in panel_body
    assert "<option" not in panel_body
    assert "investmentRenderTimeOptions(23, hour)" in panel_body
    assert "investmentRenderTimeOptions(59, minute)" in panel_body
    assert "investment-time-option-button" in options_body
    assert "investment-time-options" in panel_body
    assert "aria-pressed" in options_body
    assert "investmentSelectedTimePart" in select_body


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
    assert "点击此区域选择${escapeHtml(label)}资料图片" in upload_body
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
    assert "investmentContentHistoryQuery(currentInvestmentContentModuleKey || serviceType, investmentTodayDate())" in helper_body
    assert "query.set('limit', '1');" in helper_body
    assert "response.contents" in helper_body
    assert "records.length > 0" in helper_body
    assert "showInvestmentConfirmDialog" in helper_body
    assert "window.confirm" not in helper_body
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
    assert "hint.textContent = enabled ? '指定失效时间' : '长期有效';" in toggle_body
    assert "if (!enabled) return '';" in value_body
    assert "return `${dateValue}T${timeValue}`;" in value_body
    assert 'type="hidden"' in time_body
    assert "investment-time-popover hidden" in time_body
    assert "investmentFormatBeijingTime(record.expires_at) || '长期有效'" in detail_body
    assert "investmentFormatBeijingTime(record?.expires_at) || '长期有效'" in current_body


def test_daily_content_effective_action_refreshes_current_preview():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    effective_body = _js_function_body(js, "effectiveInvestmentContent")
    dialog_body = _js_function_body(js, "openInvestmentContentEffectiveDialog")
    history_body = _js_function_body(js, "renderInvestmentContentHistoryGroups")

    save_body = _js_function_body(js, "saveInvestmentEffectiveDialog")
    assert "await renderInvestmentContent(targetServiceType, {effective_date: investmentContentHistoryEffectiveDate(targetServiceType)})" in save_body
    assert "await refreshInvestmentContentRecords(targetServiceType);" not in effective_body
    assert "window.prompt" not in effective_body
    assert "openInvestmentContentEffectiveDialog" in effective_body
    assert "const expiresDate = document.getElementById('investment-content-effective-expires-date')?.value || investmentAddDays(investmentTodayDate(), 1);" in save_body
    assert "const expiresAt = `${expiresDate}T00:00`;" in save_body
    assert "body: JSON.stringify({operator: 'admin', effective_date: investmentTodayDate(), expires_at: expiresAt})" in save_body
    assert "effectiveInvestmentContent('${record.content_id}', '${actionServiceType}')" in history_body
    assert "失效日期" in dialog_body
    assert "investment-content-effective-expires-date" in dialog_body
    assert "investmentAddDays(investmentTodayDate(), 1)" in dialog_body
    assert "生效日期" not in dialog_body
    assert "设置结果图片生效日期" not in dialog_body
    assert "investment-effective-help" in dialog_body
    assert "默认次日 00:00 失效" in dialog_body


def test_daily_content_current_effective_exposes_manual_expiry_actions():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    current_body = _js_function_body(js, "renderInvestmentCurrentEffective")
    invalidate_body = _js_function_body(js, "invalidateInvestmentContent")
    update_body = _js_function_body(js, "updateInvestmentContentExpiresAt")
    clear_body = _js_function_body(js, "clearInvestmentContentExpiresAt")
    dialog_body = _js_function_body(js, "openInvestmentContentExpiryDialog")
    confirm_body = _js_function_body(js, "showInvestmentConfirmDialog")
    auto_body = _js_function_body(js, "investmentShouldAutoEffectiveAfterGenerate")

    assert "investment-current-actions" in current_body
    assert "立即失效" in current_body
    assert "修改失效时间" in current_body
    assert "设为长期有效" in current_body
    assert "/api/investment/daily-content/${encodeURIComponent(contentId)}/invalidate" in invalidate_body
    assert "/api/investment/daily-content/${encodeURIComponent(contentId)}/expires-at" in update_body
    assert "body: JSON.stringify({expires_at: expiresAt})" in update_body
    assert "await updateInvestmentContentExpiresAt(contentId, '', serviceType)" in clear_body
    assert "showInvestmentConfirmDialog" in clear_body
    assert "window.confirm" not in clear_body
    assert "showInvestmentConfirmDialog" in auto_body
    assert "window.confirm" not in auto_body
    assert "investment-content-expiry-date" in dialog_body
    assert "investment-content-expiry-time" in dialog_body
    assert "investmentContentExpiryDialogDefaultValue(expiresAt)" in dialog_body
    assert "investment-confirm-dialog" in confirm_body
    assert ".investment-current-actions" in css
    assert ".investment-expiry-dialog" in css
    assert ".investment-confirm-dialog" in css


def test_daily_content_expiry_dialog_defaults_to_next_midnight_when_empty_or_past():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    default_body = _js_function_body(js, "investmentContentExpiryDialogDefaultValue")

    assert "const fallback = {date: investmentAddDays(investmentTodayDate(), 1), time: '00:00'};" in default_body
    assert "if (!local) return fallback;" in default_body
    assert "if (expiresAt && new Date(expiresAt).getTime() <= Date.now()) return fallback;" in default_body
    assert "return {date: local.slice(0, 10), time: local.slice(11, 16) || '00:00'};" in default_body


def test_business_modal_date_picker_opens_upward_without_clipping():
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert ".investment-modal .investment-date-popover" in css
    assert "bottom: calc(100% + 6px);" in css
    assert ".investment-modal:has(.investment-date-popover:not(.hidden))" in css
    assert ".investment-modal-body:has(.investment-date-popover:not(.hidden))" in css
    assert "overflow: visible !important;" in css


def test_business_console_hides_actions_by_admin_role():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "let currentInvestmentAdmin = null;" in js
    assert "function investmentCan(" in js
    assert "async function loadInvestmentAdminSession({redirectOnMissing = false} = {})" in js
    assert "const previousInvestmentAdmin = currentInvestmentAdmin;" in js
    assert "currentInvestmentAdmin = previousInvestmentAdmin;" in js
    assert "/api/investment/auth/me" in js
    assert "if (redirectOnMissing) {\n            currentInvestmentAdmin = null;\n            redirectToLogin();\n            return null;\n        }" in js
    assert "if (!currentInvestmentAdmin && redirectOnMissing)" in js
    assert "loadInvestmentAdminSession({redirectOnMissing: currentConsoleAuthenticated})" in js
    assert "if (currentConsoleAuthenticated && !currentInvestmentAdmin)" in js
    assert "investmentButtonIfCan('customers.write'" in js
    assert "investmentButtonIfCan('customers.enable'" in js
    assert "investmentButtonIfCan('customers.import'" in js
    assert "investmentButtonIfCan('customers.export'" in js
    assert "investmentButtonIfCan('content.upload'" in js
    assert "investmentButtonIfCan('audits.read', 'fa-clock-rotate-left', '操作流水'" in js
    assert "investmentTextButtonIfCan('cache.write'" in js
    assert "investmentCanView(" in js


def test_business_config_page_loads_sections_by_permission():
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


def test_business_layout_separates_table_settings_and_card_styles():
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


def test_business_config_uses_dedicated_layout_instead_of_shared_workbench():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    shell_body = _js_function_body(js, "renderInvestmentConfigShell")
    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    reply_panel_body = _js_function_body(js, "renderInvestmentConfigReplyTextsPanel")
    web_chat_body = _js_function_body(js, "renderInvestmentConfigWebChatPanel")

    combined_panels = "\n".join([stock_panel_body, reply_panel_body, web_chat_body])
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


def test_business_config_inline_handlers_are_not_html_escaped():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    config_field_body = _js_function_body(js, "renderInvestmentConfigField")

    assert "const saveHandler = `saveInvestmentConfigKey(${keyArg}, ${typeArg})`;" in config_field_body
    assert "const dirtyHandler = `markInvestmentConfigDirty(${keyArg})`;" in config_field_body
    assert "escapeHtml(`saveInvestmentConfigKey" not in config_field_body
    assert "escapeHtml(`markInvestmentConfigDirty" not in config_field_body


def test_business_config_page_uses_task_based_tabs():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    config_body = _js_function_body(js, "renderInvestmentConfig")
    shell_body = _js_function_body(js, "renderInvestmentConfigShell")
    stock_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")

    assert "let currentInvestmentConfigPanel = 'stock-data';" in js
    assert "function switchInvestmentConfigPanel(" in js
    assert "renderInvestmentConfigShell(data, stockData)" in config_body
    assert "investment-config-nav" in shell_body
    assert "investment-config-tab" in shell_body
    assert "function investmentConfigTabDefinitions(" in js
    assert "key: 'stock-data'" in js
    assert "key: 'reply-texts'" in js
    assert "key: 'generation'" not in js
    assert "key: 'directories'" not in js
    assert "key: 'web-chat'" in js
    assert "switchInvestmentConfigPanel('${escapeHtml(tab.key)}')" in shell_body
    assert "股票数据" in js
    assert "公众号回复词" in js
    assert "业务生成配置" not in js
    assert "目录配置" not in js
    assert "后台 Web 对话" in js

    assert "renderInvestmentConfigGroupByTitle('股票字典'" not in stock_body
    assert "investmentStockTools(stockData.stats || {}, configs, canReadConfig, canReadStocks)" in stock_body
    assert "renderInvestmentConfigGenerationPanel" not in js
    assert "renderInvestmentConfigGroupByTitle('技术分析参数'" not in js
    assert "title: '技术分析参数'" not in js
    assert "technical_analysis.default_chart_days" not in js
    assert "默认图表天数" not in js
    assert "renderInvestmentConfigGroupByTitle('图片生成模板'" not in js
    assert "提示词已迁移到“投研组件”页面" not in js
    assert "renderInvestmentConfigDirectoriesPanel" not in js
    assert "technical_analysis.output_dir" not in js
    assert "storage.files_dir" not in js
    assert "storage.tmp_dir" not in js
    assert "render.template_ta_path" not in js
    assert "render.template_rate_path" not in js
    assert "render.template_cb_path" not in js
    assert "render.output_dir" not in js
    assert ".investment-config-page" in css
    assert ".investment-config-nav" in css
    assert ".investment-config-tab" in css
    assert "flex-wrap: wrap;" in css


def test_business_config_subpages_use_aligned_section_layouts():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    stock_body = _js_function_body(js, "investmentStockTools")
    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    web_chat_body = _js_function_body(js, "renderInvestmentConfigWebChatPanel")

    assert "investment-config-panel" in stock_panel_body
    assert "investment-stock-data-panel" in stock_panel_body
    assert "investment-config-section" in stock_body
    assert "investment-config-panel" in web_chat_body
    assert "investment-config-section" in web_chat_body

    assert "investment-stock-module-actions investment-stock-refresh-tool" in stock_body
    assert "investment-stock-module-actions investment-stock-query-tool" in stock_body
    assert "investment-stock-workspace" in stock_body
    assert "investment-stock-overview" in stock_body
    assert "investment-stock-module-panel investment-stock-refresh-module" in stock_body
    assert "investment-stock-module-panel investment-stock-query-module" in stock_body
    assert "investment-stock-module-head" in stock_body
    assert "investment-stock-module-actions investment-stock-refresh-tool" in stock_body
    assert "investment-stock-module-actions investment-stock-query-tool" in stock_body
    assert "investment-stock-query-result-shell" in stock_body
    assert "investment-stock-log-placeholder" in stock_body
    assert "investment-stock-refresh-tool" in stock_body
    assert "investment-stock-query-tool" in stock_body
    assert "invest-stock-refresh-provider" in stock_body
    assert "invest-stock-refresh-market" in stock_body
    assert "源" in stock_body
    assert "市场" in stock_body
    assert "一键刷新全部数据源" in js
    assert "Tushare 全部" in js
    assert "AkShare 全部" in js
    assert "BaoStock 全部" in js
    assert "A股" in js
    assert "港股" in js
    assert "美股" in js
    assert "ETF（AkShare）" in js
    assert "可转债（AkShare）" in js
    assert "黄金（AkShare）" in js
    assert "国债期货（AkShare）" in js
    assert "['auto', 'auto']" not in stock_body
    assert stock_body.count("investment-inline-form investment-stock-actions") == 0
    assert "investment-panel-heading" in stock_body
    assert "investment-subtitle" not in stock_body

    assert ".investment-config-panel" in css
    assert ".investment-config-section" in css
    assert ".investment-stock-workspace" in css
    assert ".investment-stock-overview" in css
    assert ".investment-stock-module-panel" in css
    assert ".investment-stock-module-head" in css
    assert ".investment-stock-module-actions" in css
    assert ".investment-inline-field" in css
    assert ".investment-stock-refresh-log" in css
    assert "max-height: none;" in css
    assert ".investment-progress-bar" in css
    assert "grid-template-columns: 150px 170px max-content;" in css
    assert "justify-content: end;" in css
    assert "overflow-wrap: anywhere;" in css
    assert ".investment-stock-action-card" in css
    assert ".investment-stock-action-control" in css
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert "align-items: end;" in css
    assert "align-self: stretch;" in css


def test_business_stock_data_page_combines_dictionary_config_and_tools():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    stock_panel_body = _js_function_body(js, "renderInvestmentConfigStockDataPanel")
    stock_tools_body = _js_function_body(js, "investmentStockTools")

    assert "renderInvestmentConfigGroupByTitle('股票字典'" not in stock_panel_body
    assert "investmentStockTools(stockData.stats || {}, configs, canReadConfig, canReadStocks)" in stock_panel_body
    assert "investment-stock-data-panel" in stock_panel_body
    assert "investment-stock-data-card" in stock_tools_body
    assert "renderInvestmentConfigField('tushare.token', 'Tushare Token', 'text', configs['tushare.token'])" in stock_tools_body
    assert "AkShare" in stock_tools_body
    assert "BaoStock" in stock_tools_body
    assert "仅使用 Tushare 数据源" not in stock_tools_body
    assert "必须先填写并保存 Tushare Token" not in stock_tools_body
    assert "股票数据" in stock_tools_body
    assert "股票字典维护" not in stock_tools_body


def test_business_stock_refresh_supports_multiple_sources_and_conditional_tushare_token():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    refresh_body = _js_function_body(js, "refreshInvestmentStocks")
    token_body = _js_function_body(js, "investmentHasConfiguredTushareToken")
    needs_token_body = _js_function_body(js, "investmentStockRefreshNeedsTushareToken")

    assert "investmentSelectedStockRefreshSource()" in refresh_body
    assert "invest-stock-refresh-provider" in js
    assert "invest-stock-refresh-market" in js
    assert "function updateInvestmentStockRefreshMarkets(" in js
    assert "function investmentStockRefreshMarkets(" in js
    assert "investmentStockRefreshNeedsTushareToken(source) && !investmentHasConfiguredTushareToken()" in refresh_body
    assert "请先填写并保存 Tushare Token" in token_body
    assert "请先保存 Tushare Token 后再刷新" in token_body
    assert "body: JSON.stringify({source})" in refresh_body
    assert "无新增" in js
    assert "无变化" in js
    assert "renderInvestmentStockRefreshLog(data)" in refresh_body
    assert "renderInvestmentStockRefreshProgress(source)" in refresh_body
    assert "刷新进度" in js
    assert "正在依次调用数据源" in js
    assert "刷新结果：${statusText}" in js
    assert "部分成功" in js
    assert "全部失败" in js
    assert "成功 ${escapeHtml(summary.success_count" in js
    assert "失败 ${escapeHtml(summary.failed_count" in js
    assert "数据源 / 市场" in js
    assert "去重后更新" in js
    assert "失败原因" in js
    assert "investmentStockRefreshScopeLabel" in js
    assert "'tushare'" in needs_token_body
    assert "'akshare'" not in needs_token_body
    assert "'baostock'" not in needs_token_body
    assert "'all'" not in needs_token_body
    assert "'auto'" not in refresh_body


def test_business_stock_refresh_errors_use_friendly_summaries():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    refresh_body = _js_function_body(js, "refreshInvestmentStocks")
    log_body = _js_function_body(js, "renderInvestmentStockRefreshLog")
    friendly_body = _js_function_body(js, "investmentStockRefreshFriendlyError")

    assert "investmentStockRefreshFriendlyError(error.message || error)" in refresh_body
    assert "investmentStockRefreshFriendlyError(row.error)" in log_body
    assert "investmentStockRefreshFriendlyError(item)" in log_body
    assert "Tushare Token 未配置或无权限" in friendly_body
    assert "数据源连接超时" in friendly_body
    assert "数据库写入失败" in friendly_body
    assert "不支持的数据源" in friendly_body
    assert "刷新失败，请检查数据源配置或稍后重试" in friendly_body
    assert "errors.join('；')" not in log_body
    assert "String(error.message || error))}</div>" not in refresh_body


def test_business_config_page_renders_reply_text_section():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    reply_panel_body = _js_function_body(js, "renderInvestmentConfigReplyTextsPanel")
    groups_body = _js_function_body(js, "renderInvestmentReplyConfigGroups")

    assert "renderInvestmentReplyConfigGroups(data.reply_texts || {}, configs)" in reply_panel_body
    assert "const groups = replyTexts.groups || [];" in groups_body
    assert "const definitions = replyTexts.definitions || {};" in groups_body
    assert "group.keys || []" in groups_body
    assert "renderInvestmentReplyConfigField(key, definitions[key] || {}, configs[key])" in groups_body
    assert "investment-reply-list" in groups_body
    assert "公众号回复词" in js
    assert "INVEST_REPLY_CONFIG_REFERENCE_KEYS" not in js


def test_business_reply_config_fields_render_collapsed_edit_rows():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    reply_field_body = _js_function_body(js, "renderInvestmentReplyConfigField")

    assert "function renderInvestmentReplyConfigField(" in js
    assert "investment-reply-row" in reply_field_body
    assert "标题：当前回复词" not in reply_field_body
    assert "investment-reply-row-preview" in reply_field_body
    assert "investment-reply-help" in reply_field_body
    assert "data-tooltip" in reply_field_body
    assert "openInvestmentReplyConfigDialog" in reply_field_body
    assert "escapeHtml(description)" in reply_field_body
    assert "investment-config-description" not in reply_field_body
    assert ".investment-reply-list" in css
    assert ".investment-reply-row" in css
    assert ".investment-reply-help" in css
    assert "content: attr(data-tooltip);" in css
    assert "bottom: calc(100% + 8px);" in css
    assert "transform: translateX(-50%) translateY(4px);" in css
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css


def test_business_reply_config_dialog_edits_and_saves_single_value():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    dialog_body = _js_function_body(js, "openInvestmentReplyConfigDialog")
    save_body = _js_function_body(js, "saveInvestmentReplyConfigDialog")

    assert "function openInvestmentReplyConfigDialog(" in js
    assert "showInvestmentModal('编辑公众号回复词', body)" in dialog_body
    assert "textarea id=\"${safeId}\"" in dialog_body
    assert "const placeholders = Array.isArray(payload.placeholders) ? payload.placeholders : [];" in dialog_body
    assert "investment-reply-placeholders" in dialog_body
    assert "insertInvestmentReplyPlaceholder" in dialog_body
    assert "markInvestmentConfigDirty(${investmentJsString(key)})" in dialog_body
    assert "saveInvestmentReplyConfigDialog(${investmentJsString(key)})" in dialog_body
    assert "function insertInvestmentReplyPlaceholder(" in js
    assert "textarea.setSelectionRange(nextCursor, nextCursor)" in js
    assert "await saveInvestmentConfigKey(key, 'textarea')" in save_body
    assert "investmentReplyPreviewId(key)" in save_body
    assert "hideInvestmentModal()" in save_body
    assert "window.openInvestmentReplyConfigDialog = openInvestmentReplyConfigDialog;" in js
    assert "window.saveInvestmentReplyConfigDialog = saveInvestmentReplyConfigDialog;" in js
    assert "window.insertInvestmentReplyPlaceholder = insertInvestmentReplyPlaceholder;" in js
    assert ".investment-reply-dialog" in css
    assert ".investment-reply-placeholders" in css
    assert ".investment-reply-placeholder" in css
    assert ".investment-reply-dialog-field textarea" in css


def test_business_content_and_records_ui_respect_cache_and_export_permissions():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "if (viewId === 'invest-content') return renderInvestmentGeneratedContent();" in js
    assert "/api/investment/cache" in js
    assert "async function loadInvestmentGeneratedContent()" in js
    assert "investmentButtonIfCan('records.export', 'fa-download', '导出当前结果', 'exportInvestmentRequestRecordsByCurrentFilters()'" in js
    assert "investmentButtonIfCan('records.export', 'fa-file-export', '更多导出', 'openInvestmentRequestExportDialog()'" in js


def test_business_records_filters_and_export_share_toolbar_without_title_topbar():
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
    assert "exportInvestmentRequestRecordsByCurrentFilters()" in filters_body
    assert "openInvestmentRequestExportDialog()" in filters_body
    assert "exportMode: 'range'" in js
    assert ".investment-records-toolbar" in css
    assert ".investment-records-topbar" not in css
    assert ".investment-records-filter-grid {\n    display: grid;" in css
    assert "grid-template-columns: minmax(240px, 2fr) repeat(4, minmax(132px, 1fr));" in css
    assert "@media (max-width: 1024px)" in css
    assert ".investment-records-filter-grid {\n        grid-template-columns: repeat(2, minmax(0, 1fr));" in css


def test_business_request_export_dialog_is_mode_based_and_prefills_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    dialog_body = _js_function_body(js, "openInvestmentRequestExportDialog")
    panel_body = _js_function_body(js, "renderInvestmentRequestExportDialogBody")
    assert "showInvestmentModal('导出业务记录'" in dialog_body
    assert "investmentRecordsSetFilterValues('requests', {resetPage: false})" in dialog_body
    assert "initInvestmentDropdowns(document.getElementById('investment-modal-body'))" in dialog_body
    assert "公众号请求导出" in panel_body
    assert "导出当前筛选" not in panel_body
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
    assert "renderInvestmentRequestExportCurrentSummary(values)" not in panel_body
    assert "investmentRequestExportMonthOptions()" in panel_body
    assert "type=\"month\"" not in panel_body
    assert "导出会应用上方客户/输入/错误、服务、状态和日期筛选。" not in panel_body
    assert "可按下方条件缩小范围。" in panel_body
    assert "不限制日期，按下方条件导出全部请求记录。" not in panel_body
    assert "投资服务" in panel_body
    assert "客户/机构" in panel_body
    assert "Excel" in panel_body

    current_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    month_options_body = _js_function_body(js, "investmentRequestExportMonthOptions")
    assert "investmentRecordsQueryParams('requests')" in current_body
    assert "investmentRecordsSetFilterValues('requests', {resetPage: false})" in current_body
    assert "params.delete('page')" in current_body
    assert "params.delete('page_size')" in current_body
    assert "investmentExportCustomer()" not in current_body
    assert "params.set('customer'" not in current_body
    assert "请选择导出开始和结束日期" in range_body
    assert "function renderInvestmentRequestExportCurrentSummary" not in js
    assert "`${value}（本月）`" in month_options_body
    assert "本月，最近18个月" not in month_options_body
    assert "function exportInvestmentRequestRecordsFull()" in js
    assert ".investment-request-export-dialog" in css
    assert ".investment-request-export-layout" in css
    assert "grid-template-columns: minmax(190px, 0.55fr) minmax(0, 1.45fr);" in css
    assert ".investment-request-export-mode-grid" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    assert ".investment-request-export-form" in css
    assert ".investment-request-export-fields > .investment-request-export-note" in css
    assert "grid-column: 1 / -1;" in css
    assert ".investment-request-export-footer" in css


def test_business_request_export_exposes_unauthorized_and_customer_filter():
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
    assert "params.set('customer'" not in current_body
    assert "investmentExportCustomer()" not in current_body
    assert "customer: investmentExportCustomer()" in full_body
    assert "customer: investmentExportCustomer()" in range_body
    assert "customer: investmentExportCustomer()" in month_body
    assert "customer: investmentExportCustomer()" in quarter_body


def test_business_records_default_to_unbounded_history_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_start = js.index("let investmentRecordsState =")
    state_end = js.index("const INVEST_VIEW_PERMISSIONS")
    state_body = js[state_start:state_end]
    default_body = _js_function_body(js, "investmentRecordsDefaultFilters")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")

    assert "requests: {page: '1', page_size: '80', entry_type: 'external_request', date_mode: 'day', start_date: '', end_date: '', record_month: investmentTodayDate().slice(0, 7)}" in state_body
    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: '', include_invalidated: '1'}" in state_body
    assert "audits: {page: '1', page_size: '80', date_mode: 'day', start_date: '', end_date: '', record_month: investmentTodayDate().slice(0, 7)}" in state_body
    assert "start_date: ''" in default_body
    assert "end_date: ''" in default_body
    assert "market_date: ''" in default_body
    assert "data.market_dates[0]" not in load_body
    assert "timeZone: 'Asia/Shanghai'" in _js_function_body(js, "investmentTodayDate")


def test_business_request_records_support_day_month_date_filter_modes():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    query_body = _js_function_body(js, "investmentRecordsQueryParams")
    set_filter_body = _js_function_body(js, "investmentRecordsSetFilterValues")
    export_body = _js_function_body(js, "exportInvestmentRequestRecordsByCurrentFilters")

    assert "select('date_mode', '日期方式'" in filters_body
    assert "['day', '日']" in filters_body
    assert "['month', '月']" in filters_body
    assert "investmentRequestRecordMonthOptions()" in filters_body
    assert "record-month-field" in filters_body
    assert "request-date-range-field" in filters_body
    assert "changeInvestmentRequestDateMode(value)" in filters_body
    assert "function changeInvestmentRequestDateMode(" in js
    assert "function investmentRequestRecordMonthOptions(" in js
    assert "investmentRecordMonthBounds(tab, filters.record_month || investmentTodayDate().slice(0, 7))" in query_body
    assert "params.set('start_date', bounds.start)" in query_body
    assert "params.set('end_date', bounds.end)" in query_body
    assert "if (key === 'date_mode' || key === 'record_month' || key === 'effective_date') return;" in query_body
    assert "filters.date_mode === 'month'" in set_filter_body
    assert "investmentRecordsQueryParams('requests')" in export_body


def test_business_request_records_filter_toolbar_uses_grouped_layout():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")

    assert "investment-request-records-toolbar" in filters_body
    assert "investment-request-records-filter-grid" in filters_body
    assert "investment-request-search-slot" in filters_body
    assert "investment-request-filter-selects" in filters_body
    assert "investment-request-date-panel" in filters_body
    assert "investment-request-date-controls" in filters_body
    assert ".investment-records-toolbar.investment-request-records-toolbar {" in css
    assert ".investment-records-filter-grid.investment-request-records-filter-grid {" in css
    assert ".investment-request-date-panel {" in css
    assert ".investment-request-date-controls {" in css


def test_business_content_and_audit_records_filter_toolbars_use_grouped_layouts():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    query_body = _js_function_body(js, "investmentRecordsQueryParams")
    default_body = _js_function_body(js, "investmentRecordsDefaultFilters")
    set_filter_body = _js_function_body(js, "investmentRecordsSetFilterValues")

    assert "investment-content-records-toolbar" in filters_body
    assert "investment-content-records-filter-grid" in filters_body
    assert "investment-content-search-slot" in filters_body
    assert "investment-content-date-panel" in filters_body
    assert "investment-content-date-controls" in filters_body
    assert "investment-audit-records-toolbar" in filters_body
    assert "investment-audit-records-filter-grid" in filters_body
    assert "investment-audit-search-slot" in filters_body
    assert "investment-audit-date-panel" in filters_body
    assert "investment-audit-date-controls" in filters_body
    assert "`changeInvestmentRecordDateMode('${tab}', value)`" in filters_body
    assert "changeInvestmentRecordDateMode('audits', value)" in filters_body
    assert "investmentRecordMonthBounds(tab, filters.record_month || investmentTodayDate().slice(0, 7))" in query_body
    assert "if (key === 'date_mode' || key === 'record_month' || key === 'effective_date') return;" in query_body
    assert "tab === 'backendRequests' || tab === 'contents' || tab === 'audits'" in set_filter_body
    assert "date_mode: 'day'" in default_body
    assert ".investment-records-toolbar.investment-content-records-toolbar" in css
    assert ".investment-records-filter-grid.investment-content-records-filter-grid" in css
    assert ".investment-records-toolbar.investment-audit-records-toolbar" in css
    assert ".investment-records-filter-grid.investment-audit-records-filter-grid" in css


def test_business_cache_empty_date_falls_back_to_today_before_loading():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    apply_body = _js_function_body(js, "applyInvestmentCacheDate")
    normalize_body = _js_function_body(js, "investmentNormalizeCacheDateFilters")
    assert "investmentTodayDate()" in normalize_body
    assert "await loadInvestmentGeneratedContent()" in apply_body


def test_business_records_page_uses_tab_workspace_without_side_drawer():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "let investmentRecordsState =" in js
    assert "function switchInvestmentRecordsTab(" in js
    assert "function renderInvestmentRecordsShell(" in js
    assert "function openInvestmentRecordDrawer(" in js
    assert "investment-records-workspace" in js
    assert "investment-records-board" in js
    assert "investment-records-tabs" in js
    assert 'id="investment-records-pagination"' in _js_function_body(js, "renderInvestmentRecordsShell")
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
    assert "grid-template-columns: minmax(0, 1fr) !important;" in css


def test_business_records_page_uses_human_filters_customer_display_and_compact_tables():
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
    products_table = _js_function_body(js, "renderInvestmentProductsTable")
    audit_table = _js_function_body(js, "renderInvestmentOperationAuditsTable")
    assert "record.customer_display" in request_table
    assert "<th>ID</th>" not in request_table
    assert "renderInvestmentFilePreview(" not in request_table
    assert "renderInvestmentFilePreview(" not in content_table
    assert "renderInvestmentFilePreview(" not in products_table
    assert "renderInvestmentFilePreview(" not in audit_table
    assert "investmentRecordClamp(" in request_table
    assert "investmentRecordClamp(" in audit_table
    assert ".investment-records-table-shell" in css
    assert "--investment-records-list-max-height: min(620px, calc(100vh - 300px));" in css
    assert ".investment-generated-content" in css
    assert "height: var(--investment-records-list-max-height);" in css
    assert ".investment-record-clamp" in css
    assert "-webkit-line-clamp" in css
    assert ".investment-records-list {" in css
    assert "display: flex;" in css
    assert "height: var(--investment-records-list-max-height);" in css
    assert ".investment-records-table-shell {\n    flex: 1 1 auto;" in css
    assert "field('keyword', '关键字')" in js
    assert "field('action', '动作')" in js
    assert "field('operator', '操作人')" in js


def test_business_content_page_uses_date_grouped_category_view():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentDailyGeneratedContent(" in js
    assert "function renderInvestmentProductsTable(" in js
    assert "function renderInvestmentGeneratedContentCategoryDetail(" in js
    assert "function renderInvestmentCacheCategory(" not in js
    assert "function renderInvestmentCacheCompactRows(" not in js
    assert "function selectInvestmentCacheCategory(" in js
    assert "function backInvestmentCacheCategoryMenu(" in js
    assert "technical_analysis" in js
    assert "rate" in js
    assert "convertible_bond" in js
    assert "async function renderInvestmentGeneratedContent(" in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    cache_home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    category_cards_body = _js_function_body(js, "renderInvestmentGeneratedCategoryCards")
    products_body = _js_function_body(js, "renderInvestmentProductsTable")
    assert "investment-generated-content-home" in cache_home_body
    assert "investment-generated-content-entry" in category_cards_body
    assert "renderInvestmentProductsTable(visibleEntries)" not in cache_body
    assert "renderInvestmentGeneratedContentHome(investmentGeneratedCategories(visibleEntries), visibleEntries)" in cache_body
    assert "<th>业务</th><th>对象</th><th>业务日期</th><th>有效性</th><th>产物</th><th>生成时间</th><th>操作</th>" in products_body
    assert "function investmentGeneratedCategories(" in js
    assert "['technical_analysis', 'rate', 'convertible_bond'].forEach(serviceType => addCategory(serviceType));" in js
    categories_body = _js_function_body(js, "investmentGeneratedCategories")
    assert "addCategory(investmentProductBusinessType(entry), entry.service_label)" in categories_body
    assert "entry.service_type" not in categories_body
    assert "fa-puzzle-piece" in _js_function_body(js, "investmentGeneratedServiceIcon")
    assert "investmentGeneratedCategoryLabel(category)" in category_cards_body
    assert "entriesForScope.filter(entry => investmentProductBusinessType(entry) === serviceType)" in category_cards_body
    assert "const contentCount = entries.length" in category_cards_body
    assert "entry.request_count || entry.count" not in category_cards_body
    assert "entry.service_type" not in category_cards_body
    assert "investment-records-cache-layout" not in js
    assert "investment-records-date-list" not in js


def test_business_content_page_defaults_to_history_overview():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    load_body = _js_function_body(js, "loadInvestmentProducts")
    apply_body = _js_function_body(js, "applyInvestmentCacheDate")

    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: '', include_invalidated: '1'}" in js
    assert "products: {page: '1', page_size: '120', period_mode: 'day', business_date: '', keyword: '', status_category: 'all'}" in js
    assert "select('status_category', '状态', [['all', '全部'], ['active', '有效'], ['unused', '未使用'], ['invalid', '失效']])" in js
    assert "const dateRange = investmentNormalizeCacheDateFilters();" in cache_body
    assert "const selectedDate = dateRange.marketDate;" in cache_body
    assert "const visibleEntries = values;" in cache_body
    assert "selectedDate ? values.filter(entry => (entry.market_date || '') === selectedDate) : values" not in cache_body
    assert "haystack.includes(keyword)" not in cache_body
    assert "renderInvestmentProductsTable(visibleEntries)" not in cache_body
    assert "renderInvestmentRecordsPagination('cache')" not in cache_body
    assert "investmentFetchJson(`/api/investment/products?${query.toString()}`)" in load_body
    assert "investmentFetchJson(`/api/investment/cache?${query.toString()}`)" not in load_body
    assert "investmentRecordsApplyPagination('products', data.pagination)" in load_body
    assert "if (pagination) pagination.innerHTML = renderInvestmentRecordsPagination('products');" in load_body
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
    assert "investmentRecordsState.filters.products.period_mode = investmentCachePeriodMode();" in apply_body
    assert "investmentRecordsState.filters.products.start_date = range.startDate;" in apply_body
    assert "investmentRecordsState.filters.cache.period_mode = investmentCachePeriodMode();" in apply_body
    assert "investmentRecordsState.filters.cache.start_date = range.startDate;" in apply_body
    assert "query.delete('business_date')" in load_body


def test_generated_history_defaults_to_all_products_with_status_category_filter():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_body = js[js.index("let investmentRecordsState ="):js.index("const INVEST_VIEW_PERMISSIONS")]
    default_body = _js_function_body(js, "investmentRecordsDefaultFilters")
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    load_body = _js_function_body(js, "loadInvestmentProducts")

    assert "products: {page: '1', page_size: '120', period_mode: 'day', business_date: '', keyword: '', status_category: 'all'}" in state_body
    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: '', include_invalidated: '1'}" in state_body
    assert "return {page: '1', page_size: investmentRecordsDefaultPageSize(tab), period_mode: 'day', business_date: '', keyword: '', include_invalidated: '1'};" not in default_body
    assert "return {page: '1', page_size: investmentRecordsDefaultPageSize(tab), period_mode: 'day', business_date: '', keyword: '', status_category: 'all'};" in default_body
    assert "return {page: '1', page_size: investmentRecordsDefaultPageSize(tab), period_mode: 'day', market_date: '', include_invalidated: '1'};" in default_body
    assert "investmentRecordsQueryParams('products')" in load_body
    assert "query.set('include_invalidated', '1')" not in load_body
    assert "select('status_category', '状态', [['all', '全部'], ['active', '有效'], ['unused', '未使用'], ['invalid', '失效']])" in filters_body


def test_generated_history_uses_product_api_with_category_and_artifact_tree():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    load_body = _js_function_body(js, "loadInvestmentProducts")
    render_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")

    assert "investmentFetchJson(`/api/investment/products?${query.toString()}`)" in load_body
    assert "investmentFetchJson(`/api/investment/cache?${query.toString()}`)" not in load_body
    assert "renderInvestmentGeneratedContentHome(investmentGeneratedCategories(visibleEntries), visibleEntries)" in render_body
    assert "renderInvestmentProductsTable(visibleEntries)" not in render_body
    assert "investment-artifact-browser" in detail_body
    assert "renderInvestmentArtifactLazyTree(serviceType)" in detail_body
    assert "renderInvestmentArtifactViewer()" in detail_body


def test_generated_history_artifact_requests_include_status_category():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    folder_query_body = _js_function_body(js, "investmentArtifactFolderQuery")
    package_body = _js_function_body(js, "loadInvestmentArtifactPackage")

    assert "query.set('status_category', investmentRecordsState.filters.products?.status_category || 'all')" in folder_query_body
    assert "const query = new URLSearchParams({package_id: packageId, page_size: '1'});" in package_body
    assert "query.set('status_category', investmentRecordsState.filters.products?.status_category || 'all')" in package_body
    assert "investmentFetchJson(`/api/investment/artifacts?${query.toString()}`)" in package_body


def test_generated_history_artifact_viewer_meta_uses_generated_time_without_repeating_file_path():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    viewer_body = _js_function_body(js, "renderInvestmentArtifactViewer")

    assert "investmentFormatBeijingTime(pkg.generated_at || pkg.updated_at || pkg.created_at || '')" in viewer_body
    assert "file.virtual_path || '')</span>" not in viewer_body


def test_generated_history_artifact_package_nodes_can_be_invalidated():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    folder_body = _js_function_body(js, "renderInvestmentArtifactFolderNode")
    action_body = _js_function_body(js, "investmentArtifactPackageInvalidateAction")
    invalidate_body = _js_function_body(js, "invalidateInvestmentProduct")

    assert "investmentArtifactPackageInvalidateAction(node)" in folder_body
    assert "investmentCan('cache.write')" in action_body
    assert "event.stopPropagation()" in action_body
    assert "invalidateInvestmentProduct" in action_body
    assert "fa-xmark" in action_body
    assert "手动设置失效" in action_body
    assert ">失效<" not in action_body
    assert "product_id || node.package_id || node.key" in action_body
    assert "showInvestmentConfirmDialog" in invalidate_body
    assert "确认将该产物手动设置为失效？" in invalidate_body


def test_generated_history_ui_has_no_legacy_cache_loader():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    assert "renderInvestmentCacheTableLegacy" not in js
    assert "renderInvestmentRecordsCacheTab" not in js
    assert "investmentFetchJson(`/api/investment/cache?${query.toString()}`)" not in js


def test_generated_history_does_not_call_legacy_cache_endpoint():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    load_products_body = _js_function_body(js, "loadInvestmentProducts")
    assert "/api/investment/products" in load_products_body
    assert "/api/investment/cache" not in load_products_body
    assert "loadInvestmentCacheEntries" not in _js_function_body(js, "loadInvestmentRecordsTab")


def test_business_content_page_removes_redundant_topbar_and_uses_compact_history_layout():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderInvestmentGeneratedContent")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")
    artifact_tree_body = _js_function_body(js, "renderInvestmentArtifactLazyTree")

    assert "investment-content-workspace" in render_body
    assert "investment-records-topbar" not in render_body
    assert "集中查看生成后的图片、文档和缓存产物" not in render_body
    assert "investment-content-list" in render_body
    assert "investment-generated-content-title" in cache_body
    assert "investment-generated-history-empty" not in home_body
    assert "暂无历史内容" not in home_body
    assert "investment-artifact-browser" in detail_body
    assert "investment-generated-history-empty" in artifact_tree_body
    assert "选择日期范围查看目录" in artifact_tree_body
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



def test_business_generated_content_page_avoids_duplicate_date_controls_and_wide_three_column_lists():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    records_shell = _js_function_body(js, "renderInvestmentRecordsShell")
    assert "生成内容" not in records_shell
    assert "renderInvestmentRecordsTabButton('cache'" not in records_shell
    assert "当日生成" not in js
    assert "当日有关生成内容" not in js
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    home_body = _js_function_body(js, "renderInvestmentGeneratedContentHome")
    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")
    assert cache_body.count("investment-records-filter-market_date") == 1
    assert "investment-generated-content-toolbar" in cache_body
    assert "investment-cache-category-grid" not in cache_body
    assert '<span>日期范围</span>' in cache_body
    assert "investment-content-period-mode" in cache_body
    assert "investment-content-period-value" in cache_body
    assert "investmentNormalizeCacheDateFilters()" in cache_body
    assert "investment-content-filter-keyword" in cache_body
    assert "investmentCacheKeyword()" in cache_body
    assert "renderInvestmentArtifactLazyTree(serviceType)" in detail_body
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


def test_business_generated_content_page_uses_file_explorer_layout_and_range_query():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    render_body = _js_function_body(js, "renderInvestmentGeneratedContent")
    cache_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    cards_body = _js_function_body(js, "renderInvestmentGeneratedCategoryCards")
    actions_body = _js_function_body(js, "investmentGeneratedEntryActions")
    load_body = _js_function_body(js, "loadInvestmentProducts")
    products_body = _js_function_body(js, "renderInvestmentProductsTable")
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
    assert "<th>产物</th>" in products_body
    assert "<th>操作</th>" in products_body
    assert "investmentGeneratedEntryActions(product)" in products_body
    assert "investmentTextButtonIfCan('cache.write', '失效'" in actions_body
    assert "const drawerType = sourceType === 'product' ? 'product' : investmentGeneratedRecordDrawerType(product);" in products_body
    assert "openInvestmentRecordDrawer('${drawerType}'" in products_body
    assert "invalidateInvestmentProduct" in products_body
    assert "query.delete('business_date')" in load_body
    assert "/api/investment/products" in load_body
    assert "/api/investment/cache" not in load_body
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


def test_investment_records_use_unified_products_api():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    state_body = js[js.index("let investmentRecordsState ="):js.index("const INVEST_VIEW_PERMISSIONS")]
    invalidate_body = _js_function_body(js, "invalidateInvestmentProduct")
    drawer_body = _js_function_body(js, "renderInvestmentRecordDrawerBody")
    product_drawer_body = _js_function_body(js, "renderInvestmentProductDrawer")
    records_shell_body = _js_function_body(js, "renderInvestmentRecordsShell")
    switch_body = _js_function_body(js, "switchInvestmentRecordsTab")
    load_tab_body = _js_function_body(js, "loadInvestmentRecordsTab")
    records_body = _js_function_body(js, "renderInvestmentRecords")

    assert "/api/investment/products" in js
    assert "renderInvestmentProductsTable" in js
    assert "renderInvestmentCacheTableLegacy" not in js
    assert "renderInvestmentContentRecordsTable" in js
    assert "renderInvestmentProductDrawer" in js
    assert "renderInvestmentRecordsTabButton('products', '产物'" not in records_shell_body
    assert "['requests', 'backendRequests', 'contents', 'audits'].includes(tab)" in switch_body
    assert "['requests', 'backendRequests', 'contents', 'audits'].includes(tab)" in load_tab_body
    assert "['requests', 'backendRequests', 'contents', 'audits'].includes(investmentRecordsState.tab)" in records_body
    assert "tab === 'products'" not in load_tab_body
    assert "await loadInvestmentProducts()" not in load_tab_body
    assert "/api/investment/products/${encodedProductId}/invalidate" in invalidate_body
    assert "method: 'POST'" in invalidate_body
    assert "type === 'product' ? renderInvestmentProductDrawer(record)" in drawer_body
    assert "record.version_fingerprint" in product_drawer_body
    assert "record.text_content" in product_drawer_body
    assert "record.generated_text" in product_drawer_body
    assert "filters: {" in state_body
    assert "products: {page: '1', page_size: '120', period_mode: 'day', business_date: '', keyword: '', status_category: 'all'}" in state_body
    assert "pagination: {" in state_body
    assert "products: {page: 1, page_size: 120, total: 0, total_pages: 1}" in state_body
    assert "data: {" in state_body
    assert "products: {entries: [], business_dates: []}" in state_body
    assert "产物" in js


def test_business_generated_content_filters_use_month_and_year_dropdowns_with_delayed_refresh():
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


def test_business_generated_content_category_detail_is_compact():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")
    actions_body = _js_function_body(js, "investmentGeneratedEntryActions")
    assert "investment-generated-content-detail-count" in detail_body
    assert "investment-artifact-browser" in detail_body
    assert "renderInvestmentArtifactLazyTree(serviceType)" in detail_body
    assert "renderInvestmentArtifactViewer()" in detail_body
    assert "renderInvestmentCacheCategory" not in js
    assert "renderInvestmentCacheCompactRows" not in js
    assert "align-content: start;" in css
    assert ".investment-generated-content-header,\n.investment-generated-content-row" in css
    assert "min-height: 44px;" in css
    assert "padding: 0 10px;" in css
    assert "grid-template-columns: minmax(180px, 1.45fr) 84px 82px 156px 110px 86px;" in css
    assert "grid-column: 1 / 6;" in css
    assert "investmentTextButtonIfCan('cache.write'" in actions_body


def test_business_generated_content_rows_treat_daily_content_as_content_records():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    drawer_type_body = _js_function_body(js, "investmentGeneratedRecordDrawerType")
    products_body = _js_function_body(js, "renderInvestmentProductsTable")
    assert "investmentGeneratedRecordDrawerType(product)" in products_body
    assert "investmentGeneratedEntryActions(product)" in products_body
    assert "source_type === 'cache'" in js
    assert "source_type === 'content'" in js
    assert "invalidateInvestmentCache" in _js_function_body(js, "investmentGeneratedEntryActions")
    assert "return 'content';" in drawer_type_body
    assert "openInvestmentRecordDrawer('${drawerType}'" in products_body


def test_business_generated_content_drawer_hides_low_value_long_cache_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "选择记录查看详情" in js
    assert "选择一条记录查看完整详情" not in js
    drawer_body = _js_function_body(js, "renderInvestmentCacheDrawer")
    assert "缓存 Key" not in drawer_body
    assert "缓存字段" not in drawer_body
    assert "record.cache_key" not in drawer_body
    assert "record.output_files" not in drawer_body
    assert "生成内容详情" in js


def test_business_content_drawer_shows_source_images_like_output_image():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    drawer_body = _js_function_body(js, "renderInvestmentContentDrawer")

    assert "输入图片" in drawer_body
    assert "renderInvestmentSourcePreviews(investmentContentSourceFiles(record))" in drawer_body
    assert "输出图片" in drawer_body
    assert "investmentContentOutputImage(record)" in drawer_body
    assert drawer_body.index("输入图片") < drawer_body.index("输出图片")


def test_business_file_links_prefer_file_id_urls_over_absolute_paths():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    file_url_body = _js_function_body(js, "investmentFileUrl")
    links_body = _js_function_body(js, "investmentFileLinks")

    assert "if (file.file_url) return file.file_url;" in file_url_body
    assert "file.file_id || file.id" in file_url_body
    assert "`/api/file?id=${encodeURIComponent(file.file_id || file.id)}`" in file_url_body
    assert "investmentFileUrl(file)" in links_body
    assert "investmentImageUrl(path)" not in links_body


def test_business_request_drawer_keeps_error_details_and_audit_fields():
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


def test_business_request_drawer_shows_request_event_timeline():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    drawer_body = _js_function_body(js, "renderInvestmentRequestDrawer")
    timeline_body = _js_function_body(js, "renderInvestmentRequestEventTimeline")
    open_body = _js_function_body(js, "openInvestmentRecordDrawer")

    assert "renderInvestmentRequestEventTimeline(record.events || [])" in drawer_body
    assert "请求流程" in timeline_body
    assert "event.event_type" in timeline_body
    assert "event.content" in timeline_body
    assert "investmentFormatBeijingTime(event.created_at)" in timeline_body
    assert "showInvestmentRequestDetail" not in open_body


def test_business_record_detail_buttons_escape_apostrophes_in_encoded_records():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    encoded_body = _js_function_body(js, "investmentEncodedRecord")
    request_table = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    backend_table = _js_function_body(js, "renderInvestmentBackendRequestRecordsTable")

    assert "replace(/[!'()*]/g" in encoded_body
    assert "openInvestmentRecordDrawer('request', '${investmentEncodedRecord(record)}')" in request_table
    assert "openInvestmentRecordDrawer('backendRequest', '${investmentEncodedRecord(record)}')" in backend_table


def test_business_records_page_links_to_entry_filtered_business_records():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    table_body = _js_function_body(js, "renderInvestmentBackendRequestRecordsTable")
    drawer_body = _js_function_body(js, "renderInvestmentBackendRequestDrawer")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")
    nav_body = _js_function_body(js, "renderInvestmentRecordsShell")

    assert "entry_type=external_request" in js
    assert "entry_type=internal_call" in js
    assert "/api/investment/records/requests" in load_body
    assert "/api/investment/records/internal-calls" not in load_body
    assert "公众号入口" in nav_body
    assert "后台入口" in nav_body
    assert 'href="#invest-records/${tab}"' in js
    assert "renderInvestmentRecordsTabButton('backendRequests', '后台入口'" in js
    assert "record.request_id" in table_body
    assert "record.call_id" not in table_body
    assert "record.actor_name" in table_body
    assert "record.actor_type" in table_body
    assert "record.action_type" in table_body
    assert "record.status" in table_body
    assert "record.output_files" in table_body
    assert "record.elapsed_ms" in table_body
    assert "业务记录 ID" in drawer_body
    assert "record.request_id" in drawer_body
    assert "record.actor_role" in drawer_body
    assert "record.raw_input" in drawer_body
    assert "record.output_files" in drawer_body


def test_business_content_records_show_input_prompt():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    history_body = _js_function_body(js, "renderInvestmentContentHistoryGroups")
    content_table_body = _js_function_body(js, "renderInvestmentContentRecordsTable")
    content_detail_body = _js_function_body(js, "showInvestmentContentDetail")
    records_drawer_body = _js_function_body(js, "renderInvestmentContentDrawer")

    assert "输入提示词" not in history_body
    assert "record.input_prompt" not in history_body
    assert "输入提示词" not in content_table_body
    assert "record.input_prompt" not in content_table_body
    assert "输入提示词" in content_detail_body
    assert "record.input_prompt" in content_detail_body
    assert "输入提示词" in records_drawer_body
    assert "record.input_prompt" in records_drawer_body


def test_business_audit_drawer_shows_before_and_after_state():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    drawer_body = _js_function_body(js, "renderInvestmentAuditDrawer")

    assert "修改前" in drawer_body
    assert "修改后" in drawer_body
    assert "record.before_state" in drawer_body
    assert "record.after_state" in drawer_body


def test_business_records_times_are_formatted_as_beijing_time():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function investmentFormatBeijingTime(" in js
    assert "Asia/Shanghai" in js
    request_body = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    products_body = _js_function_body(js, "renderInvestmentProductsTable")
    audit_body = _js_function_body(js, "renderInvestmentOperationAuditsTable")
    assert "investmentFormatBeijingTime(record.created_at)" in request_body
    assert "investmentFormatBeijingTime(product.created_at || product.updated_at || product.effective_at)" in products_body
    assert "investmentFormatBeijingTime(audit.created_at)" in audit_body


def test_business_console_uses_beijing_time_for_all_backend_timestamps():
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
    component_card_body = _js_function_body(js, "renderInvestmentComponentCard")

    assert "investmentFormatBeijingTime(stats.latest_updated_at || '')" in stock_stats_body
    assert "investmentFormatBeijingTime(stock.updated_at || '')" in stock_rows_body
    assert "investmentFormatBeijingDate(user.auth_end_at || '')" in users_body
    assert "investmentUtcToBeijingDateTimeParts(user.auth_start_at || '')" not in user_dialog_body
    assert "investmentUtcToBeijingDateTimeParts(user.auth_end_at || '')" not in user_dialog_body
    assert "investmentFormatBeijingDate(user.auth_start_at || '')" in user_dialog_body
    assert "investmentFormatBeijingDate(user.auth_end_at || '')" in user_dialog_body
    assert "investmentUtcToBeijingDatetimeLocal(user.auth_start_at || '')" in fill_user_body
    assert "investmentUtcToBeijingDatetimeLocal(user.auth_end_at || '')" in fill_user_body
    assert "investmentBeijingDateTimeToUtc(authStartDate, '00:00')" in save_user_body
    assert "investmentBeijingDateTimeToUtc(authEndDate, '00:00')" in save_user_body
    assert "investmentFormatBeijingTime(row.auth_start_at || '')" in import_result_body
    assert "investmentFormatBeijingTime(row.auth_end_at || '')" in import_result_body
    assert "investmentFormatBeijingTime(record?.effective_at)" in current_content_body
    assert "investmentFormatBeijingTime(record.created_at)" in content_table_body
    assert "investmentFormatBeijingTime(record.created_at)" in content_detail_body
    assert "investmentFormatBeijingTime(record.effective_at)" in content_detail_body
    assert "investmentFormatBeijingTime(record.archived_at)" in content_detail_body
    assert "investmentFormatBeijingTime(audit.created_at)" in content_audits_body
    assert "investmentFormatBeijingTime(active.uploaded_at)" not in component_card_body


def test_business_records_tabs_use_independent_loaders_and_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "function renderInvestmentRecordsFilters(" in js
    assert "function investmentSelected(" in js
    assert "function investmentRecordsFilterValue(" in js
    assert "function loadInvestmentRecordsTab(" in js
    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")
    content_load_body = _js_function_body(js, "loadInvestmentGeneratedContent")
    assert "/api/investment/records/requests" in load_body
    assert "/api/investment/records/internal-calls" not in load_body
    assert "entry_type=internal_call" in load_body
    assert "/api/investment/records/contents" in load_body
    assert "loadInvestmentProducts()" in content_load_body
    assert "/api/investment/products" in _js_function_body(js, "loadInvestmentProducts")
    assert "/api/investment/cache" not in _js_function_body(js, "loadInvestmentProducts")
    assert "/api/investment/audits" in load_body
    assert "investmentRecordsState.filters[tab]" in js
    assert "['invalidated', '已失效']" in filters_body
    assert "renderInvestmentRecordsTabButton('requests', '公众号入口'" in js
    assert "renderInvestmentRecordsTabButton('backendRequests', '后台入口'" in js
    assert "renderInvestmentRecordsTabButton('contents', '后台内容生成'" in js
    assert "renderInvestmentRecordsTabButton('audits', '操作流水'" in js


def test_request_records_service_column_prefers_module_label():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    request_table_body = _js_function_body(js, "renderInvestmentRequestRecordsTable")
    backend_table_body = _js_function_body(js, "renderInvestmentBackendRequestRecordsTable")
    filter_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    records_body = _js_function_body(js, "renderInvestmentRecords")

    assert "investmentRecordServiceLabel(record)" in request_table_body
    assert "investmentRecordServiceLabel(record)" in backend_table_body
    assert "investmentRecordServiceOptions(false)" in filter_body
    assert "ensureInvestmentComponentsLoaded()" in records_body
    assert "${investmentServiceLabel(record.service_type)}</td>" not in request_table_body


def test_business_records_tabs_keep_independent_pagination_state():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    state_start = js.index("let investmentRecordsState =")
    state_end = js.index("const INVEST_VIEW_PERMISSIONS")
    state_body = js[state_start:state_end]
    assert "requests: {page: '1', page_size: '80', entry_type: 'external_request', date_mode: 'day', start_date: '', end_date: '', record_month: investmentTodayDate().slice(0, 7)}" in state_body
    assert "backendRequests: {page: '1', page_size: '80', entry_type: 'internal_call', keyword: '', date_mode: 'day', start_date: '', end_date: '', record_month: investmentTodayDate().slice(0, 7)}" in state_body
    assert "contents: {page: '1', page_size: '80', keyword: '', date_mode: 'day', start_date: '', end_date: '', record_month: investmentTodayDate().slice(0, 7)}" in state_body
    assert "cache: {page: '1', page_size: '120', period_mode: 'day', market_date: '', include_invalidated: '1'}" in state_body
    assert "audits: {page: '1', page_size: '80', date_mode: 'day', start_date: '', end_date: '', record_month: investmentTodayDate().slice(0, 7)}" in state_body

    switch_body = _js_function_body(js, "switchInvestmentRecordsTab")
    assert "investmentRecordsState.filters[tab]" in switch_body
    assert "page: '1'" not in switch_body


def test_business_records_filters_reset_page_and_queries_page_size():
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
    assert "const pagination = document.getElementById('investment-records-pagination')" in load_body
    assert "if (pagination) pagination.innerHTML = renderInvestmentRecordsPagination(tab);" in load_body
    assert "html = `${renderInvestmentRequestRecordsTable" not in load_body
    assert "investmentRecordsState.pagination[tab]" in load_body
    assert "renderInvestmentRecordsPagination(tab)" in load_body


def test_generated_content_keyword_search_is_backend_query_not_page_filter():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    apply_body = _js_function_body(js, "applyInvestmentCacheDate")
    render_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")

    assert "investmentRecordsState.filters.products.keyword" in apply_body
    assert "investmentRecordsState.filters.cache.keyword" in apply_body
    assert "investmentRecordsQueryParams('products')" in _js_function_body(js, "loadInvestmentProducts")
    assert "haystack.includes(keyword)" not in render_body
    assert "values.filter(entry => {" not in render_body


def test_business_records_pagination_controls_are_rendered():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    generated_body = _js_function_body(js, "renderInvestmentGeneratedContent")

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
    assert '<div id="investment-records-pagination"></div>' in generated_body
    assert ".investment-records-pagination" in css
    assert ".investment-records-page-size" in css


def test_business_cache_category_selection_uses_server_side_filtering():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    select_body = _js_function_body(js, "selectInvestmentCacheCategory")
    back_body = _js_function_body(js, "backInvestmentCacheCategoryMenu")

    assert "investmentRecordsState.filters.products.service_type = serviceType" in select_body
    assert "investmentRecordsState.filters.products.page = '1'" in select_body
    assert "investmentRecordsState.filters.cache.service_type" not in select_body
    assert "scheduleInvestmentCacheFilterRefresh()" in select_body
    assert "await loadInvestmentGeneratedContent()" not in select_body
    assert "delete investmentRecordsState.filters.products.service_type" in back_body
    assert "investmentRecordsState.filters.products.page = '1'" in back_body
    assert "investmentRecordsState.filters.cache.service_type" not in back_body
    assert "await loadInvestmentGeneratedContent()" in back_body


def test_business_content_and_cache_date_filters_are_exposed():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "invest-content-history-effective-date-rate" in js
    assert "invest-content-history-effective-date-convertible_bond" in js
    assert "function investmentContentHistoryEffectiveDate(serviceType)" in js
    assert "investmentContentHistoryEffectiveDate(serviceType)" in js
    assert "refreshInvestmentContentRecords(serviceType, {effective_date: investmentContentHistoryEffectiveDate(serviceType)})" in js
    assert "investment-records-filter-market_date" in js
    assert "investmentCacheMarketDate()" in js
    assert "investmentFetchJson(`/api/investment/products?${query.toString()}`)" in js
    assert "investmentGeneratedOutputState(entry)" in js
    assert "investmentRecordFileSummary(entry.output_files || [])" not in js


def test_business_content_history_date_filters_are_scoped_by_service_type():
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
    assert "investmentContentHistoryEffectiveDate(targetServiceType)" in refresh_records_body


def test_business_health_ui_exposes_manual_full_check_and_levels():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    html = CHAT_HTML.read_text(encoding="utf-8")
    health_start = html.index('id="view-invest-health"')
    logs_start = html.index('id="view-logs"', health_start)
    health_view = html[health_start:logs_start]
    health_body = _js_function_body(js, "renderInvestmentHealth")

    assert "async function renderInvestmentHealth(runSmoke = false)" in js
    assert "/api/investment/health?smoke=1" in js
    assert "运行完整检查" in js
    assert "window.runInvestmentFullHealthCheck" in js
    assert "check.level" in js
    assert "warning" in js
    assert "不可上线" in js
    assert "w-full max-w-[1600px] mx-auto" in health_view
    assert "invest-health-shell" in health_view
    assert "invest-health-placeholder" in health_view
    assert "investment-health-page" in health_body
    assert "investment-health-header" in health_body
    assert "healthDescriptions" in health_body
    assert "renderInvestmentHealthPendingRows" in js
    assert "startInvestmentHealthProgress" in js
    assert "stopInvestmentHealthProgress" in js
    assert "setInterval" in _js_function_body(js, "startInvestmentHealthProgress")
    assert "clearInterval" in _js_function_body(js, "stopInvestmentHealthProgress")
    assert "investment-health-checking" in health_body
    assert "检查中..." in js
    assert "healthRunning" in health_body
    assert "disabled" in health_body
    assert "完整检查中..." in health_body
    assert "business_database: '业务数据库连接是否可用，是后台记录、配置和任务运行的基础。'" in health_body
    assert "const note = healthDescriptions[check.name] || '该检查项用于确认对应依赖或配置是否满足上线要求。';" in health_body
    assert '<span class="investment-health-info"' in health_body
    assert "<th>检查项</th><th>状态</th><th>详情</th>" in health_body
    assert "检查项名称" not in health_body
    assert "检查结果级别" not in health_body
    assert "后端返回的诊断说明" not in health_body
    assert "<span>健康检查</span>" not in health_body
    assert "上线前检查" not in health_body
    assert "检查项详情" not in health_body
    assert ".investment-health-page" in css
    assert ".investment-health-header" in css
    assert ".investment-health-info" in css
    assert ".investment-health-row.checking" in css
    assert "@keyframes investment-health-pulse" in css
    assert ".investment-health-info::after" not in css
    assert ".investment-health-page .investment-health-summary" in css
    assert ".investment-table-wrap.investment-table-scroll" in css
    assert ".invest-health-placeholder" in css
    assert ".investment-health-summary.warning" in css
    assert ".investment-badge.warning" in css


def test_preregistered_customer_routes_are_registered():
    from channel.web.investment_handlers import INVESTMENT_API_URLS

    urls = "\n".join(INVESTMENT_API_URLS)
    assert "/api/investment/users/(.*)/unbind-openid" in urls
    assert "/api/investment/users/(.*)/delete" in urls
    assert "/api/investment/users/import-result.xlsx" in urls


def test_preregistered_customer_web_api_wiring_exists():
    source = Path("channel/web/web_channel.py").read_text(encoding="utf-8")

    assert "bind_status" in source
    assert "generate_customer_activation_code" in source
    assert "activation_code" in source
    assert "activation_batch_id" in source
    assert "import_users_with_activation_codes" in source
    assert "result_download_url" in source
    assert "export_users_import_result_xlsx" in source
    assert "class InvestmentUserUnbindOpenidHandler" in source
    assert "unbind_customer_openid" in source
    assert "class InvestmentUserDeleteHandler" in source
    assert "delete_user_by_id" in source


def test_preregistered_customer_ui_wiring_exists():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "bind_status" in js
    assert "待绑定" in js
    assert "unbindInvestmentUserOpenid" in js
    assert "deleteInvestmentUser" in js
    assert "删除" in js
    assert "import-result.xlsx" in js
    assert "activation_code" in js
    assert "OpenID 可空" in js
    assert "下载含激活码 Excel" in js
    assert "客户专属激活码" in js


def test_preregistered_customer_creation_shows_activation_code_dialog():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    save_body = _js_function_body(js, "saveInvestmentUser")
    dialog_body = _js_function_body(js, "showInvestmentActivationCodeResultDialog")

    assert "data.activation_code" in save_body
    assert "showInvestmentActivationCodeResultDialog(data)" in save_body
    assert "showInvestmentModal('客户专属激活码'" in dialog_body
    assert "invest-user-created-activation-code" in dialog_body
    assert "activation_batch_id" in dialog_body
    assert "copyInvestmentActivationCodeFromDialog()" in dialog_body
    assert "window.copyInvestmentActivationCodeFromDialog = copyInvestmentActivationCodeFromDialog" in js


def test_activation_code_ui_marks_customer_bound_codes():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    table_body = _js_function_body(js, "renderInvestmentActivationCodesTable")

    assert "activation_mode === 'preregistered'" in table_body
    assert "客户码" in table_body
    assert "通用码" in table_body
    assert "customer_id" in table_body
    assert "subscription_end_at" in table_body
    assert "<th>类型</th>" in table_body
    assert "<th>客户ID</th>" in table_body
    assert "<th>订阅/结束</th>" in table_body
