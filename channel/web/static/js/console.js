/* =====================================================================
   智能投研辅助系统 Console - Main Application Script
   ===================================================================== */

// =====================================================================
// Version — fetched from backend (single source: /VERSION file)
// =====================================================================
let APP_VERSION = '';

// =====================================================================
// i18n
// =====================================================================
const I18N = {
    zh: {
        console: '控制台',
        nav_chat: '对话', nav_manage: '管理', nav_monitor: '监控',
        menu_chat: '对话', menu_config: '配置', menu_skills: '技能', menu_channels: '通道',
        menu_logs: '日志',
        menu_invest_users: '用户管理', menu_invest_daily_content: '投资内容',
        menu_invest_content: '内容',
        menu_invest_records: '业务记录', menu_invest_skills: '投研组件', menu_invest_config: '系统配置', menu_invest_health: '健康检查',
        knowledge_title: '知识库', knowledge_desc: '浏览和探索你的知识库',
        knowledge_tab_docs: '文档', knowledge_tab_graph: '图谱',
        knowledge_loading: '加载知识库中...', knowledge_loading_desc: '知识页面将显示在这里',
        knowledge_select_hint: '选择一个文档查看', knowledge_empty_hint: '暂无知识页面',
        knowledge_empty_guide: '在对话中发送文档、链接或主题给 Agent，它会自动整理到你的知识库中。',
        knowledge_go_chat: '开始对话',
        welcome_subtitle: '围绕投研内容生成、用户运营、业务记录和系统配置，提供统一辅助工作台',
        example_sys_title: '投研内容', example_sys_text: '生成并维护每日投研内容',
        example_task_title: '用户运营', example_task_text: '管理投研服务用户与权限状态',
        example_code_title: '业务记录', example_code_text: '查看请求、内容和操作留痕',
        example_knowledge_title: '历史内容', example_knowledge_text: '检索历史投研图片和素材包',
        example_skill_title: '系统配置', example_skill_text: '配置投研服务参数和回复词',
        example_web_title: '健康检查', example_web_text: '检查服务配置和上线状态',
        input_placeholder: '输入消息，或输入 / 使用指令',
        config_title: '配置管理', config_desc: '管理模型和 Agent 配置',
        config_model: '模型配置', config_agent: 'Agent 配置',
        config_channel: '通道配置',
        config_agent_enabled: 'Agent 模式',
        config_max_tokens: '最大上下文 Token', config_max_tokens_hint: '对话中 Agent 能输入的最大 Token 长度，超过后会智能压缩处理',
        config_max_turns: '最大记忆轮次', config_max_turns_hint: '一问一答为一轮，超过后会智能压缩处理',
        config_max_steps: '最大执行步数', config_max_steps_hint: '单次对话中 Agent 最多调用工具的次数',
        config_enable_thinking: '深度思考', config_enable_thinking_hint: '是否启用深度思考模式',
        config_channel_type: '通道类型',
        config_provider: '模型厂商', config_model_name: '模型',
        config_custom_model_hint: '输入自定义模型名称',
        config_save: '保存', config_saved: '已保存',
        config_save_error: '保存失败',
        config_custom_option: '自定义...',
        config_custom_tip: '接口需遵循 OpenAI API 协议',
        config_security: '安全设置', config_password: '访问密码',
        config_password_hint: '留空则不启用密码保护',
        config_password_changed: '密码已更新，请重新登录',
        config_password_cleared: '密码已清除',
        skills_title: '技能管理', skills_desc: '查看、启用或禁用 Agent 工具和技能', skills_hub_btn: '探索技能广场',
        skills_loading: '加载技能中...', skills_loading_desc: '技能加载后将显示在此处',
        tools_section_title: '内置工具', tools_loading: '加载工具中...',
        skills_section_title: '技能', skill_enable: '启用', skill_disable: '禁用',
        skill_toggle_error: '操作失败，请稍后再试',
        memory_title: '记忆管理', memory_desc: '查看 Agent 记忆文件和内容',
        memory_tab_files: '记忆文件', memory_tab_dreams: '梦境日记',
        memory_loading: '加载记忆文件中...', memory_loading_desc: '记忆文件将显示在此处',
        memory_back: '返回列表',
        memory_col_name: '文件名', memory_col_type: '类型', memory_col_size: '大小', memory_col_updated: '更新时间',
        channels_title: '通道管理', channels_desc: '管理已接入的消息通道',
        channels_add: '接入通道', channels_disconnect: '断开',
        channels_save: '保存配置', channels_saved: '已保存', channels_save_error: '保存失败',
        channels_restarted: '已保存并重启',
        channels_connect_btn: '接入', channels_cancel: '取消',
        channels_select_placeholder: '选择要接入的通道...',
        channels_empty: '暂未接入任何通道', channels_empty_desc: '点击右上角「接入通道」按钮开始配置',
        channels_disconnect_confirm: '确认断开该通道？配置将保留但通道会停止运行。',
        channels_connected: '已接入', channels_connecting: '接入中...',
        weixin_scan_title: '微信扫码登录', weixin_scan_desc: '请使用微信扫描下方二维码',
        weixin_scan_loading: '正在获取二维码...', weixin_scan_waiting: '等待扫码...',
        weixin_scan_scanned: '已扫码，请在手机上确认', weixin_scan_expired: '二维码已过期，正在刷新...',
        weixin_scan_success: '登录成功，正在启动通道...', weixin_scan_fail: '获取二维码失败',
        weixin_qr_tip: '二维码约2分钟后过期',
        wecom_scan_btn: '扫码创建企微机器人', wecom_scan_desc: '使用企业微信扫码，一键创建智能机器人',
        wecom_scan_success: '创建成功，正在启动通道...',
        wecom_scan_fail: '创建失败',
        wecom_mode_scan: '扫码接入', wecom_mode_manual: '手动填写',
        feishu_scan_btn: '一键创建飞书应用',
        feishu_scan_desc: '使用飞书 App 扫码，自动创建应用并预置全部权限与事件订阅',
        feishu_scan_replace_desc: '使用飞书 App 扫码创建新机器人，将覆盖当前的 App ID / Secret',
        feishu_scan_loading: '正在向飞书申请二维码...',
        feishu_scan_waiting: '等待扫码...',
        feishu_scan_tip: '二维码 10 分钟内有效，仅供一次扫描',
        feishu_scan_open_link: '或点击此处在浏览器中打开',
        feishu_scan_success: '应用创建成功，正在启动通道...',
        feishu_scan_expired: '二维码已过期，请重试',
        feishu_scan_denied: '已取消授权',
        feishu_scan_fail: '创建失败',
        feishu_scan_retry: '重试',
        feishu_mode_scan: '扫码创建', feishu_mode_manual: '手动填写',
        tasks_title: '定时任务', tasks_desc: '查看和管理定时任务',
        tasks_coming: '即将推出', tasks_coming_desc: '定时任务管理功能即将在此提供',
        logs_title: '日志', logs_desc: '实时日志输出 (run.log)',
        logs_live: '实时', logs_coming_msg: '日志流即将在此提供。将连接 run.log 实现类似 tail -f 的实时输出。',
        new_chat: '新对话',
        session_history: '历史会话',
        auth_logged_in: '已登录',
        auth_logout: '退出登录',
        role_admin: '管理员',
        role_content_operator: '内容运营',
        role_technical_operator: '技术运营',
        today: '今天', yesterday: '昨天', earlier: '更早',
        delete_session_confirm: '确认删除该会话？所有消息将被清除。',
        delete_session_title: '删除会话',
        untitled_session: '新对话',
        context_cleared: '— 以上内容已从上下文中移除 —',
        tip_new_chat: '新建对话',
        tip_clear_context: '清除上下文',
        tip_attach: '添加附件',
        attach_menu_file: '上传文件',
        attach_menu_folder: '上传文件夹',
        confirm_yes: '确认',
        confirm_cancel: '取消',
        error_send: '发送失败，请稍后再试。', error_timeout: '请求超时，请再试一次。',
        thinking_in_progress: '思考中...', thinking_done: '已深度思考', thinking_duration: '耗时',
    },
    en: {
        console: 'Console',
        nav_chat: 'Chat', nav_manage: 'Management', nav_monitor: 'Monitor',
        menu_chat: 'Chat', menu_config: 'Config', menu_skills: 'Skills', menu_channels: 'Channels',
        menu_logs: 'Logs',
        menu_invest_users: 'Users', menu_invest_daily_content: 'Investment Content',
        menu_invest_content: 'Content',
        menu_invest_records: 'Records', menu_invest_skills: 'Research Components', menu_invest_config: 'Investment Config', menu_invest_health: 'Health',
        knowledge_title: 'Knowledge', knowledge_desc: 'Browse and explore your knowledge base',
        knowledge_tab_docs: 'Documents', knowledge_tab_graph: 'Graph',
        knowledge_loading: 'Loading knowledge base...', knowledge_loading_desc: 'Knowledge pages will be displayed here',
        knowledge_select_hint: 'Select a document to view', knowledge_empty_hint: 'No knowledge pages yet',
        knowledge_empty_guide: 'Send documents, links or topics to the agent in chat, and it will automatically organize them into your knowledge base.',
        knowledge_go_chat: 'Start a conversation',
        welcome_subtitle: 'A unified workspace for investment research content, user operations, business records, and system configuration.',
        example_sys_title: 'Research Content', example_sys_text: 'Generate and maintain daily research content',
        example_task_title: 'User Operations', example_task_text: 'Manage research service users and permissions',
        example_code_title: 'Business Records', example_code_text: 'Review requests, content, and operation logs',
        example_knowledge_title: 'Content History', example_knowledge_text: 'Find historical research images and packages',
        example_skill_title: 'System Config', example_skill_text: 'Configure research service parameters and reply text',
        example_web_title: 'Health Check', example_web_text: 'Check service configuration and launch readiness',
        input_placeholder: 'Type a message, or press / for commands',
        config_title: 'Configuration', config_desc: 'Manage model and agent settings',
        config_model: 'Model Configuration', config_agent: 'Agent Configuration',
        config_channel: 'Channel Configuration',
        config_agent_enabled: 'Agent Mode',
        config_max_tokens: 'Max Context Tokens', config_max_tokens_hint: 'Max tokens the Agent can input per conversation, auto-compressed when exceeded',
        config_max_turns: 'Max Memory Turns', config_max_turns_hint: 'One Q&A pair = one turn, auto-compressed when exceeded',
        config_max_steps: 'Max Steps', config_max_steps_hint: 'Max tool calls the Agent can make in a single conversation',
        config_enable_thinking: 'Deep Thinking', config_enable_thinking_hint: 'Enable deep thinking mode',
        config_channel_type: 'Channel Type',
        config_provider: 'Provider', config_model_name: 'Model',
        config_custom_model_hint: 'Enter custom model name',
        config_save: 'Save', config_saved: 'Saved',
        config_save_error: 'Save failed',
        config_custom_option: 'Custom...',
        config_custom_tip: 'API must follow OpenAI protocol.',
        config_security: 'Security', config_password: 'Password',
        config_password_hint: 'Leave empty to disable password protection',
        config_password_changed: 'Password updated, please re-login',
        config_password_cleared: 'Password cleared',
        skills_title: 'Skills', skills_desc: 'View, enable, or disable agent tools and skills', skills_hub_btn: 'Skill Hub',
        skills_loading: 'Loading skills...', skills_loading_desc: 'Skills will be displayed here after loading',
        tools_section_title: 'Built-in Tools', tools_loading: 'Loading tools...',
        skills_section_title: 'Skills', skill_enable: 'Enable', skill_disable: 'Disable',
        skill_toggle_error: 'Operation failed, please try again',
        memory_title: 'Memory', memory_desc: 'View agent memory files and contents',
        memory_tab_files: 'Memory Files', memory_tab_dreams: 'Dream Diary',
        memory_loading: 'Loading memory files...', memory_loading_desc: 'Memory files will be displayed here',
        memory_back: 'Back to list',
        memory_col_name: 'Filename', memory_col_type: 'Type', memory_col_size: 'Size', memory_col_updated: 'Updated',
        channels_title: 'Channels', channels_desc: 'Manage connected messaging channels',
        channels_add: 'Connect', channels_disconnect: 'Disconnect',
        channels_save: 'Save', channels_saved: 'Saved', channels_save_error: 'Save failed',
        channels_restarted: 'Saved & Restarted',
        channels_connect_btn: 'Connect', channels_cancel: 'Cancel',
        channels_select_placeholder: 'Select a channel to connect...',
        channels_empty: 'No channels connected', channels_empty_desc: 'Click the "Connect" button above to get started',
        channels_disconnect_confirm: 'Disconnect this channel? Config will be preserved but the channel will stop.',
        channels_connected: 'Connected', channels_connecting: 'Connecting...',
        weixin_scan_title: 'WeChat QR Login', weixin_scan_desc: 'Scan the QR code below with WeChat',
        weixin_scan_loading: 'Loading QR code...', weixin_scan_waiting: 'Waiting for scan...',
        weixin_scan_scanned: 'Scanned, please confirm on your phone', weixin_scan_expired: 'QR code expired, refreshing...',
        weixin_scan_success: 'Login successful, starting channel...', weixin_scan_fail: 'Failed to load QR code',
        weixin_qr_tip: 'QR code expires in ~2 minutes',
        wecom_scan_btn: 'Scan to Create WeCom Bot', wecom_scan_desc: 'Scan with WeCom to create a bot instantly',
        wecom_scan_success: 'Bot created, starting channel...',
        wecom_scan_fail: 'Bot creation failed',
        wecom_mode_scan: 'Scan QR', wecom_mode_manual: 'Manual',
        feishu_scan_btn: 'One-click Create Feishu App',
        feishu_scan_desc: 'Scan with Feishu App to create an app with all required permissions pre-configured',
        feishu_scan_replace_desc: 'Scan with Feishu App to create a new bot — will overwrite the current App ID / Secret',
        feishu_scan_loading: 'Requesting QR code from Feishu...',
        feishu_scan_waiting: 'Waiting for scan...',
        feishu_scan_tip: 'QR code expires in 10 minutes, single use only',
        feishu_scan_open_link: 'Or click here to open in browser',
        feishu_scan_success: 'App created, starting channel...',
        feishu_scan_expired: 'QR code expired, please retry',
        feishu_scan_denied: 'Authorization cancelled',
        feishu_scan_fail: 'App creation failed',
        feishu_scan_retry: 'Retry',
        feishu_mode_scan: 'Scan QR', feishu_mode_manual: 'Manual',
        tasks_title: 'Scheduled Tasks', tasks_desc: 'View and manage scheduled tasks',
        tasks_coming: 'Coming Soon', tasks_coming_desc: 'Scheduled task management will be available here',
        logs_title: 'Logs', logs_desc: 'Real-time log output (run.log)',
        logs_live: 'Live', logs_coming_msg: 'Log streaming will be available here. Connects to run.log for real-time output similar to tail -f.',
        new_chat: 'New Chat',
        session_history: 'History',
        auth_logged_in: 'Signed in',
        auth_logout: 'Logout',
        role_admin: 'Admin',
        role_content_operator: 'Content Operator',
        role_technical_operator: 'Technical Operator',
        today: 'Today', yesterday: 'Yesterday', earlier: 'Earlier',
        delete_session_confirm: 'Delete this session? All messages will be removed.',
        delete_session_title: 'Delete Session',
        untitled_session: 'New Chat',
        context_cleared: '— Context above has been cleared —',
        tip_new_chat: 'New Chat',
        tip_clear_context: 'Clear Context',
        tip_attach: 'Add Attachment',
        attach_menu_file: 'Upload File',
        attach_menu_folder: 'Upload Folder',
        confirm_yes: 'Confirm',
        confirm_cancel: 'Cancel',
        error_send: 'Failed to send. Please try again.', error_timeout: 'Request timeout. Please try again.',
        thinking_in_progress: 'Thinking...', thinking_done: 'Thought', thinking_duration: 'Duration',
    }
};

let currentLang = localStorage.getItem('cow_lang') || 'zh';

function t(key) {
    return (I18N[currentLang] && I18N[currentLang][key]) || (I18N.en[key]) || key;
}

function applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
        el.innerHTML = t(el.dataset.i18nHtml);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.dataset['i18nPlaceholder']);
    });
    document.querySelectorAll('[data-tip-key]').forEach(el => {
        el.setAttribute('data-tooltip', t(el.dataset.tipKey));
    });
    installCfgTipPortal();
    const langLabel = document.getElementById('lang-label');
    if (langLabel) langLabel.textContent = currentLang === 'zh' ? '中文' : 'EN';
    updateAuthUserSummary(currentInvestmentAdmin);
}

function toggleLanguage() {
    currentLang = currentLang === 'zh' ? 'en' : 'zh';
    localStorage.setItem('cow_lang', currentLang);
    applyI18n();
    _applyInputTooltips();
}

// Floating tooltip portal for [data-tip-key] elements. Tooltip nodes are
// appended to <body> so they aren't clipped by overflow:hidden ancestors
// (e.g. the config panel's scroll container).
let _cfgTipPortalEl = null;
let _cfgTipPortalInstalled = false;
function installCfgTipPortal() {
    if (_cfgTipPortalInstalled) return;
    _cfgTipPortalInstalled = true;

    const showTip = (target) => {
        const text = target.getAttribute('data-tooltip');
        if (!text) return;
        if (!_cfgTipPortalEl) {
            _cfgTipPortalEl = document.createElement('div');
            _cfgTipPortalEl.className = 'cfg-tip-floating';
            document.body.appendChild(_cfgTipPortalEl);
        }
        _cfgTipPortalEl.textContent = text;
        const rect = target.getBoundingClientRect();
        // Render once to measure, then position above the target, centered.
        _cfgTipPortalEl.style.left = '0px';
        _cfgTipPortalEl.style.top = '0px';
        _cfgTipPortalEl.classList.add('show');
        const tipRect = _cfgTipPortalEl.getBoundingClientRect();
        let left = rect.left + rect.width / 2 - tipRect.width / 2;
        // Clamp horizontally to the viewport with an 8px gutter.
        left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
        const top = rect.top - tipRect.height - 6;
        _cfgTipPortalEl.style.left = left + 'px';
        _cfgTipPortalEl.style.top = top + 'px';
    };
    const hideTip = () => {
        if (_cfgTipPortalEl) _cfgTipPortalEl.classList.remove('show');
    };

    document.addEventListener('mouseover', (e) => {
        const target = e.target.closest('[data-tip-key]');
        if (target) showTip(target);
    });
    document.addEventListener('mouseout', (e) => {
        const target = e.target.closest('[data-tip-key]');
        if (target) hideTip();
    });
    // Hide on scroll/resize so the tooltip doesn't drift away from its anchor.
    window.addEventListener('scroll', hideTip, true);
    window.addEventListener('resize', hideTip);
}

// =====================================================================
// Theme
// =====================================================================
let currentTheme = localStorage.getItem('cow_theme') || 'dark';

function applyTheme() {
    const root = document.documentElement;
    if (currentTheme === 'dark') {
        root.classList.add('dark');
        document.getElementById('theme-icon').className = 'fas fa-sun';
        document.getElementById('hljs-light').disabled = true;
        document.getElementById('hljs-dark').disabled = false;
    } else {
        root.classList.remove('dark');
        document.getElementById('theme-icon').className = 'fas fa-moon';
        document.getElementById('hljs-light').disabled = false;
        document.getElementById('hljs-dark').disabled = true;
    }
}

function toggleTheme() {
    currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('cow_theme', currentTheme);
    applyTheme();
}

// =====================================================================
// Sidebar & Navigation
// =====================================================================
const VIEW_META = {
    chat:     { group: 'nav_chat',    page: 'menu_chat' },
    config:   { group: 'nav_manage',  page: 'menu_config' },
    skills:   { group: 'nav_manage',  page: 'menu_skills' },
    channels: { group: 'nav_manage',  page: 'menu_channels' },
    'invest-users':   { group: 'nav_manage', page: 'menu_invest_users' },
    'invest-daily-content': { group: 'nav_manage', page: 'menu_invest_daily_content' },
    'invest-content': { group: 'nav_manage', page: 'menu_invest_content' },
    'invest-records': { group: 'nav_manage', page: 'menu_invest_records' },
    'invest-skills':  { group: 'nav_manage', page: 'menu_invest_skills' },
    'invest-config':  { group: 'nav_manage', page: 'menu_invest_config' },
    'invest-health':  { group: 'nav_manage', page: 'menu_invest_health' },
    logs:     { group: 'nav_monitor', page: 'menu_logs' },
};

let currentView = 'chat';

function navigateTo(viewId) {
    const removedViews = new Set(['memory', 'knowledge', 'tasks']);
    if (removedViews.has(viewId)) {
        viewId = 'chat';
    }
    if (!VIEW_META[viewId]) return;
    if (viewId !== 'invest-daily-content') {
        stopInvestmentContentPolling();
    }
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const target = document.getElementById('view-' + viewId);
    if (target) target.classList.add('active');
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewId);
    });
    const meta = VIEW_META[viewId];
    document.getElementById('breadcrumb-group').textContent = t(meta.group);
    document.getElementById('breadcrumb-group').dataset.i18n = meta.group;
    document.getElementById('breadcrumb-page').textContent = t(meta.page);
    document.getElementById('breadcrumb-page').dataset.i18n = meta.page;
    currentView = viewId;
    loadInvestmentView(viewId);
    if (window.innerWidth < 1024) closeSidebar();
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const isOpen = !sidebar.classList.contains('-translate-x-full');
    if (isOpen) {
        closeSidebar();
    } else {
        sidebar.classList.remove('-translate-x-full');
        overlay.classList.remove('hidden');
    }
}

function closeSidebar() {
    document.getElementById('sidebar').classList.add('-translate-x-full');
    document.getElementById('sidebar-overlay').classList.add('hidden');
}

async function loadInvestmentView(viewId) {
    if (!currentInvestmentAdmin) {
        await loadInvestmentAdminSession();
    }
    if (!investmentCanView(viewId)) {
        const element = investmentContentEl(`${viewId}-content`);
        investmentError(element, '权限不足');
        return;
    }
    if (viewId === 'invest-users') return renderInvestmentUsers();
    if (viewId === 'invest-daily-content') return renderInvestmentDailyContent();
    if (viewId === 'invest-content') return renderInvestmentGeneratedContent();
    if (viewId === 'invest-records') return renderInvestmentRecords();
    if (viewId === 'invest-skills') return renderInvestmentSkills();
    if (viewId === 'invest-config') return renderInvestmentConfig();
    if (viewId === 'invest-health') return renderInvestmentHealth();
}

const INVEST_SERVICE_LABELS = {
    technical_analysis: '技术分析',
    rate: '利率',
    convertible_bond: '转债',
    unauthorized_request: '无权限请求',
    all: '全部',
    unmatched: '未命中',
};

const INVEST_CUSTOMER_SERVICE_OPTIONS = [
    ['all', '全部'],
    ['technical_analysis', '技术分析'],
    ['rate', '利率'],
    ['convertible_bond', '转债'],
];

const INVEST_STATUS_LABELS = {
    success: '成功',
    failed: '失败',
    draft: '草稿',
    generating: '生成中',
    generated: '生成成功',
    generate_failed: '生成失败',
    effective: '已生效',
    archived: '已归档',
    invalidated: '已失效',
};

const INVEST_CONTENT_POLL_INTERVAL_MS = 2000;
let investmentContentPollTimer = null;
let currentInvestmentAdmin = null;
let currentConsoleAuthenticated = false;
let currentInvestmentUserPanel = 'customers';
let currentInvestmentContentPanel = 'rate';
let currentInvestmentConfigPanel = 'stock-data';
let investmentUserState = {
    filters: {
        customers: {keyword: '', keyword_field: 'all', page: '1', page_size: '20'},
        admins: {keyword: '', page: '1', page_size: '20'},
    },
    pagination: {
        customers: {page: 1, page_size: 20, total: 0, total_pages: 1},
        admins: {page: 1, page_size: 20, total: 0, total_pages: 1},
    },
};
let investmentPendingUserImportFile = null;
let investmentPendingUserImportParsed = false;
let currentInvestmentSkills = [];
let currentInvestmentSkillDialogKey = '';
let investmentRecordsState = {
    tab: 'requests',
    selected: null,
    cacheCategory: '',
    exportMode: 'range',
    filters: {
        requests: {page: '1', page_size: '80', date_mode: 'day', start_date: investmentTodayDate(), end_date: investmentTodayDate(), record_month: investmentTodayDate().slice(0, 7)},
        contents: {page: '1', page_size: '80', keyword: '', date_mode: 'day', start_date: investmentTodayDate(), end_date: investmentTodayDate(), record_month: investmentTodayDate().slice(0, 7)},
        cache: {page: '1', page_size: '120', period_mode: 'day', market_date: investmentTodayDate()},
        audits: {page: '1', page_size: '80', date_mode: 'day', start_date: investmentTodayDate(), end_date: investmentTodayDate(), record_month: investmentTodayDate().slice(0, 7)},
    },
    pagination: {
        requests: {page: 1, page_size: 80, total: 0, total_pages: 1},
        contents: {page: 1, page_size: 80, total: 0, total_pages: 1},
        cache: {page: 1, page_size: 120, total: 0, total_pages: 1},
        audits: {page: 1, page_size: 80, total: 0, total_pages: 1},
    },
    data: {
        requests: [],
        contents: [],
        cache: {entries: [], market_dates: []},
        audits: [],
    },
};

const INVEST_VIEW_PERMISSIONS = {
    'invest-users': ['customers.read', 'admin_users.read'],
    'invest-daily-content': 'content.read',
    'invest-content': 'content.read',
    'invest-records': 'records.read',
    'invest-skills': 'skills.read',
    'invest-config': ['config.read', 'stocks.read'],
    'invest-health': 'health.read',
};

function investmentCan(permission) {
    if (!permission) return true;
    const permissions = currentInvestmentAdmin?.permissions || [];
    return permissions.includes('*') || permissions.includes(permission);
}

function investmentCanView(viewId) {
    const permissions = INVEST_VIEW_PERMISSIONS[viewId];
    if (Array.isArray(permissions)) {
        return permissions.some(permission => investmentCan(permission));
    }
    return investmentCan(permissions);
}

function investmentCurrentAdminUsername() {
    return currentInvestmentAdmin?.username || 'admin';
}

async function loadInvestmentAdminSession() {
    try {
        const data = await investmentFetchJson('/api/investment/auth/me');
        currentInvestmentAdmin = data.admin || null;
    } catch (error) {
        currentInvestmentAdmin = null;
    }
    updateAuthUserSummary(currentInvestmentAdmin);
    document.querySelectorAll('.sidebar-item').forEach(item => {
        const viewId = item.dataset.view;
        if (viewId && INVEST_VIEW_PERMISSIONS[viewId]) {
            item.classList.toggle('hidden', !investmentCanView(viewId));
        }
    });
}

const INVEST_CONFIG_GROUPS = [
    {
        title: '后台Web对话',
        keys: [
            ['router.enable_web_open_chat', 'Web 普通开放聊天（不使用记忆、技能、工具）', 'checkbox'],
        ],
    },
    {
        title: '股票字典',
        keys: [
            ['tushare.token', 'Tushare Token', 'text'],
        ],
    },
    {
        title: '技术分析参数',
        keys: [
            ['technical_analysis.output_dir', '技术分析输出目录', 'text'],
            ['technical_analysis.default_chart_days', '默认图表天数', 'number'],
        ],
    },
    {
        title: '图片生成模板',
        keys: [
            ['render.template_ta_path', '技术分析模板', 'text'],
            ['render.template_rate_path', '利率模板', 'text'],
            ['render.template_cb_path', '转债模板', 'text'],
            ['render.output_dir', '渲染输出目录', 'text'],
        ],
    },
    {
        title: '存储与提示词',
        keys: [
            ['storage.files_dir', '统一文件目录', 'text'],
            ['storage.tmp_dir', '临时工作目录', 'text'],
            ['prompt.technical_analysis', '技术分析摘要 prompt', 'textarea'],
            ['prompt.rate', '利率文本生成 prompt', 'textarea'],
            ['prompt.convertible_bond', '转债文本生成 prompt', 'textarea'],
        ],
    },
];

const INVEST_ADMIN_ONLY_CONFIG_KEYS = new Set([
    'router.enable_web_open_chat',
]);
const INVEST_CONTENT_HISTORY_DATE_IDS = [
    'invest-content-history-effective-date-rate',
    'invest-content-history-effective-date-convertible_bond',
];
let investmentCacheFilterRefreshTimer = null;

function investmentContentEl(id) {
    return document.getElementById(id);
}

const INVEST_TW = {
    panel: 'bg-white dark:bg-[#1A1A1A] rounded-xl border border-slate-200 dark:border-white/10 p-6 shadow-sm min-w-0',
    panelHeading: 'flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4',
    panelActions: 'flex flex-wrap items-center justify-start sm:justify-end gap-2',
    panelTitle: 'flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3 [&_i]:text-primary-500',
    subtitle: 'text-xs leading-relaxed text-slate-500 dark:text-slate-400',
    field: 'flex flex-col gap-1.5 text-xs text-slate-500 dark:text-slate-400 min-w-0 [&_input:not([type=checkbox])]:min-h-10 [&_input:not([type=checkbox])]:w-full [&_input:not([type=checkbox])]:rounded-lg [&_input:not([type=checkbox])]:border [&_input:not([type=checkbox])]:border-slate-300 [&_input:not([type=checkbox])]:bg-white [&_input:not([type=checkbox])]:px-3 [&_input:not([type=checkbox])]:py-2 [&_input:not([type=checkbox])]:text-sm [&_input:not([type=checkbox])]:text-slate-700 [&_input:not([type=checkbox])]:outline-none [&_input:not([type=checkbox])]:transition-colors [&_input:not([type=checkbox])]:focus:border-primary-500 dark:[&_input:not([type=checkbox])]:border-white/10 dark:[&_input:not([type=checkbox])]:bg-white/5 dark:[&_input:not([type=checkbox])]:text-slate-200 [&_textarea]:w-full [&_textarea]:min-h-[92px] [&_textarea]:rounded-lg [&_textarea]:border [&_textarea]:border-slate-300 [&_textarea]:bg-white [&_textarea]:px-3 [&_textarea]:py-2 [&_textarea]:text-sm [&_textarea]:text-slate-700 [&_textarea]:outline-none [&_textarea]:transition-colors [&_textarea]:focus:border-primary-500 dark:[&_textarea]:border-white/10 dark:[&_textarea]:bg-white/5 dark:[&_textarea]:text-slate-200',
    input: 'min-h-10 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-colors focus:border-primary-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-200',
    check: 'inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300',
    button: 'inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10',
    buttonPrimary: 'border-primary-500 bg-primary-500 text-white hover:border-primary-600 hover:bg-primary-600 dark:border-primary-500 dark:bg-primary-500 dark:text-white',
    buttonDanger: 'border-rose-200 text-rose-600 hover:bg-rose-50 dark:border-rose-500/30 dark:text-rose-300 dark:hover:bg-rose-500/10',
    iconButton: 'w-8 min-w-8 px-0',
    tabs: 'mb-3 inline-flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 dark:border-white/10 dark:bg-white/5',
    tab: 'inline-flex min-h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium text-slate-500 transition-colors hover:bg-white hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-200',
    tabActive: 'bg-white text-slate-900 shadow-sm dark:bg-white/10 dark:text-white',
    tableWrap: 'w-full min-w-0 overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-[#1A1A1A]',
    table: 'w-full min-w-[720px] table-fixed text-sm',
    th: 'sticky top-0 z-[1] border-b border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:border-white/10 dark:bg-[#202020] dark:text-slate-400',
    td: 'border-b border-slate-100 bg-white px-3 py-2 align-middle text-sm text-slate-700 dark:border-white/5 dark:bg-[#1A1A1A] dark:text-slate-300',
    empty: 'flex min-h-24 items-center justify-center gap-2 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400',
    muted: 'flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400',
    mutedInline: 'text-xs text-slate-400 dark:text-slate-500',
    alertError: 'rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300',
    badge: 'inline-flex min-h-6 items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 whitespace-nowrap dark:bg-white/10 dark:text-slate-300',
    badgeOk: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300',
    badgeFail: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300',
    badgeWarning: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300',
    link: 'inline-flex max-w-full overflow-wrap-anywhere text-sm text-primary-600 hover:underline dark:text-primary-400',
    compactText: 'block max-w-[260px] truncate',
    pre: 'max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300',
};

function investmentTokenToTailwind(token, tokens) {
    if (token === 'hidden') return 'hidden';
    if (['export', 'keyword', 'direct-output-check'].includes(token)) return '';
    if (token === 'search') return tokens.includes('investment-toolbar-section') ? 'justify-start' : '';
    if (token === 'actions') return tokens.includes('investment-toolbar-section') ? 'justify-start lg:justify-end' : '';
    if (token === 'textarea') return tokens.includes('investment-field') ? '[&_textarea]:min-h-32' : '';
    if (token === 'textarea-config') return 'sm:grid-cols-1';
    if (token === 'active') {
        if (tokens.includes('investment-tab') || tokens.includes('investment-records-tab') || tokens.includes('investment-request-export-mode')) {
            return INVEST_TW.tabActive;
        }
        return token;
    }
    if (['ok', 'success'].includes(token)) return tokens.includes('investment-health-summary') ? 'text-emerald-600 dark:text-emerald-300' : INVEST_TW.badgeOk;
    if (['fail', 'error'].includes(token)) {
        if (tokens.includes('investment-alert')) return '';
        return tokens.includes('investment-health-summary') ? 'text-rose-600 dark:text-rose-300' : INVEST_TW.badgeFail;
    }
    if (['warning', 'pending'].includes(token)) return tokens.includes('investment-health-summary') ? 'text-amber-600 dark:text-amber-300' : INVEST_TW.badgeWarning;
    if (token === 'primary') return tokens.includes('investment-btn') || tokens.includes('investment-request-export-mode') ? INVEST_TW.buttonPrimary : '';
    if (token === 'danger') return tokens.includes('investment-btn') || tokens.includes('investment-request-export-mode') ? INVEST_TW.buttonDanger : '';
    if (token === 'secondary') return '';
    if (token === 'compact') {
        if (tokens.includes('investment-btn')) return 'min-h-7 px-2 py-1 text-xs';
        if (tokens.includes('investment-field')) return '[&_input:not([type=checkbox])]:py-1.5';
        return '';
    }
    if (token === 'full') return 'col-span-full';
    if (token === 'cols-1') return tokens.includes('investment-grid') ? 'grid-cols-1' : '';
    if (token === 'cols-2') return tokens.includes('investment-grid') ? 'grid-cols-1 md:grid-cols-2' : '';
    if (token === 'cols-3') return tokens.includes('investment-grid') ? 'grid-cols-1 md:grid-cols-3' : '';
    if (token === 'lines-1') return 'truncate';
    if (token === 'lines-2') return 'line-clamp-2';

    const map = {
        'investment-layout': 'grid grid-cols-1 lg:grid-cols-2 gap-4 items-start',
        'investment-workbench': 'grid grid-cols-1 lg:grid-cols-12 gap-4',
        'investment-workbench-full': 'lg:col-span-12',
        'investment-panel': INVEST_TW.panel + ' lg:col-span-6',
        'investment-table-panel': INVEST_TW.panel + ' lg:col-span-12',
        'investment-panel-heading': INVEST_TW.panelHeading,
        'investment-panel-actions': INVEST_TW.panelActions,
        'investment-panel-title': INVEST_TW.panelTitle,
        'investment-subtitle': INVEST_TW.subtitle,
        'investment-tabs': INVEST_TW.tabs,
        'investment-config-tabs': 'w-full',
        'investment-tab': INVEST_TW.tab,
        'investment-records-tabs': INVEST_TW.tabs + ' w-full overflow-x-auto',
        'investment-records-tab': INVEST_TW.tab,
        'investment-request-export-mode': INVEST_TW.button,
        'investment-config-page': 'grid gap-3',
        'investment-config-grid': 'grid grid-cols-1 lg:grid-cols-12 gap-3 items-start',
        'investment-config-panel': 'items-start',
        'investment-settings-panel': '',
        'investment-stock-data-panel': '',
        'investment-config-section': '',
        'investment-field': INVEST_TW.field,
        'investment-check': INVEST_TW.check,
        'investment-service-row': 'mt-3 flex flex-wrap items-center gap-3',
        'investment-actions': 'mt-3 flex flex-wrap items-center gap-2',
        'investment-btn': INVEST_TW.button,
        'investment-icon-btn': INVEST_TW.iconButton,
        'investment-table-wrap': INVEST_TW.tableWrap,
        'investment-table-scroll': 'overflow-x-auto',
        'investment-table': INVEST_TW.table,
        'investment-row-actions': 'whitespace-nowrap [&_.fa]:text-xs',
        'investment-empty': INVEST_TW.empty,
        'investment-alert': INVEST_TW.alertError,
        'investment-muted': INVEST_TW.muted,
        'investment-muted-inline': INVEST_TW.mutedInline,
        'investment-badge': INVEST_TW.badge,
        'investment-detail-link': INVEST_TW.link,
        'investment-compact-text': INVEST_TW.compactText,
        'investment-record-clamp': 'block max-w-[280px] overflow-hidden text-ellipsis',
        'investment-mono': 'font-mono',
        'investment-grid': 'grid gap-3',
        'investment-stat-grid': 'grid grid-cols-1 md:grid-cols-4 gap-3 mb-3',
        'investment-stat': 'rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm dark:border-white/10 dark:bg-white/5 [&_span]:block [&_span]:text-xs [&_span]:text-slate-500 dark:[&_span]:text-slate-400 [&_strong]:mt-1 [&_strong]:block [&_strong]:font-semibold [&_strong]:text-slate-700 dark:[&_strong]:text-slate-200',
        'investment-user-page': 'grid gap-4',
        'investment-user-toolbar': 'mb-4',
        'investment-user-toolbar-heading': 'max-w-xl',
        'investment-user-actionbar': 'mb-4 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5',
        'investment-user-toolbar-grid': 'grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end',
        'investment-toolbar-section': 'flex min-w-0 flex-wrap items-end gap-2',
        'investment-toolbar-group': 'flex flex-wrap items-end gap-2',
        'investment-user-pagination': 'mt-4 flex flex-col gap-3 rounded-lg border-t border-slate-100 pt-4 dark:border-white/10',
        'investment-search-type-field': 'w-full sm:w-36',
        'investment-search-field': 'w-full sm:w-[370px]',
        'investment-status-field': 'w-full sm:w-60',
        'investment-config-toolbar': 'mt-3 grid grid-cols-1 xl:grid-cols-2 gap-3 items-end',
        'investment-config-tool': 'grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_auto] gap-2 items-end',
        'investment-stock-source-config': 'mb-3 max-w-xl',
        'investment-source-field': 'w-40',
        'investment-stock-query-field': 'min-w-0 sm:min-w-80',
        'investment-import-dialog': 'grid gap-4',
        'investment-user-import-section': 'mt-4 border-t border-slate-200 pt-4 dark:border-white/10',
        'investment-import-template': 'flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5',
        'investment-import-sample': '',
        'investment-import-result': 'min-h-6 text-sm text-slate-500 dark:text-slate-400',
        'investment-import-summary': 'flex flex-wrap items-center gap-2 py-2 text-sm text-slate-600 dark:text-slate-300',
        'investment-import-preview': 'mt-2',
        'investment-current-panel': 'lg:col-span-7',
        'investment-upload-panel': 'lg:col-span-5',
        'investment-current-body': 'grid grid-cols-1 xl:grid-cols-[minmax(0,1.35fr)_minmax(220px,0.65fr)] gap-4',
        'investment-current-preview': 'flex min-h-60 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-white/5',
        'investment-current-meta': 'grid content-start gap-2 [&>div]:rounded-lg [&>div]:border [&>div]:border-slate-200 [&>div]:bg-slate-50 [&>div]:p-3 dark:[&>div]:border-white/10 dark:[&>div]:bg-white/5 [&_span]:mb-1 [&_span]:block [&_span]:text-xs [&_span]:text-slate-500 dark:[&_span]:text-slate-400 [&_strong]:block [&_strong]:break-words [&_strong]:text-sm [&_strong]:font-semibold [&_strong]:text-slate-700 dark:[&_strong]:text-slate-200',
        'investment-current-empty': 'flex min-h-60 w-full items-center justify-center text-sm text-slate-500 dark:text-slate-400',
        'investment-preview': 'h-20 w-20 rounded-lg border border-slate-200 bg-slate-50 object-contain dark:border-white/10 dark:bg-white/5',
        'investment-preview-placeholder': 'inline-flex h-20 w-20 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-center text-xs text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400',
        'investment-file-chip': 'inline-flex h-20 w-20 flex-col items-center justify-center gap-1 overflow-hidden rounded-lg border border-dashed border-slate-300 bg-slate-50 p-2 text-center text-xs text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400',
        'investment-image-flow': 'inline-flex min-w-56 items-center gap-2',
        'investment-file-stack': 'inline-flex min-w-0 items-center gap-1.5',
        'investment-flow-arrow': 'font-semibold text-primary-500',
        'investment-date-group': 'grid gap-2 mb-4',
        'investment-date-group-title': 'flex items-center justify-between gap-3 text-sm font-semibold text-slate-600 dark:text-slate-300 [&_span:last-child]:text-xs [&_span:last-child]:font-normal [&_span:last-child]:text-slate-400',
        'investment-detail-panel': 'mt-4 rounded-lg border border-sky-200 bg-sky-50 p-4 dark:border-sky-400/20 dark:bg-sky-500/10',
        'investment-detail-grid': 'grid grid-cols-1 md:grid-cols-3 gap-2 [&>div]:rounded-lg [&>div]:border [&>div]:border-slate-200 [&>div]:bg-slate-50 [&>div]:p-3 dark:[&>div]:border-white/10 dark:[&>div]:bg-white/5 [&_span]:mb-1 [&_span]:block [&_span]:text-xs [&_span]:text-slate-500 dark:[&_span]:text-slate-400 [&_strong]:block [&_strong]:break-words [&_strong]:text-sm [&_strong]:font-semibold [&_strong]:text-slate-700 dark:[&_strong]:text-slate-200',
        'investment-detail-block': 'mt-3 [&>span]:mb-1 [&>span]:block [&>span]:text-xs [&>span]:text-slate-500 dark:[&>span]:text-slate-400',
        'investment-detail-links': 'flex flex-wrap gap-2',
        'investment-records-workspace': 'grid gap-3',
        'investment-records-summary': 'grid grid-cols-1 md:grid-cols-4 gap-3',
        'investment-records-stat': 'rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5 [&_span]:block [&_span]:text-xs [&_span]:text-slate-500 dark:[&_span]:text-slate-400 [&_strong]:mt-1 [&_strong]:block [&_strong]:text-lg [&_strong]:font-semibold [&_strong]:text-slate-700 dark:[&_strong]:text-slate-200',
        'investment-records-board': 'grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5',
        'investment-records-toolbar': 'flex flex-wrap items-end justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-[#1A1A1A]',
        'investment-records-filters': '',
        'investment-records-filter-grid': 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3',
        'investment-records-filter-actions': 'flex flex-wrap items-center justify-start xl:justify-end gap-2',
        'investment-request-export-dialog': 'grid gap-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-[#1A1A1A]',
        'investment-request-export-heading': 'flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3',
        'investment-request-export-modes': 'flex flex-wrap gap-2',
        'investment-request-export-fields': 'flex flex-wrap items-end gap-3',
        'investment-request-export-note': 'text-sm text-slate-500 dark:text-slate-400',
        'investment-request-export-action': 'ml-auto',
        'investment-records-main': 'grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] gap-3 items-start',
        'investment-records-list': 'min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-[#1A1A1A]',
        'investment-records-drawer': 'min-w-0 rounded-lg border border-slate-200 bg-white dark:border-white/10 dark:bg-[#1A1A1A]',
        'investment-records-drawer-empty': 'flex min-h-40 flex-col items-center justify-center gap-2 text-sm text-slate-400 dark:text-slate-500',
        'investment-records-drawer-header': 'flex items-start justify-between gap-3 border-b border-slate-200 p-4 dark:border-white/10 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-slate-800 dark:[&_h3]:text-slate-100 [&_span]:text-xs [&_span]:text-slate-500 dark:[&_span]:text-slate-400',
        'investment-records-drawer-body': 'grid gap-4 p-4',
        'investment-records-drawer-section': 'grid gap-2 [&_h4]:text-xs [&_h4]:font-semibold [&_h4]:uppercase [&_h4]:text-slate-500 dark:[&_h4]:text-slate-400',
        'investment-records-pagination': 'flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5',
        'investment-records-pagination-summary': 'flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400',
        'investment-records-pagination-actions': 'flex flex-wrap items-center gap-2',
        'investment-records-page-size': 'flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400',
        'investment-records-table-shell': 'h-full overflow-auto rounded-lg bg-white dark:bg-[#1A1A1A]',
        'investment-generated-content-home': '',
        'investment-generated-content-entry': '',
        'investment-generated-entry-icon': '',
        'investment-generated-entry-main': '',
        'investment-generated-entry-meta': '',
        'investment-generated-content-detail': '',
        'investment-generated-content-detail-header': '',
        'investment-generated-content-detail-title': '',
        'investment-generated-content-detail-count': '',
        'investment-generated-content-entries': '',
        'investment-generated-content-header': '',
        'investment-generated-content-row': '',
        'investment-generated-content-row-main': '',
        'investment-generated-target': '',
        'investment-cache-category': 'grid gap-2',
        'investment-cache-category-grid': 'grid grid-cols-1 md:grid-cols-3 gap-3',
        'investment-cache-date-group': 'grid gap-3',
        'investment-config-field': 'grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_auto] items-end gap-2',
        'investment-config-actions': 'flex min-h-8 items-center gap-2',
        'investment-config-description': 'mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400',
        'investment-config-status': 'text-xs text-slate-500 dark:text-slate-400',
        'investment-skill-version-list': 'mt-2',
        'investment-skill-config-actions': 'whitespace-nowrap',
        'investment-wide': 'min-w-56 break-words',
        'investment-health-summary': 'flex items-center gap-2 text-sm font-semibold',
    };
    return map[token] || (token.startsWith('investment-') ? '' : token);
}

function investmentTailwindHtml(html) {
    if (typeof html !== 'string' || !html.includes('investment-')) return html;
    let output = html.replace(/class="([^"]*investment-[^"]*)"/g, (_, classValue) => {
        const tokens = classValue.split(/\s+/).filter(Boolean);
        const mapped = tokens.flatMap(token => investmentTokenToTailwind(token, tokens).split(/\s+/).filter(Boolean));
        return `class="${Array.from(new Set([...tokens, ...mapped])).join(' ')}"`;
    });
    output = output
        .replace(/<th\b(?![^>]*class=)([^>]*)>/g, `<th class="${INVEST_TW.th}"$1>`)
        .replace(/<th\b class="([^"]*)"/g, `<th class="$1 ${INVEST_TW.th}"`)
        .replace(/<td\b(?![^>]*class=)([^>]*)>/g, `<td class="${INVEST_TW.td}"$1>`)
        .replace(/<td\b class="([^"]*)"/g, `<td class="$1 ${INVEST_TW.td}"`)
        .replace(/<pre(?![^>]*class=)([^>]*)>/g, `<pre class="${INVEST_TW.pre}"$1>`)
        .replace(/<input(?![^>]*type="hidden")(?![^>]*type="checkbox")(?![^>]*class=)([^>]*)>/g, `<input class="${INVEST_TW.input}"$1>`)
        .replace(/<textarea(?![^>]*class=)([^>]*)>/g, `<textarea class="${INVEST_TW.input} min-h-24"$1>`);
    return output.replace(/\sclass=""/g, '');
}

const _nativeInnerHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
const _nativeOuterHTML = Object.getOwnPropertyDescriptor(Element.prototype, 'outerHTML');
Object.defineProperty(Element.prototype, 'innerHTML', {
    get: _nativeInnerHTML.get,
    set(value) {
        _nativeInnerHTML.set.call(this, investmentTailwindHtml(value));
    },
});
Object.defineProperty(Element.prototype, 'outerHTML', {
    get: _nativeOuterHTML.get,
    set(value) {
        _nativeOuterHTML.set.call(this, investmentTailwindHtml(value));
    },
});

function investmentLoading(element) {
    if (element) {
        element.innerHTML = '<div class="investment-empty"><i class="fas fa-spinner fa-spin"></i><span>加载中...</span></div>';
    }
}

function investmentError(element, error) {
    if (element) {
        element.innerHTML = `<div class="investment-alert error">${escapeHtml(String(error))}</div>`;
    }
}

function investmentServiceLabel(value) {
    return INVEST_SERVICE_LABELS[value] || value || '-';
}

function investmentNormalizeCustomerServices(values = []) {
    const labelsToValues = Object.fromEntries(INVEST_CUSTOMER_SERVICE_OPTIONS.map(([value, label]) => [label, value]));
    const selected = Array.from(new Set((values || [])
        .map(value => labelsToValues[value] || value)
        .filter(Boolean)));
    if (!selected.length || selected.includes('all')) return ['all'];
    const businessValues = INVEST_CUSTOMER_SERVICE_OPTIONS
        .map(([value]) => value)
        .filter(value => value !== 'all');
    if (businessValues.length && businessValues.every(value => selected.includes(value))) {
        return ['all'];
    }
    return businessValues.filter(value => selected.includes(value));
}

function investmentExpandCustomerServicesForUi(values = []) {
    const normalized = investmentNormalizeCustomerServices(values);
    if (!normalized.includes('all')) return normalized;
    return INVEST_CUSTOMER_SERVICE_OPTIONS.map(([value]) => value);
}

function investmentCustomerServicesDisplay(values = []) {
    return investmentNormalizeCustomerServices(values).map(investmentServiceLabel).join(', ');
}

function investmentStatusLabel(value) {
    return INVEST_STATUS_LABELS[value] || value || '-';
}

function investmentSelected(current, value) {
    return String(current ?? '') === String(value ?? '') ? 'selected' : '';
}

function investmentDropdown(id, options = [], selectedValue = '', attrs = '', onChange = '') {
    const normalized = options.map(item => {
        if (Array.isArray(item)) return {value: String(item[0] ?? ''), label: String(item[1] ?? '')};
        return {value: String(item.value ?? ''), label: String(item.label ?? item.value ?? '')};
    });
    const selected = normalized.find(item => String(item.value) === String(selectedValue)) || normalized[0] || {value: '', label: '--'};
    const safeId = escapeHtml(id);
    const changeAttr = onChange ? ` data-investment-dropdown-onchange="${escapeHtml(onChange)}"` : '';
    const items = normalized.map(item => {
        const active = String(item.value) === String(selected.value) ? ' active' : '';
        return `<div class="cfg-dropdown-item${active}" data-value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</div>`;
    }).join('');
    return `<input type="hidden" id="${safeId}" ${attrs} value="${escapeHtml(selected.value)}">
        <div class="cfg-dropdown investment-cow-dropdown" tabindex="0" data-investment-dropdown="${safeId}"${changeAttr}>
            <div class="cfg-dropdown-selected">
                <span class="cfg-dropdown-text">${escapeHtml(selected.label)}</span>
                <i class="fas fa-chevron-down cfg-dropdown-arrow"></i>
            </div>
            <div class="cfg-dropdown-menu">${items}</div>
        </div>`;
}

function resetInvestmentDropdownMenu(dropdown) {
    const menu = dropdown?.querySelector?.('.cfg-dropdown-menu');
    if (!menu) return;
    ['position', 'left', 'top', 'right', 'bottom', 'width', 'minWidth', 'maxWidth', 'maxHeight', 'zIndex'].forEach(prop => {
        menu.style[prop] = '';
    });
}

function positionInvestmentDropdownMenu(dropdown) {
    const menu = dropdown?.querySelector?.('.cfg-dropdown-menu');
    if (!menu) return;
    const selected = dropdown.querySelector('.cfg-dropdown-selected');
    const rect = (selected || dropdown).getBoundingClientRect();
    const gap = 4;
    const viewportPadding = 12;
    const menuWidth = Math.max(120, Math.min(rect.width, window.innerWidth - viewportPadding * 2));
    const spaceBelow = window.innerHeight - rect.bottom - gap - viewportPadding;
    const spaceAbove = rect.top - gap - viewportPadding;
    const opensUp = spaceBelow < 160 && spaceAbove > spaceBelow;
    const available = Math.max(120, Math.min(240, opensUp ? spaceAbove : spaceBelow));
    const desiredHeight = Math.min(menu.scrollHeight || 240, available);
    const left = Math.min(Math.max(viewportPadding, rect.left), window.innerWidth - menuWidth - viewportPadding);
    const top = opensUp
        ? Math.max(viewportPadding, rect.top - gap - desiredHeight)
        : Math.min(rect.bottom + gap, window.innerHeight - viewportPadding - desiredHeight);
    menu.style.position = 'fixed';
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.right = 'auto';
    menu.style.bottom = 'auto';
    menu.style.width = `${menuWidth}px`;
    menu.style.minWidth = `${menuWidth}px`;
    menu.style.maxWidth = `${menuWidth}px`;
    menu.style.maxHeight = `${available}px`;
    menu.style.zIndex = '9999';
}

function handleInvestmentDropdownClick(event) {
    const selected = event.target.closest('.cfg-dropdown[data-investment-dropdown] .cfg-dropdown-selected');
    if (selected) {
        event.stopPropagation();
        event.stopImmediatePropagation();
        const dropdown = selected.closest('.cfg-dropdown[data-investment-dropdown]');
        document.querySelectorAll('.cfg-dropdown.open').forEach(item => {
            if (item !== dropdown) {
                item.classList.remove('open');
                resetInvestmentDropdownMenu(item);
            }
        });
        const willOpen = !dropdown.classList.contains('open');
        dropdown.classList.toggle('open', willOpen);
        if (willOpen) positionInvestmentDropdownMenu(dropdown);
        else resetInvestmentDropdownMenu(dropdown);
        return;
    }
    const option = event.target.closest('.cfg-dropdown[data-investment-dropdown] .cfg-dropdown-item');
    if (!option) return;
    event.stopPropagation();
    event.stopImmediatePropagation();
    const dropdown = option.closest('.cfg-dropdown[data-investment-dropdown]');
    const input = document.getElementById(dropdown.dataset.investmentDropdown || '');
    if (!input) return;
    const value = option.dataset.value || '';
    input.value = value;
    const text = dropdown.querySelector('.cfg-dropdown-text');
    if (text) text.textContent = option.textContent || '';
    dropdown.querySelectorAll('.cfg-dropdown-item').forEach(item => item.classList.remove('active'));
    option.classList.add('active');
    dropdown.classList.remove('open');
    resetInvestmentDropdownMenu(dropdown);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    const onChange = dropdown.dataset.investmentDropdownOnchange || '';
    if (onChange) new Function('value', onChange)(value);
}

document.addEventListener('click', handleInvestmentDropdownClick);

function initInvestmentDropdowns(root = document) {
    if (!root || !root.querySelectorAll) return;
    const dropdowns = [];
    if (root.matches && root.matches('.cfg-dropdown[data-investment-dropdown]')) dropdowns.push(root);
    root.querySelectorAll('.cfg-dropdown[data-investment-dropdown]').forEach(el => dropdowns.push(el));
    dropdowns.forEach(el => {
        if (el.dataset.investmentDropdownReady === '1') return;
        const input = document.getElementById(el.dataset.investmentDropdown || '');
        if (!input) return;
        const items = Array.from(el.querySelectorAll('.cfg-dropdown-item'));
        const selected = items.find(item => String(item.dataset.value || '') === String(input.value || '')) || items[0];
        if (selected) {
            items.forEach(item => item.classList.toggle('active', item === selected));
            const text = el.querySelector('.cfg-dropdown-text');
            if (text) text.textContent = selected.textContent || '';
            input.value = selected.dataset.value || '';
        }
        el.dataset.investmentDropdownReady = '1';
    });
}

let investmentDropdownObserverStarted = false;
function startInvestmentDropdownObserver() {
    if (investmentDropdownObserverStarted || !document.body) return;
    investmentDropdownObserverStarted = true;
    initInvestmentDropdowns(document);
    if (typeof MutationObserver === 'undefined') return;
    const observer = new MutationObserver(records => {
        records.forEach(record => {
            record.addedNodes.forEach(node => {
                if (node.nodeType === 1) initInvestmentDropdowns(node);
            });
        });
    });
    observer.observe(document.body, {childList: true, subtree: true});
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startInvestmentDropdownObserver);
} else {
    startInvestmentDropdownObserver();
}

function investmentFilePath(file) {
    if (file && typeof file === 'object') return file.file_path || file.path || '';
    return file || '';
}

function investmentFileUrl(file) {
    if (file && typeof file === 'object') {
        if (file.file_url) return file.file_url;
        if (file.file_id || file.id) return `/api/file?id=${encodeURIComponent(file.file_id || file.id)}`;
    }
    const path = investmentFilePath(file);
    return `/api/file?path=${encodeURIComponent(path)}`;
}

function investmentImageUrl(path) {
    return investmentFileUrl(path);
}

function investmentFileName(path) {
    const value = investmentFilePath(path);
    return String(value || '').split(/[\\/]/).pop() || '文件';
}

function investmentIsImage(path) {
    return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(String(investmentFilePath(path) || ''));
}

function investmentTruncate(value, max = 60) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    if (text.length <= max) return text || '-';
    return `${text.slice(0, max)}...`;
}

function investmentFormatTime(value) {
    const text = String(value || '');
    if (!text) return '';
    return text.replace('T', ' ').replace(/\.\d+/, '').replace(/\+00:00$/, '');
}

function investmentFormatBeijingTime(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(text) ? text : `${text}Z`;
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return investmentFormatTime(value);
    const parts = new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    }).formatToParts(date).reduce((acc, part) => {
        acc[part.type] = part.value;
        return acc;
    }, {});
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

function investmentFormatBeijingDate(value) {
    const formatted = investmentFormatBeijingTime(value);
    return formatted ? formatted.slice(0, 10) : '';
}

function investmentMiddleEllipsis(value, head = 10, tail = 8) {
    const text = String(value || '').trim();
    if (!text) return '';
    if (text.length <= head + tail + 1) return text;
    return `${text.slice(0, head)}...${text.slice(-tail)}`;
}

function investmentPadDatePart(value) {
    return String(value).padStart(2, '0');
}

function investmentUtcToBeijingDatetimeLocal(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(text) ? text : `${text}Z`;
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return '';
    const beijing = new Date(date.getTime() + 8 * 60 * 60 * 1000);
    return [
        beijing.getUTCFullYear(),
        investmentPadDatePart(beijing.getUTCMonth() + 1),
        investmentPadDatePart(beijing.getUTCDate()),
    ].join('-') + `T${investmentPadDatePart(beijing.getUTCHours())}:${investmentPadDatePart(beijing.getUTCMinutes())}`;
}

function investmentBeijingDatetimeLocalToUtc(value) {
    const text = String(value || '').trim();
    if (!text) return null;
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (!match) return text;
    const [, year, month, day, hour, minute, second = '00'] = match;
    const utc = new Date(Date.UTC(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour) - 8,
        Number(minute),
        Number(second),
    ));
    return utc.toISOString().slice(0, 19);
}

function investmentTodayDate() {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).formatToParts(new Date()).reduce((acc, part) => {
        acc[part.type] = part.value;
        return acc;
    }, {});
    return `${parts.year}-${parts.month}-${parts.day}`;
}

function investmentDateParts(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    return {year: Number(match[1]), month: Number(match[2]), day: Number(match[3])};
}

function investmentFormatDateValue(year, month, day) {
    return `${year}-${investmentPadDatePart(month)}-${investmentPadDatePart(day)}`;
}

function investmentMonthLabel(year, month) {
    return new Intl.DateTimeFormat('zh-CN', {year: 'numeric', month: 'long'}).format(new Date(year, month - 1, 1));
}

function investmentDatePickerInitialMonth(value) {
    const parsed = investmentDateParts(value) || investmentDateParts(investmentTodayDate());
    return {year: parsed.year, month: parsed.month};
}

function investmentDatePickerInput(id) {
    return document.getElementById(id);
}

function investmentDatePickerLabel(id) {
    return document.getElementById(`${id}-date-label`);
}

function investmentDatePickerPanel(id) {
    return document.getElementById(`${id}-date-panel`);
}

function investmentRenderDateControl(id, value = '', options = {}) {
    const placeholder = options.placeholder || '选择日期';
    const attrs = options.attrs || '';
    const safeId = escapeHtml(id);
    const safeValue = escapeHtml(value || '');
    const label = value ? escapeHtml(value) : escapeHtml(placeholder);
    return `<div class="investment-date-control" data-investment-date-control="${safeId}">
        <input id="${safeId}" type="hidden" value="${safeValue}" ${attrs}>
        <button class="investment-date-value-button ${value ? '' : 'empty'}" type="button" onclick="investmentToggleDatePicker('${safeId}')" aria-haspopup="dialog" aria-expanded="false" data-placeholder="${escapeHtml(placeholder)}">
            <span id="${safeId}-date-label">${label}</span>
        </button>
        <button class="investment-date-picker-button" type="button" onclick="investmentToggleDatePicker('${safeId}')" title="选择日期" aria-label="选择日期"><i class="fas fa-calendar-days"></i></button>
        <div id="${safeId}-date-panel" class="investment-date-popover hidden"></div>
    </div>`;
}

function investmentRenderDatePickerPanel(id, year, month) {
    const input = investmentDatePickerInput(id);
    const selected = investmentDateParts(input?.value || '');
    const today = investmentDateParts(investmentTodayDate());
    const first = new Date(year, month - 1, 1);
    const start = new Date(year, month - 1, 1 - first.getDay());
    const dayCells = [];
    for (let index = 0; index < 42; index += 1) {
        const current = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index);
        const currentYear = current.getFullYear();
        const currentMonth = current.getMonth() + 1;
        const currentDay = current.getDate();
        const value = investmentFormatDateValue(currentYear, currentMonth, currentDay);
        const outside = currentMonth !== month;
        const isSelected = selected && selected.year === currentYear && selected.month === currentMonth && selected.day === currentDay;
        const isToday = today && today.year === currentYear && today.month === currentMonth && today.day === currentDay;
        dayCells.push(`<button class="investment-date-day ${outside ? 'outside' : ''} ${isSelected ? 'selected' : ''} ${isToday ? 'today' : ''}" type="button" onclick="investmentSelectDate('${id}', '${value}')">${currentDay}</button>`);
    }
    return `<div class="investment-date-picker" data-year="${year}" data-month="${month}">
        <div class="investment-date-picker-head">
            <button type="button" class="investment-date-nav" onclick="investmentMoveDatePickerMonth('${id}', -1)" aria-label="上个月"><i class="fas fa-chevron-left"></i></button>
            <strong>${escapeHtml(investmentMonthLabel(year, month))}</strong>
            <button type="button" class="investment-date-nav" onclick="investmentMoveDatePickerMonth('${id}', 1)" aria-label="下个月"><i class="fas fa-chevron-right"></i></button>
        </div>
        <div class="investment-date-weekdays"><span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span></div>
        <div class="investment-date-days">${dayCells.join('')}</div>
        <div class="investment-date-picker-foot">
            <button type="button" onclick="investmentClearDatePicker('${id}')">清除</button>
            <button type="button" onclick="investmentSelectDate('${id}', investmentTodayDate())">今天</button>
        </div>
    </div>`;
}

function investmentCloseDatePickers(exceptId = '') {
    document.querySelectorAll('.investment-date-popover').forEach(panel => {
        if (exceptId && panel.id === `${exceptId}-date-panel`) return;
        panel.classList.add('hidden');
    });
}

function investmentToggleDatePicker(id) {
    const panel = investmentDatePickerPanel(id);
    const input = investmentDatePickerInput(id);
    if (!panel || !input) return;
    const shouldOpen = panel.classList.contains('hidden');
    investmentCloseDatePickers(id);
    if (!shouldOpen) {
        panel.classList.add('hidden');
        return;
    }
    const month = investmentDatePickerInitialMonth(input.value);
    panel.innerHTML = investmentRenderDatePickerPanel(id, month.year, month.month);
    panel.classList.remove('hidden');
}

function investmentMoveDatePickerMonth(id, delta) {
    const panel = investmentDatePickerPanel(id);
    if (!panel) return;
    const picker = panel.querySelector('.investment-date-picker');
    const year = Number(picker?.dataset.year || investmentDatePickerInitialMonth('').year);
    const month = Number(picker?.dataset.month || investmentDatePickerInitialMonth('').month);
    const next = new Date(year, month - 1 + Number(delta || 0), 1);
    panel.innerHTML = investmentRenderDatePickerPanel(id, next.getFullYear(), next.getMonth() + 1);
}

function investmentSetDatePickerValue(id, value) {
    const input = investmentDatePickerInput(id);
    const label = investmentDatePickerLabel(id);
    if (!input || !label) return;
    input.value = value || '';
    const button = label.closest('.investment-date-value-button');
    label.textContent = value || button?.dataset.placeholder || '选择日期';
    button?.classList.toggle('empty', !value);
    input.dispatchEvent(new Event('change', {bubbles: true}));
}

function investmentSelectDate(id, value) {
    investmentSetDatePickerValue(id, value);
    investmentCloseDatePickers();
}

function investmentClearDatePicker(id) {
    investmentSetDatePickerValue(id, '');
    investmentCloseDatePickers();
}

function investmentTimePickerInput(id) {
    return document.getElementById(id);
}

function investmentTimePickerLabel(id) {
    return document.getElementById(`${id}-time-label`);
}

function investmentTimePickerPanel(id) {
    return document.getElementById(`${id}-time-panel`);
}

function investmentNormalizeTimeValue(value) {
    const match = String(value || '').match(/^(\d{1,2}):(\d{1,2})$/);
    if (!match) return '00:00';
    const hour = Math.max(0, Math.min(23, Number(match[1]) || 0));
    const minute = Math.max(0, Math.min(59, Number(match[2]) || 0));
    return `${investmentPadDatePart(hour)}:${investmentPadDatePart(minute)}`;
}

function investmentRenderTimeOptions(max, selected) {
    const values = [];
    for (let value = 0; value <= max; value += 1) {
        const text = investmentPadDatePart(value);
        values.push(`<option value="${text}" ${text === selected ? 'selected' : ''}>${text}</option>`);
    }
    return values.join('');
}

function investmentRenderTimeControl(id, value = '00:00', options = {}) {
    const attrs = options.attrs || '';
    const safeId = escapeHtml(id);
    const normalized = investmentNormalizeTimeValue(value);
    return `<div class="investment-time-control" data-investment-time-control="${safeId}">
        <input id="${safeId}" type="hidden" value="${escapeHtml(normalized)}" ${attrs}>
        <button class="investment-time-value-button" type="button" onclick="investmentToggleTimePicker('${safeId}')" aria-haspopup="dialog" aria-expanded="false">
            <span id="${safeId}-time-label">${escapeHtml(normalized)}</span>
        </button>
        <button class="investment-time-picker-button" type="button" onclick="investmentToggleTimePicker('${safeId}')" title="选择时间" aria-label="选择时间"><i class="far fa-clock"></i></button>
        <div id="${safeId}-time-panel" class="investment-time-popover hidden"></div>
    </div>`;
}

function investmentRenderTimePickerPanel(id) {
    const [hour, minute] = investmentNormalizeTimeValue(investmentTimePickerInput(id)?.value || '00:00').split(':');
    return `<div class="investment-time-picker">
        <div class="investment-time-picker-head"><strong>选择时间</strong><span>北京时间</span></div>
        <div class="investment-time-select-row">
            <label><span>时</span><select id="${id}-hour-select" class="investment-time-select">${investmentRenderTimeOptions(23, hour)}</select></label>
            <span class="investment-time-separator">:</span>
            <label><span>分</span><select id="${id}-minute-select" class="investment-time-select">${investmentRenderTimeOptions(59, minute)}</select></label>
        </div>
        <div class="investment-time-picker-foot">
            <button type="button" onclick="investmentSetTimePickerValue('${id}', '00:00')">00:00</button>
            <button type="button" onclick="investmentSelectTime('${id}')">确定</button>
        </div>
    </div>`;
}

function investmentCloseTimePickers(exceptId = '') {
    document.querySelectorAll('.investment-time-popover').forEach(panel => {
        if (exceptId && panel.id === `${exceptId}-time-panel`) return;
        panel.classList.add('hidden');
    });
}

function investmentToggleTimePicker(id) {
    const panel = investmentTimePickerPanel(id);
    const input = investmentTimePickerInput(id);
    if (!panel || !input || input.disabled) return;
    const shouldOpen = panel.classList.contains('hidden');
    investmentCloseDatePickers();
    investmentCloseTimePickers(id);
    if (!shouldOpen) {
        panel.classList.add('hidden');
        return;
    }
    panel.innerHTML = investmentRenderTimePickerPanel(id);
    panel.classList.remove('hidden');
}

function investmentSetTimePickerValue(id, value) {
    const input = investmentTimePickerInput(id);
    const label = investmentTimePickerLabel(id);
    if (!input || !label) return;
    const normalized = investmentNormalizeTimeValue(value);
    input.value = normalized;
    label.textContent = normalized;
    input.dispatchEvent(new Event('change', {bubbles: true}));
    investmentCloseTimePickers();
}

function investmentSelectTime(id) {
    const hour = document.getElementById(`${id}-hour-select`)?.value || '00';
    const minute = document.getElementById(`${id}-minute-select`)?.value || '00';
    investmentSetTimePickerValue(id, `${hour}:${minute}`);
}

function investmentAddDays(dateValue, days) {
    const parts = investmentDateParts(dateValue || investmentTodayDate());
    if (!parts) return investmentTodayDate();
    const date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + Number(days || 0)));
    return investmentFormatDateValue(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

function investmentDefaultExpiresDate() {
    const effectiveDate = document.getElementById('invest-content-effective-date')?.value || investmentTodayDate();
    return investmentAddDays(effectiveDate, 1);
}

function syncInvestmentDefaultExpiresAt() {
    const enabled = document.getElementById('invest-content-expires-enabled')?.checked === true;
    if (!enabled) return;
    investmentSetDatePickerValue('invest-content-expires-date', investmentDefaultExpiresDate());
    investmentSetTimePickerValue('invest-content-expires-time', '00:00');
}

function toggleInvestmentExpiresAt(checked) {
    const enabled = checked === true;
    const fields = document.getElementById('invest-content-expires-fields');
    const hint = document.getElementById('invest-content-expires-hint');
    const disabled = !enabled;
    fields?.classList.toggle('disabled', disabled);
    fields?.classList.toggle('hidden', disabled);
    fields?.querySelectorAll('input, button').forEach(input => {
        input.disabled = disabled;
    });
    if (hint) hint.textContent = enabled ? '指定失效时间' : '不指定失效时间';
    if (enabled) {
        syncInvestmentDefaultExpiresAt();
    }
}

function changeInvestmentExpiresMode() {
    toggleInvestmentExpiresAt(document.getElementById('invest-content-expires-enabled')?.checked === true);
}

function investmentContentExpiresAtValue() {
    const enabled = document.getElementById('invest-content-expires-enabled')?.checked === true;
    if (!enabled) return '';
    const dateValue = document.getElementById('invest-content-expires-date')?.value || investmentDefaultExpiresDate();
    const timeValue = document.getElementById('invest-content-expires-time')?.value || '00:00';
    return `${dateValue}T${timeValue}`;
}

document.addEventListener('click', event => {
    if (event.target.closest('.investment-date-control')) return;
    if (event.target.closest('.investment-time-control')) return;
    investmentCloseDatePickers();
    investmentCloseTimePickers();
});

function investmentCompactText(value, max = 60) {
    return `<span class="investment-compact-text" title="${escapeHtml(String(value || ''))}">${escapeHtml(investmentTruncate(value, max))}</span>`;
}

function investmentHistoryHoverText(value, max = 24) {
    const rawText = String(value || '').trim();
    const text = rawText || '无';
    return `<span class="investment-history-cell-summary" data-tooltip="${escapeHtml(text)}" title="${escapeHtml(text)}">${escapeHtml(investmentTruncate(text, max))}</span>`;
}

function investmentFileLinks(files = []) {
    const values = Array.isArray(files) ? files.filter(Boolean) : [];
    if (!values.length) return '<span class="investment-muted-inline">无</span>';
    return values.map(file => {
        const path = investmentFilePath(file);
        const name = escapeHtml(investmentFileName(file));
        const url = investmentFileUrl(file);
        return `<a class="investment-detail-link" href="${url}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(path)}">${name}</a>`;
    }).join('');
}

function investmentFileSummary(files = []) {
    const values = Array.isArray(files) ? files.filter(Boolean) : [];
    if (!values.length) return '<span class="investment-muted-inline">无输出</span>';
    const first = investmentFileName(values[0]);
    const extra = values.length > 1 ? ` 等 ${values.length} 个文件` : '';
    return `<span class="investment-compact-text" title="${escapeHtml(values.join('\n'))}">${escapeHtml(first + extra)}</span>`;
}

function investmentRecordClamp(value, lines = 1, max = 80) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    const display = investmentTruncate(text || '-', max);
    return `<span class="investment-record-clamp lines-${lines}" title="${escapeHtml(String(value || ''))}">${escapeHtml(display)}</span>`;
}

function investmentRecordFileSummary(files = [], emptyText = '无文件') {
    const values = Array.isArray(files) ? files.filter(Boolean) : [];
    if (!values.length) return `<span class="investment-muted-inline">${escapeHtml(emptyText)}</span>`;
    const first = investmentFileName(values[0]);
    const text = values.length > 1 ? `${first} 等 ${values.length} 个文件` : first;
    return investmentRecordClamp(text, 1, 28);
}

function investmentRecordTableShell(tableHtml) {
    return `<div class="investment-records-table-shell">${investmentTableWrap(tableHtml, true, '业务记录表格')}</div>`;
}

function investmentArtifactTable(artifacts = []) {
    const values = Array.isArray(artifacts) ? artifacts : [];
    if (!values.length) return '<span class="investment-muted-inline">无</span>';
    const rows = values.map(item => `<tr>
        <td class="investment-artifact-role">${escapeHtml(item.artifact_role || '-')}</td>
        <td class="investment-artifact-file">${investmentFileLinks([item.file_path])}</td>
        <td>${escapeHtml(item.file_size ?? '-')}</td>
        <td>${investmentCompactText(item.file_hash || '', 28)}</td>
        <td>${investmentCompactText(item.version_tag || '', 28)}</td>
    </tr>`).join('');
    return `<div class="investment-table-scroll"><table class="investment-table investment-artifact-table">
        <thead><tr><th>角色</th><th>文件</th><th>大小</th><th>哈希</th><th>版本</th></tr></thead>
        <tbody>${rows}</tbody>
    </table></div>`;
}

function investmentEncodedRecord(record) {
    return encodeURIComponent(JSON.stringify(record || {}));
}

function investmentStatusClass(status) {
    if (status === 'success' || status === 'generated' || status === 'effective') return 'ok';
    if (status === 'failed' || status === 'generate_failed' || status === 'invalidated') return 'fail';
    if (status === 'generating') return 'pending';
    return '';
}

function investmentDeliveryStatusClass(status) {
    if (status === '已交付') return 'ok';
    if (status === '交付异常' || status === '未交付') return 'fail';
    if (status === '待客户领取' || status === '待生成') return 'pending';
    return '';
}

function investmentContentHasActiveTask(records = []) {
    return records.some(record => record.status === 'generating');
}

function stopInvestmentContentPolling() {
    if (investmentContentPollTimer) {
        clearTimeout(investmentContentPollTimer);
        investmentContentPollTimer = null;
    }
}

function scheduleInvestmentContentPolling(serviceType, records = []) {
    stopInvestmentContentPolling();
    if (!investmentContentHasActiveTask(records)) return;
    investmentContentPollTimer = setTimeout(() => {
        refreshInvestmentContentRecords(serviceType).catch(error => {
            console.error('Investment content polling failed:', error);
            scheduleInvestmentContentPolling(serviceType, records);
        });
    }, INVEST_CONTENT_POLL_INTERVAL_MS);
}

async function investmentFetchJson(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch (error) {
        throw new Error(text || `HTTP ${response.status}`);
    }
    if (!response.ok) {
        throw new Error(data.message || data.user_prompt || data.detail || `HTTP ${response.status}`);
    }
    if (data.status && data.status !== 'success') {
        throw new Error(data.message || data.user_prompt || data.detail || '操作失败');
    }
    return data;
}

function investmentDownload(path, params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).trim() !== '') {
            query.set(key, String(value).trim());
        }
    });
    const suffix = query.toString();
    window.location.href = suffix ? `${path}?${suffix}` : path;
}

function investmentButton(icon, label, onclick, variant = 'secondary') {
    return `<button class="investment-btn ${variant}" onclick="${onclick}"><i class="fas ${icon}"></i><span>${label}</span></button>`;
}

function investmentButtonIfCan(permission, icon, label, onclick, variant = 'secondary') {
    if (!investmentCan(permission)) return '';
    return investmentButton(icon, label, onclick, variant);
}

function investmentIconButton(icon, label, onclick, variant = 'secondary') {
    return `<button class="investment-btn investment-icon-btn ${variant}" onclick="${onclick}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"><i class="fas ${icon}"></i></button>`;
}

function investmentIconButtonIfCan(permission, icon, label, onclick, variant = 'secondary') {
    if (!investmentCan(permission)) return '';
    return investmentIconButton(icon, label, onclick, variant);
}

function investmentTextButton(label, onclick, variant = 'secondary') {
    return `<button class="investment-btn investment-text-action ${variant}" onclick="${onclick}"><span>${label}</span></button>`;
}

function investmentTextButtonIfCan(permission, label, onclick, variant = 'secondary') {
    if (!investmentCan(permission)) return '';
    return investmentTextButton(label, onclick, variant);
}

function showInvestmentModal(title, bodyHtml) {
    let overlay = document.getElementById('investment-modal-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'investment-modal-overlay';
        overlay.className = 'investment-modal-overlay fixed inset-0 z-[120] hidden items-center justify-center bg-slate-950/60 p-6';
        overlay.innerHTML = `
            <div class="investment-modal flex max-h-[calc(100vh-48px)] w-[min(920px,100%)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-white/10 dark:bg-[#1A1A1A]" role="dialog" aria-modal="true" aria-labelledby="investment-modal-title">
                <div class="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 text-slate-800 dark:border-white/10 dark:text-slate-100">
                    <strong id="investment-modal-title" class="text-sm font-semibold"></strong>
                    <button class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-200" type="button" onclick="hideInvestmentModal()" aria-label="关闭">
                        <i class="fas fa-xmark"></i>
                    </button>
                </div>
                <div id="investment-modal-body" class="investment-modal-body overflow-auto p-4"></div>
            </div>`;
        overlay.addEventListener('click', event => {
            if (event.target === overlay) hideInvestmentModal();
        });
        document.body.appendChild(overlay);
    }
    document.getElementById('investment-modal-title').textContent = title || '';
    document.getElementById('investment-modal-body').innerHTML = bodyHtml || '';
    overlay.classList.remove('hidden');
    overlay.classList.add('flex');
}

function hideInvestmentModal() {
    const overlay = document.getElementById('investment-modal-overlay');
    if (!overlay) return;
    overlay.classList.add('hidden');
    overlay.classList.remove('flex');
    const body = document.getElementById('investment-modal-body');
    if (body) body.innerHTML = '';
}

document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hideInvestmentModal();
});

function showInvestmentToast(message, variant = 'success') {
    let container = document.getElementById('investment-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'investment-toast-container';
        container.className = 'fixed right-4 top-4 z-[140] grid w-[min(360px,calc(100vw-32px))] gap-2 pointer-events-none';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = variant === 'error'
        ? 'pointer-events-auto flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm leading-relaxed text-rose-700 shadow-lg transition-all duration-200 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300'
        : 'pointer-events-auto flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm leading-relaxed text-emerald-700 shadow-lg transition-all duration-200 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300';
    const icon = variant === 'error' ? 'fa-triangle-exclamation' : 'fa-circle-check';
    toast.innerHTML = `<i class="fas ${icon}"></i><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('opacity-0', '-translate-y-1');
        setTimeout(() => toast.remove(), 180);
    }, 2600);
}

function investmentField(label, id, value = '', type = 'text') {
    if (type === 'textarea') {
        return `<label class="investment-field textarea"><span>${label}</span><textarea id="${id}" rows="4">${escapeHtml(value || '')}</textarea></label>`;
    }
    if (type === 'checkbox') {
        const checked = value === true || value === 'true' || value === '1' ? 'checked' : '';
        return investmentSwitch(label, id, Boolean(checked));
    }
    return `<label class="investment-field"><span>${label}</span><input id="${id}" type="${type}" value="${escapeHtml(value || '')}"></label>`;
}

function investmentSwitch(label, id, checked = false, options = {}) {
    const safeId = escapeHtml(id || '');
    const safeLabel = escapeHtml(label || '');
    const className = options.className ? ` ${escapeHtml(options.className)}` : '';
    const inputClass = options.inputClass ? ` class="${escapeHtml(options.inputClass)}"` : '';
    const value = options.value !== undefined ? ` value="${escapeHtml(options.value)}"` : '';
    const attrs = options.attrs ? ` ${options.attrs}` : '';
    const checkedAttr = checked ? ' checked' : '';
    const idAttr = safeId ? ` id="${safeId}"` : '';
    return `<label class="investment-switch${className}"><input${idAttr} type="checkbox"${inputClass}${value}${checkedAttr}${attrs}><span class="investment-switch-track" aria-hidden="true"><span class="investment-switch-thumb"></span></span><span class="investment-switch-label">${safeLabel}</span></label>`;
}

function investmentTableWrap(tableHtml, scroll = true, label = '数据表格') {
    const scrollClass = scroll ? ' investment-table-scroll' : '';
    return `<div class="investment-table-wrap${scrollClass}" role="region" aria-label="${escapeHtml(label)}" data-scroll-hint="左右滑动查看完整表格">${tableHtml}</div>`;
}

function investmentStockStats(stats = {}) {
    return `
        <div class="investment-stat-grid">
            <div class="investment-stat"><span>字典数量</span><strong>${escapeHtml(stats.total ?? 0)}</strong></div>
            <div class="investment-stat"><span>最近刷新时间</span><strong>${escapeHtml(investmentFormatBeijingTime(stats.latest_updated_at || '') || '-')}</strong></div>
            <div class="investment-stat"><span>最近刷新来源</span><strong>${escapeHtml(stats.latest_source || '-')}</strong></div>
            <div class="investment-stat"><span>来源数量</span><strong>${escapeHtml(stats.source_count ?? 0)}</strong></div>
        </div>`;
}

function investmentStockTools(stats = {}, configs = {}, canReadConfig = false, canReadStocks = true) {
    return `
        <section class="investment-panel investment-config-section investment-workbench-full investment-stock-data-card">
            <div class="investment-panel-heading">
                <div>
                    <div class="investment-panel-title"><i class="fas fa-chart-line"></i><span>股票数据</span></div>
                    <div class="investment-subtitle">维护股票字典数据源，刷新基础股票字典，并用股票名称查询验证解析结果。</div>
                </div>
            </div>
            ${canReadConfig ? `
                <div class="investment-stock-source-config">
                    ${renderInvestmentConfigField('tushare.token', 'Tushare Token', 'text', configs['tushare.token'])}
                </div>` : ''}
            ${investmentStockStats(stats)}
            ${canReadStocks ? `
                <div class="investment-config-toolbar investment-stock-toolbar">
                    <div class="investment-config-tool investment-stock-refresh-tool">
                        <label class="investment-field investment-source-field">
                            <span>刷新来源</span>
                            ${investmentDropdown('invest-stock-refresh-source', [['auto', 'auto'], ['akshare', 'akshare'], ['tushare', 'tushare']], 'auto')}
                        </label>
                        ${investmentButtonIfCan('stocks.write', 'fa-arrows-rotate', '刷新股票字典', 'refreshInvestmentStocks()', 'primary')}
                    </div>
                    <div class="investment-config-tool investment-stock-query-tool">
                        <label class="investment-field investment-stock-query-field">
                            <span>股票名查询测试</span>
                            <input id="invest-stock-query-name" type="text" placeholder="例如：新易盛">
                        </label>
                        ${investmentButton('fa-magnifying-glass', '查询', 'queryInvestmentStocks()', 'primary')}
                    </div>
                </div>
                <div id="invest-stock-action-result" class="investment-muted"></div>
                <div id="invest-stock-query-result" class="investment-table-wrap"></div>` : ''}
        </section>`;
}

function renderInvestmentStockRows(stocks = []) {
    if (!stocks.length) return '<div class="investment-empty">暂无匹配股票</div>';
    const rows = stocks.map(stock => `
        <tr>
            <td class="investment-mono">${escapeHtml(stock.code || '')}</td>
            <td>${escapeHtml(stock.name || '')}</td>
            <td>${escapeHtml(stock.market || '')}</td>
            <td class="investment-mono">${escapeHtml(stock.ts_code || '')}</td>
            <td>${escapeHtml(stock.source || '')}</td>
            <td>${escapeHtml(investmentFormatBeijingTime(stock.updated_at || '') || '-')}</td>
        </tr>`).join('');
    return investmentTableWrap(`<table class="investment-table">
        <thead><tr><th>代码</th><th>名称</th><th>市场</th><th>TS Code</th><th>来源</th><th>更新时间</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

async function renderInvestmentUsers() {
    const element = investmentContentEl('invest-users-content');
    const canSeeAdminUsers = investmentCan('admin_users.read');
    if (currentInvestmentUserPanel === 'admins' && !canSeeAdminUsers) {
        currentInvestmentUserPanel = 'customers';
    }
    element.innerHTML = `
        <div class="investment-tabs">
            <button class="investment-tab ${currentInvestmentUserPanel === 'customers' ? 'active' : ''}" onclick="switchInvestmentUserPanel('customers')">
                <i class="fas fa-user-check"></i><span>客户</span>
            </button>
            ${canSeeAdminUsers ? `<button class="investment-tab ${currentInvestmentUserPanel === 'admins' ? 'active' : ''}" onclick="switchInvestmentUserPanel('admins')">
                <i class="fas fa-user-shield"></i><span>后台人员</span>
            </button>` : ''}
        </div>
        <div id="investment-users-panel-content"></div>`;
    if (currentInvestmentUserPanel === 'admins') {
        await renderInvestmentAdminUsers();
    } else {
        await renderInvestmentCustomerUsers();
    }
}

function switchInvestmentUserPanel(panel) {
    currentInvestmentUserPanel = panel === 'admins' ? 'admins' : 'customers';
    renderInvestmentUsers();
}

function investmentUserQuery(panel) {
    const filters = investmentUserState.filters[panel] || {};
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).trim() !== '') {
            query.set(key, String(value).trim());
        }
    });
    return query.toString();
}

function applyInvestmentCustomerSearch() {
    investmentUserState.filters.customers = {
        ...investmentUserState.filters.customers,
        keyword: document.getElementById('invest-users-keyword')?.value || '',
        keyword_field: document.getElementById('invest-users-keyword-field')?.value || 'all',
        page: '1',
    };
    renderInvestmentCustomerUsers();
}

function clearInvestmentCustomerSearch() {
    investmentUserState.filters.customers = {
        ...investmentUserState.filters.customers,
        keyword: '',
        keyword_field: 'all',
        page: '1',
    };
    renderInvestmentCustomerUsers();
}

function applyInvestmentAdminSearch() {
    investmentUserState.filters.admins = {
        ...investmentUserState.filters.admins,
        keyword: document.getElementById('invest-admin-users-keyword')?.value || '',
        page: '1',
    };
    renderInvestmentAdminUsers();
}

function investmentUserApplyPagination(panel, pagination = {}) {
    const current = investmentUserState.filters[panel] || {};
    const page = Number(pagination.page || current.page || 1);
    const pageSize = Number(pagination.page_size || current.page_size || 20);
    investmentUserState.pagination[panel] = {
        page,
        page_size: pageSize,
        total: Number(pagination.total || 0),
        total_pages: Math.max(1, Number(pagination.total_pages || 1)),
    };
    investmentUserState.filters[panel] = {
        ...current,
        page: String(page),
        page_size: String(pageSize),
    };
}

function renderInvestmentUserPagination(panel, pagination = null) {
    const meta = pagination || investmentUserState.pagination[panel] || {};
    const page = Number(meta.page || 1);
    const totalPages = Math.max(1, Number(meta.total_pages || 1));
    const total = Number(meta.total || 0);
    const pageSize = Number(meta.page_size || 20);
    return `
        <div class="investment-user-pagination">
            <div class="investment-records-pagination-summary">共 ${total} 条，每页 ${pageSize} 条，第 ${page} / ${totalPages} 页</div>
            <div class="investment-records-pagination-actions">
                <button class="investment-btn" type="button" ${page <= 1 ? 'disabled' : ''} onclick="changeInvestmentUserPage('${panel}', ${page - 1})"><i class="fas fa-chevron-left"></i><span>上一页</span></button>
                <button class="investment-btn" type="button" ${page >= totalPages ? 'disabled' : ''} onclick="changeInvestmentUserPage('${panel}', ${page + 1})"><span>下一页</span><i class="fas fa-chevron-right"></i></button>
            </div>
        </div>`;
}

function changeInvestmentUserPage(panel, page) {
    investmentUserState.filters[panel] = {
        ...(investmentUserState.filters[panel] || {}),
        page: String(Math.max(1, Number(page || 1))),
    };
    if (panel === 'admins') return renderInvestmentAdminUsers();
    return renderInvestmentCustomerUsers();
}

async function renderInvestmentCustomerUsers() {
    const element = document.getElementById('investment-users-panel-content') || investmentContentEl('invest-users-content');
    investmentLoading(element);
    try {
        const filters = investmentUserState.filters.customers;
        const data = await investmentFetchJson(`/api/investment/users?${investmentUserQuery('customers')}`);
        const users = data.users || [];
        investmentUserApplyPagination('customers', data.pagination);
        element.innerHTML = `
            <div class="investment-user-page">
                <section class="investment-table-panel full">
                    <div class="investment-user-toolbar">
                        <div class="investment-user-toolbar-heading">
                            <div class="investment-panel-title"><i class="fas fa-users"></i><span>客户列表</span></div>
                            <div class="investment-subtitle">客户仅用于微信公众号端授权，不可登录后台 Web。</div>
                        </div>
                    </div>
                    <div class="investment-user-actionbar investment-user-toolbar-grid">
                        <div class="investment-toolbar-section search investment-toolbar-group primary">
                            <label class="investment-field investment-search-type-field">
                                <span>分类</span>
                                ${investmentDropdown('invest-users-keyword-field', [['all', '全部'], ['openid', 'OpenID'], ['name', '姓名'], ['institution', '机构'], ['mobile', '手机号'], ['service', '服务']], filters.keyword_field || 'all', 'name="keyword_field"')}
                            </label>
                            <label class="investment-field investment-search-field"><span>关键字</span><input id="invest-users-keyword" type="text" value="${escapeHtml(filters.keyword || '')}" placeholder="OpenID / 姓名 / 机构 / 手机号 / 服务"></label>
                            ${investmentButton('fa-magnifying-glass', '查询', 'applyInvestmentCustomerSearch()', 'primary')}
                            ${investmentButton('fa-rotate-left', '清除搜索', 'clearInvestmentCustomerSearch()')}
                        </div>
                        <div class="investment-toolbar-section actions investment-toolbar-group">
                            ${investmentButtonIfCan('customers.write', 'fa-user-plus', '新增客户', 'openInvestmentUserDialog()', 'primary')}
                            ${investmentButtonIfCan('customers.import', 'fa-file-import', '批量导入客户', 'openInvestmentUsersImportDialog()', 'primary')}
                            ${investmentButtonIfCan('customers.export', 'fa-download', '导出', 'openInvestmentCustomerExportDialog()', 'primary')}
                        </div>
                    </div>
                    ${renderInvestmentUsersTable(users)}
                    ${renderInvestmentUserPagination('customers', data.pagination)}
                </section>
            </div>`;
    } catch (error) {
        investmentError(element, error);
    }
}

function renderInvestmentUsersTable(users) {
    if (!users.length) return '<div class="investment-empty">暂无用户</div>';
    const rows = users.map(user => `
        <tr>
            <td title="${escapeHtml(user.openid)}">${escapeHtml(investmentMiddleEllipsis(user.openid, 10, 8))}</td>
            <td>${escapeHtml(user.name || '')}</td>
            <td>${escapeHtml(user.institution || '')}</td>
            <td>${escapeHtml(user.mobile || '')}</td>
            <td>${escapeHtml(investmentCustomerServicesDisplay(user.allowed_services || []))}</td>
            <td><span class="investment-badge ${user.enabled ? 'ok' : 'fail'}">${user.enabled ? '启用' : '停用'}</span></td>
            <td>${escapeHtml(investmentFormatBeijingDate(user.auth_end_at || '') || '-')}</td>
            <td class="investment-row-actions">
                ${investmentButtonIfCan('customers.write', 'fa-pen', '编辑', `openInvestmentUserDialog('${encodeURIComponent(JSON.stringify(user))}')`)}
                ${investmentButtonIfCan('customers.enable', user.enabled ? 'fa-ban' : 'fa-check', user.enabled ? '停用' : '启用', `setInvestmentUserStatus('${encodeURIComponent(user.openid)}', '${user.enabled ? 'disable' : 'enable'}')`, user.enabled ? 'danger' : 'secondary')}
            </td>
        </tr>`).join('');
    return investmentTableWrap(`<table class="investment-table">
        <thead><tr><th>OpenID</th><th>姓名</th><th>机构</th><th>手机号</th><th>服务</th><th>状态</th><th>授权结束</th><th>动作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

async function renderInvestmentAdminUsers() {
    const element = document.getElementById('investment-users-panel-content') || investmentContentEl('invest-users-content');
    investmentLoading(element);
    try {
        const filters = investmentUserState.filters.admins;
        const data = await investmentFetchJson(`/api/investment/admin-users?${investmentUserQuery('admins')}`);
        const users = data.users || [];
        investmentUserApplyPagination('admins', data.pagination);
        element.innerHTML = `
            <div class="investment-user-page">
                <section class="investment-table-panel full">
                    <div class="investment-user-toolbar">
                        <div class="investment-user-toolbar-heading">
                            <div class="investment-panel-title"><i class="fas fa-users-gear"></i><span>后台人员列表</span></div>
                            <div class="investment-subtitle">后台人员可登录后台 Web，角色分为管理员、内容运营和技术运营。</div>
                        </div>
                    </div>
                    <div class="investment-user-actionbar investment-user-toolbar-grid">
                        <div class="investment-toolbar-section search investment-toolbar-group primary">
                            <label class="investment-field investment-search-field"><span>关键字</span><input id="invest-admin-users-keyword" type="text" value="${escapeHtml(filters.keyword || '')}" placeholder="账号 / 角色"></label>
                                ${investmentButton('fa-magnifying-glass', '查询', 'applyInvestmentAdminSearch()', 'primary')}
                        </div>
                        <div class="investment-toolbar-section actions investment-toolbar-group">
                            ${investmentButtonIfCan('admin_users.write', 'fa-user-plus', '新增后台人员', 'openInvestmentAdminUserDialog()', 'primary')}
                        </div>
                    </div>
                    ${renderInvestmentAdminUsersTable(users)}
                    ${renderInvestmentUserPagination('admins', data.pagination)}
                </section>
            </div>`;
    } catch (error) {
        investmentError(element, error);
    }
}

function investmentAdminRoleOptions(selected) {
    return ['admin', 'content_operator', 'technical_operator']
        .map(role => `<option value="${role}" ${role === selected ? 'selected' : ''}>${escapeHtml(investmentAdminRoleLabel(role))}</option>`)
        .join('');
}

function renderInvestmentAdminUsersTable(users) {
    if (!users.length) return '<div class="investment-empty">暂无后台人员</div>';
    const rows = users.map(user => `
        <tr>
            <td title="${escapeHtml(user.username || '')}">${escapeHtml(user.username || '')}</td>
            <td>${escapeHtml(investmentAdminRoleLabel(user.role || ''))}</td>
            <td><span class="investment-badge ${user.enabled ? 'ok' : 'fail'}">${user.enabled ? '启用' : '停用'}</span></td>
            <td>${escapeHtml(investmentFormatBeijingTime(user.last_login_at || '') || '-')}</td>
            <td class="investment-row-actions">
                ${investmentButtonIfCan('admin_users.write', 'fa-pen', '编辑', `fillInvestmentAdminUserForm('${encodeURIComponent(JSON.stringify(user))}')`)}
                ${investmentButtonIfCan('admin_users.write', user.enabled ? 'fa-ban' : 'fa-check', user.enabled ? '停用' : '启用', `setInvestmentAdminUserStatus('${encodeURIComponent(user.username)}', '${user.enabled ? 'disable' : 'enable'}')`, user.enabled ? 'danger' : 'secondary')}
                ${investmentButtonIfCan('admin_users.reset_password', 'fa-key', '重置密码', `resetInvestmentAdminPassword('${encodeURIComponent(user.username)}')`)}
            </td>
        </tr>`).join('');
    return investmentTableWrap(`<table class="investment-table">
        <thead><tr><th>账号</th><th>角色</th><th>状态</th><th>最近登录</th><th>动作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function openInvestmentAdminUserDialog(encoded = '') {
    const user = encoded ? JSON.parse(decodeURIComponent(encoded)) : {};
    const body = `
        <div class="investment-grid cols-2">
            ${investmentField('账号', 'invest-admin-username', user.username || '')}
            ${investmentField(user.username ? '新密码（留空不修改）' : '初始密码', 'invest-admin-password', '', 'password')}
            <label class="investment-field">
                <span>角色</span>
                ${investmentDropdown('invest-admin-role', [
                    ['admin', investmentAdminRoleLabel('admin')],
                    ['content_operator', investmentAdminRoleLabel('content_operator')],
                    ['technical_operator', investmentAdminRoleLabel('technical_operator')],
                ], user.role || 'content_operator')}
            </label>
            ${investmentSwitch('启用', 'invest-admin-enabled', user.enabled !== false, {className: 'investment-direct-output-check'})}
        </div>
        <div class="investment-actions investment-modal-actions">
            ${investmentButtonIfCan('admin_users.write', 'fa-floppy-disk', '保存后台人员', 'saveInvestmentAdminUser()', 'primary')}
            ${investmentButton('fa-xmark', '取消', 'hideInvestmentModal()')}
        </div>`;
    showInvestmentModal('后台人员信息', body);
}

function resetInvestmentAdminUserForm() {
    const username = document.getElementById('invest-admin-username');
    const password = document.getElementById('invest-admin-password');
    const role = document.getElementById('invest-admin-role');
    const enabled = document.getElementById('invest-admin-enabled');
    if (username) username.value = '';
    if (password) password.value = '';
    if (role) role.value = 'content_operator';
    if (enabled) enabled.checked = true;
}

function fillInvestmentAdminUserForm(encoded) {
    openInvestmentAdminUserDialog(encoded);
}

async function saveInvestmentAdminUser() {
    const body = {
        username: document.getElementById('invest-admin-username').value.trim(),
        password: document.getElementById('invest-admin-password').value,
        role: document.getElementById('invest-admin-role').value,
        enabled: document.getElementById('invest-admin-enabled').checked,
    };
    try {
        await investmentFetchJson('/api/investment/admin-users', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        showInvestmentToast('后台人员已保存');
        hideInvestmentModal();
        await renderInvestmentUsers();
    } catch (error) {
        showInvestmentToast(`保存后台人员失败：${String(error.message || error)}`, 'error');
    }
}

async function setInvestmentAdminUserStatus(encodedUsername, action) {
    const username = decodeURIComponent(encodedUsername);
    try {
        await investmentFetchJson(`/api/investment/admin-users/${encodeURIComponent(username)}/status/${action}`, {method: 'POST'});
        showInvestmentToast(action === 'enable' ? '后台人员已启用' : '后台人员已停用');
        await renderInvestmentUsers();
    } catch (error) {
        showInvestmentToast(`状态更新失败：${String(error.message || error)}`, 'error');
    }
}

async function resetInvestmentAdminPassword(encodedUsername) {
    const username = decodeURIComponent(encodedUsername);
    const password = window.prompt(`请输入 ${username} 的新密码`);
    if (!password) return;
    try {
        await investmentFetchJson(`/api/investment/admin-users/${encodeURIComponent(username)}/password`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({password}),
        });
        showInvestmentToast('密码已重置');
    } catch (error) {
        showInvestmentToast(`重置密码失败：${String(error.message || error)}`, 'error');
    }
}

function resetInvestmentUserForm() {
    ['openid', 'name', 'institution', 'mobile', 'auth-start', 'auth-end', 'remark'].forEach(key => {
        const el = document.getElementById(`invest-user-${key}`);
        if (el) el.value = '';
    });
    const enabled = document.getElementById('invest-user-enabled');
    if (enabled) enabled.checked = true;
    document.querySelectorAll('.invest-user-service').forEach((item, index) => item.checked = index === 0);
}

function investmentUserServiceChecks(prefix, user = {}) {
    const services = investmentExpandCustomerServicesForUi(user.allowed_services || ['all']);
    return INVEST_CUSTOMER_SERVICE_OPTIONS.map(([value, label], index) => {
        const checked = services.includes(value);
        return investmentSwitch(label, `${prefix}-service-${index}`, checked, {
            inputClass: `${prefix}-service`,
            value,
            attrs: `data-service-value="${escapeHtml(value)}" onchange="handleInvestmentUserServiceToggle('${escapeHtml(prefix)}', '${escapeHtml(value)}')"`,
        });
    }).join('');
}

function handleInvestmentUserServiceToggle(prefix, value) {
    const items = Array.from(document.querySelectorAll(`.${prefix}-service`));
    const allItem = items.find(item => item.dataset.serviceValue === 'all');
    const businessItems = items.filter(item => item.dataset.serviceValue !== 'all');
    if (value === 'all') {
        if (allItem?.checked) {
            businessItems.forEach(item => { item.checked = true; });
        } else {
            businessItems.forEach(item => { item.checked = false; });
        }
        return;
    }
    if (allItem && !businessItems.every(item => item.checked)) allItem.checked = false;
    if (businessItems.length && businessItems.every(item => item.checked)) {
        if (allItem) allItem.checked = true;
    }
}

function renderInvestmentUserImportSection() {
    return `
        <section class="investment-import-dialog investment-user-import-section">
            <section class="investment-import-template">
                <div>
                    <div class="investment-panel-title"><i class="fas fa-table"></i><span>存在用户名单示例模板</span></div>
                    <div class="investment-subtitle">必填字段：手机号、服务权限、授权结束日期。OpenID 可空，系统会生成待绑定用户。</div>
                </div>
                <a class="investment-btn" href="/api/investment/users/import-template.xlsx" target="_blank" download>
                    <i class="fas fa-download"></i><span>下载模板</span>
                </a>
            </section>
            <div class="investment-import-sample">
                <table class="investment-table compact">
                    <thead><tr><th>手机号</th><th>服务权限</th><th>授权结束日期</th><th>OpenID</th><th>姓名</th></tr></thead>
                    <tbody><tr><td>13800000000</td><td>全部</td><td>2026-12-31</td><td>可空</td><td>张三</td></tr></tbody>
                </table>
            </div>
            <label class="investment-field">
                <span>批量导入客户</span>
                <input id="invest-users-import-file" type="file" accept=".xlsx,.xls">
            </label>
            <div class="investment-actions investment-modal-actions">
                ${investmentButtonIfCan('customers.import', 'fa-magnifying-glass-chart', '解析文件', 'parseInvestmentUsersImport()', 'primary')}
            </div>
            <div id="invest-users-import-result" class="investment-import-result"></div>
        </section>`;
}

function openInvestmentUserDialog(encoded = '') {
    const user = encoded ? JSON.parse(decodeURIComponent(encoded)) : {};
    const body = `
        <div class="investment-grid cols-2">
            ${investmentField('OpenID', 'invest-user-modal-openid', user.openid || '')}
            ${investmentField('姓名', 'invest-user-modal-name', user.name || '')}
            ${investmentField('机构', 'invest-user-modal-institution', user.institution || '')}
            ${investmentField('手机号', 'invest-user-modal-mobile', user.mobile || '')}
            ${investmentField('授权开始', 'invest-user-modal-auth-start', investmentUtcToBeijingDatetimeLocal(user.auth_start_at || ''), 'datetime-local')}
            ${investmentField('授权结束', 'invest-user-modal-auth-end', investmentUtcToBeijingDatetimeLocal(user.auth_end_at || ''), 'datetime-local')}
        </div>
        <div class="investment-service-row">
            ${investmentUserServiceChecks('invest-user-modal', user)}
            ${investmentSwitch('启用', 'invest-user-modal-enabled', user.enabled !== false)}
        </div>
        ${investmentField('备注', 'invest-user-modal-remark', user.remark || '', 'textarea')}
        <div class="investment-actions investment-modal-actions">
            ${investmentButtonIfCan('customers.write', 'fa-floppy-disk', '保存用户', "saveInvestmentUser('invest-user-modal')", 'primary')}
            ${investmentButton('fa-xmark', '取消', 'hideInvestmentModal()')}
        </div>`;
    showInvestmentModal('用户信息', body);
}

function editInvestmentUser(encoded) {
    openInvestmentUserDialog(encoded);
}

function fillInvestmentUserForm(encoded) {
    const user = JSON.parse(decodeURIComponent(encoded));
    document.getElementById('invest-user-openid').value = user.openid || '';
    document.getElementById('invest-user-name').value = user.name || '';
    document.getElementById('invest-user-institution').value = user.institution || '';
    document.getElementById('invest-user-mobile').value = user.mobile || '';
    document.getElementById('invest-user-auth-start').value = investmentUtcToBeijingDatetimeLocal(user.auth_start_at || '');
    document.getElementById('invest-user-auth-end').value = investmentUtcToBeijingDatetimeLocal(user.auth_end_at || '');
    document.getElementById('invest-user-remark').value = user.remark || '';
    document.getElementById('invest-user-enabled').checked = !!user.enabled;
    const services = new Set((user.allowed_services || []).map(investmentServiceLabel));
    document.querySelectorAll('.invest-user-service').forEach(item => {
        item.checked = services.has(item.value);
    });
}

async function saveInvestmentUser(prefix = 'invest-user') {
    const serviceClass = prefix === 'invest-user-modal' ? '.invest-user-modal-service:checked' : '.invest-user-service:checked';
    const selectedServices = Array.from(document.querySelectorAll(serviceClass)).map(item => item.value);
    const services = investmentNormalizeCustomerServices(selectedServices);
    const body = {
        openid: document.getElementById(`${prefix}-openid`).value.trim(),
        name: document.getElementById(`${prefix}-name`).value.trim(),
        institution: document.getElementById(`${prefix}-institution`).value.trim(),
        mobile: document.getElementById(`${prefix}-mobile`).value.trim(),
        enabled: document.getElementById(`${prefix}-enabled`).checked,
        allowed_services: services,
        auth_start_at: investmentBeijingDatetimeLocalToUtc(document.getElementById(`${prefix}-auth-start`).value),
        auth_end_at: investmentBeijingDatetimeLocalToUtc(document.getElementById(`${prefix}-auth-end`).value),
        remark: document.getElementById(`${prefix}-remark`).value.trim(),
    };
    try {
        await investmentFetchJson('/api/investment/users', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        showInvestmentToast('用户已保存');
        if (prefix === 'invest-user-modal') hideInvestmentModal();
        await renderInvestmentUsers();
    } catch (error) {
        showInvestmentToast(`保存用户失败：${String(error.message || error)}`, 'error');
    }
}

async function setInvestmentUserStatus(encodedOpenid, action) {
    const openid = decodeURIComponent(encodedOpenid);
    try {
        await investmentFetchJson(`/api/investment/users/${encodeURIComponent(openid)}/status/${action}`, {method: 'POST'});
        showInvestmentToast(action === 'enable' ? '用户已启用' : '用户已停用');
        await renderInvestmentUsers();
    } catch (error) {
        showInvestmentToast(`状态更新失败：${String(error.message || error)}`, 'error');
    }
}

async function disableInvestmentUser(encodedOpenid) {
    return setInvestmentUserStatus(encodedOpenid, 'disable');
}

function openInvestmentUsersImportDialog() {
    investmentPendingUserImportFile = null;
    investmentPendingUserImportParsed = false;
    showInvestmentModal('批量导入客户', renderInvestmentUserImportSection());
}

function renderInvestmentImportResult(data, committed = false) {
    const preview = data.preview || [];
    const rows = preview.map(row => `
        <tr>
            <td>${escapeHtml(row.openid_generated ? '待绑定' : (row.openid || ''))}</td>
            <td>${escapeHtml(row.name || '')}</td>
            <td>${escapeHtml(row.institution || '')}</td>
            <td>${escapeHtml(row.mobile || '')}</td>
            <td>${row.enabled === false ? '停用' : '启用'}</td>
            <td>${escapeHtml(row.allowed_services || '')}</td>
            <td>${escapeHtml(String(investmentFormatBeijingTime(row.auth_end_at || '') || '').slice(0, 10) || '-')}</td>
        </tr>`).join('');
    return `
        <div class="investment-import-summary">
            <span class="investment-badge ok">${committed ? '已导入' : '解析完成'}</span>
            <span>解析 ${Number(data.parsed || 0)} 行</span>
            <span>新用户 ${Number(data.new_users || 0)}</span>
            <span>新增 ${Number(data.created || 0)}</span>
            <span>更新 ${Number(data.updated || 0)}</span>
        </div>
        ${rows ? `<div class="investment-import-preview">${investmentTableWrap(`<table class="investment-table compact">
            <thead><tr><th>OpenID</th><th>姓名</th><th>机构</th><th>手机号</th><th>状态</th><th>服务权限</th><th>授权结束</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`)}</div>` : ''}
        ${!committed ? `<div class="investment-actions investment-modal-actions">
            ${investmentButtonIfCan('customers.import', 'fa-check', '确认导入', 'confirmInvestmentUsersImport()', 'primary')}
        </div>` : ''}`;
}

async function postInvestmentUsersImport(commit) {
    const input = document.getElementById('invest-users-import-file');
    const result = document.getElementById('invest-users-import-result');
    const file = investmentPendingUserImportFile || input?.files?.[0];
    if (!file) {
        result.textContent = '请选择 Excel 文件';
        return null;
    }
    investmentPendingUserImportFile = file;
    const form = new FormData();
    form.append('file', file);
    form.append('commit', commit ? 'true' : 'false');
    result.textContent = commit ? '导入中...' : '解析中...';
    return investmentFetchJson('/api/investment/users/import', {method: 'POST', body: form});
}

async function parseInvestmentUsersImport() {
    const result = document.getElementById('invest-users-import-result');
    try {
        const data = await postInvestmentUsersImport(false);
        if (!data) return;
        investmentPendingUserImportParsed = true;
        result.innerHTML = renderInvestmentImportResult(data, false);
    } catch (error) {
        result.textContent = String(error.message || error);
        showInvestmentToast('用户解析失败', 'error');
    }
}

async function confirmInvestmentUsersImport() {
    const result = document.getElementById('invest-users-import-result');
    if (!investmentPendingUserImportParsed) {
        result.textContent = '请先解析文件';
        return;
    }
    try {
        const data = await postInvestmentUsersImport(true);
        if (!data) return;
        result.innerHTML = renderInvestmentImportResult(data, true);
        showInvestmentToast('用户导入完成');
        await renderInvestmentUsers();
    } catch (error) {
        result.textContent = String(error.message || error);
        showInvestmentToast('用户导入失败', 'error');
    }
}

async function importInvestmentUsers() {
    return confirmInvestmentUsersImport();
}

function openInvestmentCustomerExportDialog() {
    const body = `
        <div class="investment-grid cols-1">
            <label class="investment-field">
                <span>导出状态</span>
                ${investmentDropdown('invest-users-export-enabled', [['', '全部'], ['true', '启用'], ['false', '停用']], '')}
            </label>
        </div>
        <div class="investment-actions investment-modal-actions">
            ${investmentButtonIfCan('customers.export', 'fa-download', '导出客户', 'downloadInvestmentUsersExport()', 'primary')}
            ${investmentButton('fa-xmark', '取消', 'hideInvestmentModal()')}
        </div>`;
    showInvestmentModal('导出客户名单', body);
}

function downloadInvestmentUsersExport() {
    const enabled = document.getElementById('invest-users-export-enabled')?.value || '';
    investmentDownload('/api/investment/export/users.xlsx', {enabled});
}

function exportInvestmentUsers() {
    openInvestmentCustomerExportDialog();
}

async function renderInvestmentDailyContent() {
    const element = investmentContentEl('invest-daily-content-content');
    if (!element) return;
    element.innerHTML = `
        <div class="investment-tabs">
            <button class="investment-tab ${currentInvestmentContentPanel === 'rate' ? 'active' : ''}" onclick="switchInvestmentContentPanel('rate')">
                <i class="fas fa-chart-line"></i><span>利率内容</span>
            </button>
            <button class="investment-tab ${currentInvestmentContentPanel === 'convertible_bond' ? 'active' : ''}" onclick="switchInvestmentContentPanel('convertible_bond')">
                <i class="fas fa-scale-balanced"></i><span>转债内容</span>
            </button>
        </div>
        <div id="invest-daily-content-panel" class="grid gap-3"></div>`;
    return renderInvestmentContent(currentInvestmentContentPanel);
}

function switchInvestmentContentPanel(panel) {
    currentInvestmentContentPanel = panel === 'convertible_bond' ? 'convertible_bond' : 'rate';
    stopInvestmentContentPolling();
    renderInvestmentDailyContent();
}

function currentInvestmentContentServiceType() {
    return currentInvestmentContentPanel === 'convertible_bond' ? 'convertible_bond' : 'rate';
}

async function renderInvestmentContent(serviceType, options = {}) {
    const element = investmentContentEl('invest-daily-content-panel') || investmentContentEl('invest-daily-content-content');
    investmentLoading(element);
    try {
        const effectiveDate = options.effective_date ?? investmentContentHistoryEffectiveDate(serviceType);
        const query = investmentContentHistoryQuery(serviceType, effectiveDate);
        const data = await investmentFetchJson(`/api/investment/daily-content?${query.toString()}`);
        const records = data.contents || [];
        const isCb = serviceType === 'convertible_bond';
        const historyDateId = investmentContentHistoryEffectiveDateId(serviceType);
        element.innerHTML = `
            <div class="investment-daily-content-page">
                <section class="investment-panel investment-content-top-panel">
                    <div class="investment-content-top">
                        ${renderInvestmentCurrentEffective(data.current_effective, serviceType)}
                        ${renderInvestmentContentUploadPanel(serviceType)}
                    </div>
                </section>
                <section class="investment-panel investment-content-history-panel">
                    <div class="investment-history-header">
                        <div class="investment-history-heading-row">
                            <div>
                                <div class="investment-panel-title"><i class="fas fa-layer-group"></i><span>${isCb ? '转债内容历史' : '利率内容历史'}</span></div>
                            </div>
                            <span class="investment-muted-inline">${records.length} 条记录</span>
                        </div>
                        <div class="investment-history-filterbar">
                            <label class="investment-field compact investment-history-date-field">
                                <span>日期</span>
                                ${investmentRenderDateControl(historyDateId, effectiveDate || '', {
                                    placeholder: '选择日期',
                                    attrs: `onchange="refreshInvestmentContentRecords('${serviceType}', {effective_date: investmentContentHistoryEffectiveDate('${serviceType}')})"`,
                                })}
                            </label>
                            ${investmentButtonIfCan('audits.read', 'fa-clock-rotate-left', '操作流水', 'renderInvestmentOperationAudits()')}
                            ${investmentButton('fa-arrows-rotate', '刷新', `refreshInvestmentContentRecords('${serviceType}', {effective_date: investmentContentHistoryEffectiveDate('${serviceType}')})`)}
                        </div>
                    </div>
                    <div id="invest-content-records-table" class="investment-content-history-body">${renderInvestmentContentHistoryGroups(records)}</div>
                    <div id="invest-content-detail" data-investment-detail-panel class="investment-detail-panel hidden"></div>
                </section>
            </div>`;
        const result = document.getElementById('invest-content-action-result');
        if (result && options.message) result.textContent = options.message;
        scheduleInvestmentContentPolling(serviceType, records);
    } catch (error) {
        investmentError(element, error);
    }
}

function investmentContentHistoryEffectiveDateId(serviceType) {
    const normalizedServiceType = String(serviceType || '').replace(/[^a-zA-Z0-9_-]/g, '_');
    return `invest-content-history-effective-date-${normalizedServiceType}`;
}

function investmentContentHistoryEffectiveDate(serviceType) {
    const historyDateId = investmentContentHistoryEffectiveDateId(serviceType);
    return document.getElementById(historyDateId)?.value || investmentTodayDate();
}

function investmentContentHistoryQuery(serviceType, effectiveDate = investmentTodayDate()) {
    const query = new URLSearchParams({service_type: serviceType});
    query.set('effective_date', effectiveDate || investmentTodayDate());
    return query;
}

function renderInvestmentCurrentEffective(record, serviceType) {
    const isCb = serviceType === 'convertible_bond';
    const title = isCb ? '当前生效转债图' : '当前生效利率图';
    const subtitle = isCb ? '公众号用户输入“转债”时会收到这张图' : '公众号用户输入“利率”时会收到这张图';
    const image = record?.output_image ? renderInvestmentFilePreview(record.output_image, title) : '<div class="investment-current-empty">暂无生效图片</div>';
    return `
        <section class="investment-daily-current-panel">
            <div class="investment-panel-heading">
                <div>
                    <div class="investment-panel-title"><i class="fas ${isCb ? 'fa-scale-balanced' : 'fa-chart-line'}"></i><span>${title}</span></div>
                    <div class="investment-subtitle">${subtitle}</div>
                </div>
                ${record ? `<span class="investment-badge ok">已生效</span>` : `<span class="investment-badge pending">未设置</span>`}
            </div>
            <div class="investment-current-body">
                <div class="investment-current-preview">${image}</div>
                <div class="investment-current-meta">
                    <div><span>ID</span><strong>${escapeHtml((record?.content_id || '-').slice(0, 8))}</strong></div>
                    <div><span>生效日期</span><strong>${escapeHtml(record?.effective_date || '-')}</strong></div>
                    <div><span>生效时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record?.effective_at) || '-')}</strong></div>
                    <div><span>失效时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record?.expires_at) || '不失效')}</strong></div>
                    <div><span>操作人</span><strong>${escapeHtml(record?.operator || '-')}</strong></div>
                    <div><span>输出文件</span><strong>${record?.output_image ? investmentFileLinks([record.output_image]) : '-'}</strong></div>
                </div>
            </div>
        </section>`;
}

function renderInvestmentContentUploadPanel(serviceType) {
    const isCb = serviceType === 'convertible_bond';
    return `
        <section class="investment-daily-upload-panel">
            <div class="investment-panel-title"><i class="fas fa-upload"></i><span>${isCb ? '上传转债资料' : '上传利率资料'}</span></div>
            <input type="hidden" id="invest-content-service" value="${serviceType}">
            <input type="hidden" id="invest-content-upload-mode" value="image">
            <div class="investment-daily-upload-stage image-mode" id="invest-content-upload-stage">
                <div class="investment-upload-mode-bar">
                    ${investmentSwitch('纯文字生成', 'invest-content-text-mode-toggle', false, {className: 'investment-upload-mode-switch', attrs: `onchange="switchInvestmentUploadMode(this.checked ? 'text' : 'image')"`})}
                </div>
                <div class="investment-upload-image-mode">
                    <label class="investment-upload-dropzone" for="invest-content-files">
                        <input id="invest-content-files" type="file" accept="image/*" multiple onchange="updateInvestmentUploadFileSummary()">
                        <span class="investment-upload-plus"><i class="fas fa-plus"></i></span>
                        <strong>上传图片</strong>
                        <small id="invest-content-file-summary">点击此区域选择利率/转债资料图片</small>
                        <span id="invest-content-file-preview" class="investment-upload-preview"></span>
                    </label>
                    <label class="investment-field investment-upload-supplement">
                        <span>${isCb ? '段子/补充文本（可选）' : '补充文本（可选）'}</span>
                        <input id="invest-content-supplement-text" type="text" placeholder="${isCb ? '可输入转债段子或补充说明，参与生成' : '可输入补充说明，参与生成'}">
                    </label>
                </div>
                <div class="investment-upload-text-mode">
                    <label class="investment-field">
                        <span>${isCb ? '转债段子/文字资料' : '文字资料'}</span>
                        <textarea id="invest-content-source-text" placeholder="${isCb ? '输入转债段子或完整文字资料，用于生成转债结果图片' : '输入利率文字资料，用于生成利率结果图片'}"></textarea>
                    </label>
                </div>
            </div>
            <div class="investment-grid cols-2">
                <div class="investment-field investment-expires-toggle-field">
                    <span>失效设置</span>
                    <div class="investment-expires-toggle-row">
                        ${investmentSwitch('指定失效时间', 'invest-content-expires-enabled', false, {className: 'investment-expires-switch', attrs: 'onchange="toggleInvestmentExpiresAt(this.checked)"'})}
                        <small id="invest-content-expires-hint">不指定失效时间</small>
                    </div>
                </div>
            </div>
            <div id="invest-content-expires-fields" class="investment-grid cols-2 investment-expires-fields disabled hidden">
                <label class="investment-field"><span>失效日期</span>${investmentRenderDateControl('invest-content-expires-date', investmentAddDays(investmentTodayDate(), 1), {placeholder: '选择失效日期'})}</label>
                <label class="investment-field"><span>失效时间</span>${investmentRenderTimeControl('invest-content-expires-time', '00:00')}</label>
            </div>
            <div class="investment-actions">
                ${investmentButtonIfCan('content.upload', 'fa-wand-magic-sparkles', '生成', 'createInvestmentContent(true)', 'primary')}
            </div>
            <div id="invest-content-action-result" class="investment-muted"></div>
        </section>`;
}

async function investmentShouldAutoEffectiveAfterGenerate(serviceType) {
    const label = serviceType === 'convertible_bond' ? '转债' : '利率';
    const response = await investmentFetchJson(`/api/investment/daily-content?service_type=${encodeURIComponent(serviceType)}&effective_date=${encodeURIComponent(investmentTodayDate())}&limit=1`);
    const records = Array.isArray(response.contents) ? response.contents : [];
    if (records.length > 0) return false;
    const confirmed = window.confirm(`今日还没有${label}内容记录，是否使用本次生成结果作为 ${investmentTodayDate()} 生效${label}图？`);
    return confirmed ? true : null;
}

function switchInvestmentUploadMode(mode) {
    const targetMode = mode === 'text' ? 'text' : 'image';
    const modeInput = document.getElementById('invest-content-upload-mode');
    const stage = document.getElementById('invest-content-upload-stage');
    const toggle = document.getElementById('invest-content-text-mode-toggle');
    if (modeInput) modeInput.value = targetMode;
    if (toggle) toggle.checked = targetMode === 'text';
    if (stage) {
        stage.classList.toggle('text-mode', targetMode === 'text');
        stage.classList.toggle('image-mode', targetMode !== 'text');
    }
    if (targetMode === 'text') {
        document.getElementById('invest-content-source-text')?.focus();
    }
}

function updateInvestmentUploadFileSummary() {
    const input = document.getElementById('invest-content-files');
    const summary = document.getElementById('invest-content-file-summary');
    const preview = document.getElementById('invest-content-file-preview');
    const files = Array.from(input?.files || []);
    if (!summary) return;
    summary.textContent = files.length
        ? files.map(file => file.name).join('、')
        : '点击此区域选择利率/转债资料图片';
    if (!preview) return;
    preview.innerHTML = files.slice(0, 4).map(file => {
        if (!file.type.startsWith('image/')) return '';
        const url = URL.createObjectURL(file);
        return `<span class="investment-upload-thumb"><img src="${url}" alt="${escapeHtml(file.name)}"></span>`;
    }).join('');
}

async function refreshInvestmentContentRecords(serviceType, filters = {}) {
    const effectiveDate = filters.effective_date ?? investmentContentHistoryEffectiveDate(serviceType);
    const query = investmentContentHistoryQuery(serviceType, effectiveDate);
    const data = await investmentFetchJson(`/api/investment/daily-content?${query.toString()}`);
    const records = data.contents || [];
    const table = document.getElementById('invest-content-records-table');
    if (table) table.innerHTML = renderInvestmentContentHistoryGroups(records);
    scheduleInvestmentContentPolling(serviceType, records);
    return records;
}

async function refreshInvestmentContentAction(serviceType) {
    if (currentView === 'invest-records') {
        await renderInvestmentRecords();
        return;
    }
    serviceType = serviceType || currentInvestmentContentServiceType();
    await refreshInvestmentContentRecords(serviceType, {effective_date: investmentContentHistoryEffectiveDate(serviceType)});
}

function renderInvestmentFilePreview(path, label) {
    if (!path) return '<div class="investment-preview-placeholder">待输出</div>';
    const safePath = escapeHtml(path);
    const name = escapeHtml(investmentFileName(path));
    const url = investmentImageUrl(path);
    if (investmentIsImage(path)) {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" title="${safePath}"><img class="investment-preview" src="${url}" alt="${escapeHtml(label)}"></a>`;
    }
    return `<a class="investment-file-chip" href="${url}" target="_blank" rel="noopener noreferrer" title="${safePath}"><i class="fas fa-file"></i><span>${name}</span></a>`;
}

function renderInvestmentSourcePreviews(sourceFiles = []) {
    const files = Array.isArray(sourceFiles) ? sourceFiles.filter(Boolean) : [];
    if (!files.length) return '<div class="investment-preview-placeholder">无输入图</div>';
    return files.map(path => renderInvestmentFilePreview(path, '输入图片')).join('');
}

function investmentArtifactsByRole(record, role) {
    const artifacts = Array.isArray(record?.output_artifacts) ? record.output_artifacts : [];
    return artifacts.filter(item => item && item.artifact_role === role);
}

function investmentContentSourceFiles(record) {
    const artifacts = investmentArtifactsByRole(record, 'source_image');
    return artifacts.length ? artifacts : (record.source_files || []);
}

function investmentContentOutputImage(record) {
    const artifacts = investmentArtifactsByRole(record, 'output_image');
    return artifacts[0] || record.output_image || '';
}

function renderInvestmentImageFlow(record) {
    return `<div class="investment-image-flow">
        <div class="investment-file-stack">${renderInvestmentSourcePreviews(investmentContentSourceFiles(record))}</div>
        <span class="investment-flow-arrow">→</span>
        <div class="investment-file-stack">${renderInvestmentFilePreview(investmentContentOutputImage(record), '输出图片')}</div>
    </div>`;
}

function renderInvestmentContentHistoryGroups(records) {
    if (!records.length) return '<div class="investment-empty">暂无内容记录</div>';
    return investmentTableWrap(`<table class="investment-table investment-history-table">
                <thead><tr><th>ID</th><th>服务</th><th>版本</th><th>状态</th><th>模式</th><th>操作人</th><th>生成时间</th><th>原始资料</th><th>生成内容</th><th>输出</th><th>产物</th><th>操作</th></tr></thead>
                <tbody>${records.map(record => {
                    const serviceType = record.service_type || '';
                    const canGenerate = record.status !== 'generating';
                    const actionServiceType = escapeHtml(serviceType);
                    const artifactFiles = Array.isArray(record.output_artifacts) ? record.output_artifacts.filter(item => item && item.file_path) : [];
                    const outputImage = investmentContentOutputImage(record);
                    const artifactCount = artifactFiles.length;
                    const warningText = record.status_warning || record.error_message || '';
                    const warning = warningText ? investmentCompactText(warningText, 80) : '';
                    return `<tr>
                        <td class="investment-mono">${escapeHtml((record.content_id || '').slice(0, 8))}</td>
                        <td>${investmentServiceLabel(record.service_type)}</td>
                        <td>v${escapeHtml(record.content_version || 1)}</td>
                        <td>
                            <span class="investment-badge ${investmentStatusClass(record.status)}">${investmentStatusLabel(record.status)}</span>
                            ${warning ? `<div class="investment-history-warning">${warning}</div>` : ''}
                        </td>
                        <td><span class="investment-muted-inline">AI+渲染</span></td>
                        <td>${escapeHtml(record.operator || '')}</td>
                        <td>${escapeHtml(investmentFormatBeijingTime(record.created_at) || '')}</td>
                        <td>${investmentHistoryHoverText(record.source_text, 24)}</td>
                        <td>${investmentHistoryHoverText(record.generated_text, 24)}</td>
                        <td><div class="investment-history-output-preview">${outputImage ? renderInvestmentFilePreview(outputImage, '输出图片') : '<div class="investment-preview-placeholder">未生成</div>'}</div></td>
                        <td>
                            <span class="investment-muted-inline">${artifactCount} 个</span>
                            ${artifactFiles.length ? investmentFileLinks(artifactFiles) : ''}
                        </td>
                        <td class="investment-row-actions">
                            ${investmentTextButton('刷新', `refreshInvestmentContentAction('${actionServiceType}')`)}
                            ${canGenerate ? investmentTextButtonIfCan('content.generate', '生成', `generateInvestmentContent('${record.content_id}', '${actionServiceType}')`) : ''}
                            ${record.output_image ? investmentTextButtonIfCan('content.publish', '设为生效', `effectiveInvestmentContent('${record.content_id}', '${actionServiceType}')`, 'primary') : ''}
                            ${investmentTextButton('详情', `showInvestmentContentDetail('${investmentEncodedRecord(record)}')`)}
                        </td>
                    </tr>`;
                }).join('')}</tbody>
            </table>`, 'content-history-current-date');
}

function renderInvestmentContentTable(records) {
    if (!records.length) return '<div class="investment-empty">暂无内容记录</div>';
    const rows = records.map(record => {
        const serviceType = record.service_type || '';
        const canGenerate = record.status !== 'generating';
        const actionServiceType = escapeHtml(serviceType);
        return `<tr>
            <td class="investment-mono">${escapeHtml((record.content_id || '').slice(0, 8))}</td>
            <td>${investmentServiceLabel(record.service_type)}</td>
            <td>${escapeHtml(record.effective_date || '-')}</td>
            <td>v${escapeHtml(record.content_version || 1)}</td>
            <td><span class="investment-badge ${investmentStatusClass(record.status)}">${investmentStatusLabel(record.status)}</span></td>
            <td><span class="investment-muted-inline">AI+渲染</span></td>
            <td>${record.output_image ? renderInvestmentFilePreview(record.output_image, '输出图片') : '<span class="investment-muted-inline">未生成</span>'}</td>
            <td>${investmentCompactText(record.status_warning || record.error_message || '', 42)}</td>
            <td>${escapeHtml(investmentFormatBeijingTime(record.created_at))}</td>
            <td class="investment-row-actions">
                ${investmentIconButton('fa-arrows-rotate', '刷新', `refreshInvestmentContentAction('${actionServiceType}')`)}
                ${canGenerate ? investmentIconButtonIfCan('content.generate', 'fa-rotate', '生成', `generateInvestmentContent('${record.content_id}', '${actionServiceType}')`) : ''}
                ${record.output_image ? investmentIconButtonIfCan('content.publish', 'fa-circle-check', '设为生效', `effectiveInvestmentContent('${record.content_id}', '${actionServiceType}')`, 'primary') : ''}
                ${investmentIconButton('fa-circle-info', '详情', `showInvestmentContentDetail('${investmentEncodedRecord(record)}')`)}
            </td>
        </tr>`;
    }).join('');
    return investmentTableWrap(`<table class="investment-table">
        <thead><tr><th>ID</th><th>类型</th><th>生效日期</th><th>版本</th><th>状态</th><th>模式</th><th>输出</th><th>失败原因</th><th>创建时间</th><th>动作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function showInvestmentContentDetail(encoded) {
    const record = JSON.parse(decodeURIComponent(encoded));
    const body = `
        <div class="investment-detail-grid">
            <div><span>类型</span><strong>${investmentServiceLabel(record.service_type)}</strong></div>
            <div><span>状态</span><strong>${investmentStatusLabel(record.status)}</strong></div>
            <div><span>操作人</span><strong>${escapeHtml(record.operator || '-')}</strong></div>
            <div><span>生效日期</span><strong>${escapeHtml(record.effective_date || '-')}</strong></div>
            <div><span>版本</span><strong>v${escapeHtml(record.content_version || 1)}</strong></div>
            <div><span>模式</span><strong>AI+渲染</strong></div>
            <div><span>创建时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')}</strong></div>
            <div><span>生效时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record.effective_at) || '-')}</strong></div>
            <div><span>失效时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record.expires_at) || '不失效')}</strong></div>
            <div><span>归档时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record.archived_at) || '-')}</strong></div>
            <div><span>输出图片</span><strong>${record.output_image ? investmentFileLinks([record.output_image]) : '-'}</strong></div>
        </div>
        <div class="investment-detail-block">
            <span>输入文件</span>
            <div>${investmentFileLinks(record.source_files || [])}</div>
        </div>
        <div class="investment-detail-block">
            <span>失败原因</span>
            <pre>${escapeHtml(record.status_warning || record.error_message || '无')}</pre>
        </div>
        <div class="investment-detail-block">
            <span>资料文本</span>
            <pre>${escapeHtml(record.source_text || '无')}</pre>
        </div>
        <div class="investment-detail-block">
            <span>生成文本</span>
            <pre>${escapeHtml(record.generated_text || '无')}</pre>
        </div>
        <div class="investment-detail-block">
            <span>产物审计</span>
            ${investmentArtifactTable(record.output_artifacts || [])}
        </div>`;
    showInvestmentModal('内容详情 ' + (record.content_id || '').slice(0, 8), body);
}

async function createInvestmentContent(generateAfterCreate) {
    const serviceType = document.getElementById('invest-content-service').value;
    const result = document.getElementById('invest-content-action-result');
    if (result) result.textContent = generateAfterCreate ? '生成中...' : '保存中...';
    const autoEffective = generateAfterCreate ? await investmentShouldAutoEffectiveAfterGenerate(serviceType) : false;
    if (autoEffective === null) return;
    const uploadMode = document.getElementById('invest-content-upload-mode')?.value || 'image';
    const sourceText = uploadMode === 'text'
        ? document.getElementById('invest-content-source-text')?.value || ''
        : document.getElementById('invest-content-supplement-text')?.value || '';
    const form = new FormData();
    form.append('service_type', serviceType);
    form.append('source_text', sourceText);
    form.append('operator', investmentCurrentAdminUsername());
    form.append('expires_at', investmentContentExpiresAtValue());
    form.append('auto_effective_after_generate', autoEffective ? '1' : '0');
    Array.from(document.getElementById('invest-content-files').files || []).forEach(file => form.append('files', file));
    try {
        const created = await investmentFetchJson('/api/investment/daily-content', {method: 'POST', body: form});
        let message = '已保存';
        showInvestmentToast('已保存');
        if (generateAfterCreate) {
            try {
                await investmentFetchJson(`/api/investment/daily-content/${encodeURIComponent(created.content_id)}/generate`, {method: 'POST'});
                message = autoEffective ? '已保存，生成任务已启动，生成成功后会自动设为生效图' : '已保存，生成任务已启动';
                showInvestmentToast(autoEffective ? '已启动生成，成功后自动生效' : '已启动生成');
            } catch (error) {
                message = `已保存，生成启动失败：${String(error.message || error)}`;
                showInvestmentToast('生成启动失败', 'error');
            }
        }
        await renderInvestmentContent(serviceType, {message});
    } catch (error) {
        if (result) result.textContent = String(error.message || error);
        showInvestmentToast('保存内容失败', 'error');
    }
}

async function generateInvestmentContent(contentId, serviceType = '') {
    const targetServiceType = serviceType || currentInvestmentContentServiceType();
    try {
        await investmentFetchJson(`/api/investment/daily-content/${encodeURIComponent(contentId)}/generate`, {method: 'POST'});
        showInvestmentToast('已启动生成');
    } catch (error) {
        showInvestmentToast(`生成启动失败：${String(error.message || error)}`, 'error');
    } finally {
        if (currentView === 'invest-records') {
            await renderInvestmentRecords();
        } else {
            await refreshInvestmentContentRecords(targetServiceType);
        }
    }
}

async function effectiveInvestmentContent(contentId, serviceType = '') {
    const targetServiceType = serviceType || currentInvestmentContentServiceType();
    const effectiveDate = window.prompt('生效日期（YYYY-MM-DD）', investmentTodayDate());
    if (effectiveDate === null) return;
    try {
        await investmentFetchJson(`/api/investment/daily-content/${encodeURIComponent(contentId)}/effective`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({operator: 'admin', effective_date: effectiveDate || investmentTodayDate()}),
        });
        showInvestmentToast('已设为生效');
        if (currentView === 'invest-records') {
            await renderInvestmentRecords();
        } else {
            await renderInvestmentContent(targetServiceType, {effective_date: investmentContentHistoryEffectiveDate(targetServiceType)});
        }
    } catch (error) {
        showInvestmentToast(`设置生效失败：${String(error.message || error)}`, 'error');
    }
}

async function renderInvestmentOperationAudits(targetId = '') {
    const params = new URLSearchParams({limit: '80'});
    if (targetId) {
        params.set('target_type', 'daily_content');
        params.set('target_id', targetId);
    }
    try {
        const data = await investmentFetchJson(`/api/investment/audits?${params.toString()}`);
        const audits = data.audits || [];
        const body = audits.length ? `
            <div class="investment-audit-list">
                ${audits.map(audit => `
                    <div class="investment-audit-item">
                        <div>
                            <strong>${escapeHtml(audit.action || '-')}</strong>
                            <span>${escapeHtml(audit.target_type || '-')}${audit.target_id ? ' / ' + escapeHtml(String(audit.target_id).slice(0, 8)) : ''}</span>
                        </div>
                        <div>
                            <span>${escapeHtml(audit.operator || '-')}</span>
                            <span>${escapeHtml(investmentFormatBeijingTime(audit.created_at) || '-')}</span>
                        </div>
                        <pre>${escapeHtml(JSON.stringify(audit.detail || {}, null, 2))}</pre>
                    </div>
                `).join('')}
            </div>
        ` : '<div class="investment-empty">暂无操作流水</div>';
        showInvestmentModal('操作流水', body);
    } catch (error) {
        showInvestmentToast(`加载操作流水失败：${String(error.message || error)}`, 'error');
    }
}

async function renderInvestmentRecordsLegacy() {
    const element = investmentContentEl('invest-records-content');
    investmentLoading(element);
    try {
        const cacheRequest = investmentCan('cache.read') ? investmentFetchJson('/api/investment/cache') : Promise.resolve({entries: []});
        const [requests, contents, caches] = await Promise.all([
            investmentFetchJson('/api/investment/records/requests'),
            investmentFetchJson('/api/investment/records/contents'),
            cacheRequest,
        ]);
        const cacheSection = investmentCan('cache.read') ? `
                <section class="investment-table-panel full">
                    <div class="investment-panel-heading">
                        <div class="investment-panel-title"><i class="fas fa-database"></i><span>技术分析缓存</span></div>
                        <div class="investment-panel-actions">
                            ${investmentButtonIfCan('cache.write', 'fa-broom', '清理当日技术分析', 'clearInvestmentTechnicalAnalysisCacheByDate()')}
                        </div>
                    </div>
                    ${renderInvestmentCacheTable(caches.entries || [])}
                </section>` : '';
        element.innerHTML = `
            <div class="investment-workbench">
                <section class="investment-panel investment-workbench-full">
                    <div class="investment-panel-heading">
                        <div>
                            <div class="investment-panel-title"><i class="fas fa-table-list"></i><span>业务记录</span></div>
                            <div class="investment-subtitle">默认紧凑展示，完整失败原因和输出文件在详情中查看。</div>
                        </div>
                        <div class="investment-panel-actions">
                            ${investmentButton('fa-arrows-rotate', '刷新记录', 'renderInvestmentRecords()', 'primary')}
                        </div>
                    </div>
                    <div class="investment-grid cols-3">
                        ${investmentField('开始日期', 'invest-export-start-date', '', 'date')}
                        ${investmentField('结束日期', 'invest-export-end-date', '', 'date')}
                        <label class="investment-field">
                            <span>服务类型</span>
                            ${investmentDropdown('invest-export-service-type', [['', '全部'], ['technical_analysis', '技术分析'], ['rate', '利率'], ['convertible_bond', '转债']], '')}
                        </label>
                    </div>
                    <div class="investment-actions">
                        ${investmentButtonIfCan('records.export', 'fa-download', '按范围导出', 'exportInvestmentRequestRecordsByRange()', 'primary')}
                        <label class="investment-field">
                            <span>月度</span>
                            <input id="invest-export-month" type="month">
                        </label>
                        ${investmentButtonIfCan('records.export', 'fa-calendar-days', '导出月度', 'exportInvestmentRequestRecordsByMonth()')}
                        <label class="investment-field">
                            <span>年度</span>
                            <input id="invest-export-quarter-year" type="number" min="2000" max="2100" value="${new Date().getFullYear()}">
                        </label>
                        <label class="investment-field">
                            <span>季度</span>
                            ${investmentDropdown('invest-export-quarter', [['1', 'Q1'], ['2', 'Q2'], ['3', 'Q3'], ['4', 'Q4']], '1')}
                        </label>
                        ${investmentButtonIfCan('records.export', 'fa-chart-pie', '导出季度', 'exportInvestmentRequestRecordsByQuarter()')}
                    </div>
                </section>
                <section class="investment-table-panel full">
                    <div class="investment-panel-title"><i class="fas fa-message"></i><span>公众号请求记录</span></div>
                    ${renderInvestmentRequestRecordsTable(requests.records || [])}
                </section>
                <section class="investment-table-panel full">
                    <div class="investment-panel-title"><i class="fas fa-gears"></i><span>后台生成记录</span></div>
                    ${renderInvestmentContentTable(contents.records || [])}
                    <div id="invest-content-detail" data-investment-detail-panel class="investment-detail-panel hidden"></div>
                </section>
                ${cacheSection}
                <section class="investment-panel investment-workbench-full">
                    <div id="invest-record-detail" data-investment-detail-panel class="investment-detail-panel hidden"></div>
                </section>
            </div>`;
    } catch (error) {
        investmentError(element, error);
    }
}

function investmentExportServiceType() {
    return document.getElementById('invest-export-service-type')?.value || '';
}

function investmentExportCustomer() {
    return document.getElementById('invest-export-customer')?.value || '';
}

function changeInvestmentRequestExportMode(mode) {
    const allowed = ['full', 'range', 'month', 'quarter'];
    investmentRecordsState.exportMode = allowed.includes(mode) ? mode : 'range';
    const modalBody = document.getElementById('investment-modal-body');
    if (modalBody) {
        modalBody.innerHTML = renderInvestmentRequestExportDialogBody();
        initInvestmentDropdowns(modalBody);
    }
}

function exportInvestmentRequestRecordsByCurrentFilters() {
    investmentRecordsSetFilterValues('requests', {resetPage: false});
    const params = investmentRecordsQueryParams('requests');
    params.delete('page');
    params.delete('page_size');
    investmentDownload('/api/investment/export/requests.xlsx', Object.fromEntries(params.entries()));
}

function exportInvestmentRequestRecordsFull() {
    investmentDownload('/api/investment/export/requests.xlsx', {
        service_type: investmentExportServiceType(),
        customer: investmentExportCustomer(),
    });
}

function exportInvestmentRequestRecordsByRange() {
    const startDate = document.getElementById('invest-export-start-date')?.value || '';
    const endDate = document.getElementById('invest-export-end-date')?.value || '';
    if (!startDate || !endDate) {
        showInvestmentToast('请选择导出开始和结束日期', 'error');
        return;
    }
    if (startDate > endDate) {
        showInvestmentToast('导出开始日期不能晚于结束日期', 'error');
        return;
    }
    investmentDownload('/api/investment/export/requests.xlsx', {
        start_date: startDate,
        end_date: endDate,
        service_type: investmentExportServiceType(),
        customer: investmentExportCustomer(),
    });
}

function exportInvestmentRequestRecordsByMonth() {
    const value = document.getElementById('invest-export-month')?.value || '';
    if (!value) {
        showInvestmentToast('请选择导出月份', 'error');
        return;
    }
    const [year, month] = value.split('-');
    investmentDownload('/api/investment/export/requests.xlsx', {
        year,
        month,
        service_type: investmentExportServiceType(),
        customer: investmentExportCustomer(),
    });
}

function exportInvestmentRequestRecordsByQuarter() {
    const year = document.getElementById('invest-export-quarter-year')?.value || '';
    if (!year) {
        showInvestmentToast('请选择导出年度', 'error');
        return;
    }
    investmentDownload('/api/investment/export/requests.xlsx', {
        year,
        quarter: document.getElementById('invest-export-quarter')?.value || '',
        service_type: investmentExportServiceType(),
        customer: investmentExportCustomer(),
    });
}

function renderInvestmentRequestRecordsTableLegacy(records) {
    if (!records.length) return '<div class="investment-empty">暂无公众号请求记录</div>';
    const rows = records.map(record => `<tr>
        <td class="investment-mono">${escapeHtml((record.request_id || '').slice(0, 8))}</td>
        <td>${investmentCompactText(record.openid || '', 22)}</td>
        <td>${investmentCompactText(record.raw_input || '', 32)}</td>
        <td>${investmentServiceLabel(record.service_type)}</td>
        <td><span class="investment-badge ${record.status === 'success' ? 'ok' : 'fail'}">${investmentStatusLabel(record.status)}</span></td>
        <td>${escapeHtml(record.error_code || '')}</td>
        <td>${record.cache_hit ? '<span class="investment-badge ok">命中</span>' : '<span class="investment-badge">未命中</span>'}</td>
        <td>${investmentCompactText(record.status_warning || record.error_message || record.user_prompt || '', 42)}</td>
        <td>${investmentFileSummary(record.output_files || [])}</td>
        <td>${escapeHtml(investmentFormatBeijingTime(record.created_at))}</td>
        <td class="investment-row-actions">${investmentIconButton('fa-circle-info', '详情', `showInvestmentRequestDetail('${investmentEncodedRecord(record)}')`)}</td>
    </tr>`).join('');
    return investmentTableWrap(`<table class="investment-table">
        <thead><tr><th>ID</th><th>OpenID</th><th>输入</th><th>服务</th><th>状态</th><th>错误码</th><th>缓存</th><th>失败原因</th><th>输出文件</th><th>时间</th><th>动作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function renderInvestmentCacheTableLegacy(entries) {
    if (!entries.length) return '<div class="investment-empty">暂无技术分析缓存</div>';
    const rows = entries.map(entry => `<tr>
        <td class="investment-mono">${investmentCompactText(entry.cache_key || '', 34)}</td>
        <td>${investmentServiceLabel(entry.service_type)}</td>
        <td>${escapeHtml(entry.normalized_target || '')}</td>
        <td>${escapeHtml(entry.market_date || '')}</td>
        <td>${escapeHtml(entry.hit_count ?? 0)}</td>
        <td>${investmentFileSummary(entry.output_files || [])}</td>
        <td class="investment-row-actions">${investmentIconButtonIfCan('cache.write', 'fa-ban', '失效', `invalidateInvestmentCache('${encodeURIComponent(entry.cache_key || '')}')`, 'danger')}</td>
    </tr>`).join('');
    return investmentTableWrap(`<table class="investment-table">
        <thead><tr><th>Key</th><th>服务</th><th>标的</th><th>日期</th><th>命中</th><th>输出</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

async function invalidateInvestmentCache(encodedKey) {
    try {
        await investmentFetchJson(`/api/investment/cache/${encodedKey}/invalidate`, {method: 'POST'});
        if (currentView === 'invest-content') {
            await loadInvestmentGeneratedContent();
            return;
        }
        await renderInvestmentRecords();
    } catch (error) {
        showInvestmentToast(`缓存失效失败：${String(error.message || error)}`, 'error');
    }
}

async function clearInvestmentTechnicalAnalysisCacheByDate() {
    const today = investmentTodayDate();
    const marketDate = prompt('清理技术分析缓存日期', today);
    if (!marketDate) return;
    try {
        await investmentFetchJson('/api/investment/cache/clear', {
            method: 'POST',
            body: JSON.stringify({service_type: 'technical_analysis', market_date: marketDate}),
        });
        await renderInvestmentRecords();
    } catch (error) {
        showInvestmentToast(`缓存清理失败：${String(error.message || error)}`, 'error');
    }
}

function showInvestmentRequestDetail(encoded) {
    const record = JSON.parse(decodeURIComponent(encoded));
    const body = `
        <div class="investment-detail-grid">
            <div><span>OpenID</span><strong>${escapeHtml(record.openid || '-')}</strong></div>
            <div><span>服务</span><strong>${investmentServiceLabel(record.service_type)}</strong></div>
            <div><span>状态</span><strong>${investmentStatusLabel(record.status)}</strong></div>
            <div><span>错误码</span><strong>${escapeHtml(record.error_code || '-')}</strong></div>
            <div><span>耗时</span><strong>${escapeHtml(record.elapsed_ms ?? '-')} ms</strong></div>
            <div><span>时间</span><strong>${escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')}</strong></div>
        </div>
        <div class="investment-detail-block">
            <span>原始输入</span>
            <pre>${escapeHtml(record.raw_input || '无')}</pre>
        </div>
        <div class="investment-detail-block">
            <span>用户提示</span>
            <pre>${escapeHtml(record.user_prompt || '无')}</pre>
        </div>
        <div class="investment-detail-block">
            <span>失败原因</span>
            <pre>${escapeHtml(record.status_warning || record.error_message || '无')}</pre>
        </div>
        <div class="investment-detail-block">
            <span>输出文件</span>
            <div>${investmentFileLinks(record.output_files || [])}</div>
        </div>
        <div class="investment-detail-block">
            <span>审计字段</span>
            <pre>${escapeHtml(JSON.stringify({
                customer_name: record.customer_name || '',
                institution: record.institution || '',
                normalized_target: record.normalized_target || '',
                stock_code: record.stock_code || '',
                stock_name: record.stock_name || '',
                market_date: record.market_date || '',
                cache_key: record.cache_key || '',
                cache_hit: Boolean(record.cache_hit),
                program_version: record.program_version || '',
                ta_version: record.ta_version || '',
                renderer_version: record.renderer_version || '',
                template_version: record.template_version || ''
            }, null, 2))}</pre>
        </div>
        <div class="investment-detail-block">
            <span>产物审计</span>
            ${investmentArtifactTable(record.output_artifacts || [])}
        </div>`;
    showInvestmentModal('请求详情 ' + (record.request_id || '').slice(0, 8), body);
}

function investmentRecordsQueryParams(tab) {
    const params = new URLSearchParams();
    const filters = investmentRecordsState.filters[tab] || {};
    params.set('page', filters.page || '1');
    params.set('page_size', filters.page_size || investmentRecordsDefaultPageSize(tab));
    if ((tab === 'requests' || tab === 'contents' || tab === 'audits') && filters.date_mode === 'month') {
        const bounds = investmentRecordMonthBounds(tab, filters.record_month || investmentTodayDate().slice(0, 7));
        params.set('start_date', bounds.start);
        params.set('end_date', bounds.end);
    }
    Object.entries(filters).forEach(([key, value]) => {
        if (key === 'page' || key === 'page_size') return;
        if (key === 'date_mode' || key === 'record_month' || key === 'effective_date') return;
        if ((tab === 'requests' || tab === 'contents' || tab === 'audits') && filters.date_mode === 'month' && (key === 'start_date' || key === 'end_date')) return;
        if (value !== undefined && value !== null && String(value) !== '') {
            params.set(key, value);
        }
    });
    return params;
}

function investmentRecordsDefaultPageSize(tab) {
    return tab === 'cache' ? '120' : '80';
}

function investmentRecordsDefaultFilters(tab) {
    if (tab === 'requests') {
        return {
            page: '1',
            page_size: investmentRecordsDefaultPageSize(tab),
            date_mode: 'day',
            start_date: investmentTodayDate(),
            end_date: investmentTodayDate(),
            record_month: investmentTodayDate().slice(0, 7),
        };
    }
    if (tab === 'cache') {
        return {page: '1', page_size: investmentRecordsDefaultPageSize(tab), period_mode: 'day', market_date: investmentTodayDate()};
    }
    if (tab === 'audits') {
        return {
            page: '1',
            page_size: investmentRecordsDefaultPageSize(tab),
            date_mode: 'day',
            start_date: investmentTodayDate(),
            end_date: investmentTodayDate(),
            record_month: investmentTodayDate().slice(0, 7),
        };
    }
    if (tab === 'contents') {
        return {
            page: '1',
            page_size: investmentRecordsDefaultPageSize(tab),
            keyword: '',
            date_mode: 'day',
            start_date: investmentTodayDate(),
            end_date: investmentTodayDate(),
            record_month: investmentTodayDate().slice(0, 7),
        };
    }
    return {page: '1', page_size: investmentRecordsDefaultPageSize(tab)};
}

function investmentRecordsFilterValue(key) {
    const id = `investment-records-filter-${key}`;
    return document.getElementById(id)?.value || '';
}

function investmentRecordsSetFilterValues(tab, options = {}) {
    const filters = {...(investmentRecordsState.filters[tab] || {})};
    document.querySelectorAll('[data-investment-records-filter]').forEach(input => {
        filters[input.dataset.investmentRecordsFilter] = input.value || '';
    });
    if (tab === 'requests' || tab === 'contents' || tab === 'audits') {
        filters.date_mode = filters.date_mode === 'month' ? 'month' : 'day';
        if (!filters.record_month) filters.record_month = investmentTodayDate().slice(0, 7);
        if (filters.date_mode === 'day') {
            if (!filters.start_date) filters.start_date = investmentTodayDate();
            if (!filters.end_date) filters.end_date = filters.start_date;
        }
    }
    if (!filters.page_size) filters.page_size = investmentRecordsDefaultPageSize(tab);
    if (options.resetPage) {
        filters.page = '1';
    }
    if (!filters.page) filters.page = '1';
    investmentRecordsState.filters[tab] = filters;
}

function investmentRequestRecordMonthOptions() {
    return investmentRecordMonthOptions();
}

function investmentRecordMonthOptions() {
    return investmentRequestExportMonthOptions();
}

function investmentRecordMonthBounds(tab, monthValue) {
    const value = /^\d{4}-\d{2}$/.test(String(monthValue || '')) ? String(monthValue) : investmentTodayDate().slice(0, 7);
    const [year, month] = value.split('-').map(item => Number(item));
    const lastDay = new Date(year, month, 0).getDate();
    return {
        start: `${value}-01`,
        end: `${value}-${String(lastDay).padStart(2, '0')}`,
    };
}

function investmentRequestMonthBounds(monthValue) {
    return investmentRecordMonthBounds('requests', monthValue);
}

function changeInvestmentRecordDateMode(tab, mode) {
    if (!['requests', 'contents', 'audits'].includes(tab)) tab = 'requests';
    const filters = investmentRecordsState.filters[tab] || investmentRecordsDefaultFilters(tab);
    investmentRecordsState.filters[tab] = {
        ...filters,
        date_mode: mode === 'month' ? 'month' : 'day',
        record_month: filters.record_month || investmentTodayDate().slice(0, 7),
        start_date: filters.start_date || investmentTodayDate(),
        end_date: filters.end_date || filters.start_date || investmentTodayDate(),
    };
    const container = document.getElementById('investment-records-filters');
    if (container) {
        container.innerHTML = renderInvestmentRecordsFilters(tab);
        initInvestmentDropdowns(container);
    }
}

function changeInvestmentRequestDateMode(mode) {
    changeInvestmentRecordDateMode('requests', mode);
}

function investmentCacheMarketDate() {
    return investmentRecordsState.filters.cache?.market_date || document.getElementById('investment-records-filter-market_date')?.value || '';
}

function investmentCacheKeyword() {
    return investmentRecordsState.filters.cache?.keyword || document.getElementById('investment-content-filter-keyword')?.value || '';
}

function investmentCachePeriodMode() {
    return document.getElementById('investment-content-period-mode')?.value || investmentRecordsState.filters.cache?.period_mode || 'all';
}

function investmentCachePeriodValue() {
    return document.getElementById('investment-content-period-value')?.value || investmentRecordsState.filters.cache?.period_value || '';
}

function investmentGeneratedDateValues(marketDates = [], entries = []) {
    const values = new Set(Array.isArray(marketDates) ? marketDates : []);
    (Array.isArray(entries) ? entries : []).forEach(entry => {
        if (entry?.market_date) values.add(entry.market_date);
        if (entry?.effective_date) values.add(entry.effective_date);
    });
    return Array.from(values).filter(value => /^\d{4}-\d{2}-\d{2}$/.test(String(value))).sort().reverse();
}

function investmentGeneratedDefaultPeriodValue(mode) {
    const today = investmentTodayDate();
    if (mode === 'year') return today.slice(0, 4);
    if (mode === 'month') return today.slice(0, 7);
    return '';
}

function investmentGeneratedPeriodOptions(mode, marketDates = [], entries = []) {
    const normalized = mode === 'year' ? 'year' : 'month';
    const values = investmentGeneratedDateValues(marketDates, entries).map(dateValue => (
        normalized === 'year' ? dateValue.slice(0, 4) : dateValue.slice(0, 7)
    ));
    values.push(investmentGeneratedDefaultPeriodValue(normalized));
    return Array.from(new Set(values.filter(Boolean))).sort().reverse().map(value => [value, normalized === 'year' ? `${value} 年` : `${value} 月`]);
}

function renderInvestmentGeneratedPeriodValueControl(mode, marketDates = [], entries = []) {
    const normalized = mode === 'year' ? 'year' : 'month';
    return `
        <span>${normalized === 'year' ? '年份' : '月份'}</span>
        ${investmentDropdown('investment-content-period-value', investmentGeneratedPeriodOptions(normalized, marketDates, entries), investmentCachePeriodValue() || investmentGeneratedDefaultPeriodValue(normalized), '', 'scheduleInvestmentCacheFilterRefresh()')}`;
}

function investmentNormalizeCacheDateFilters() {
    const periodMode = investmentCachePeriodMode();
    if (periodMode === 'day') {
        const marketDate = document.getElementById('investment-records-filter-market_date')?.value || investmentRecordsState.filters.cache?.market_date || investmentTodayDate();
        return {mode: periodMode, marketDate, startDate: '', endDate: '', label: marketDate};
    }
    const periodValue = investmentCachePeriodValue().trim();
    if (periodMode === 'month' && /^\d{4}-\d{2}$/.test(periodValue)) {
        const [year, month] = periodValue.split('-').map(Number);
        const lastDay = new Date(year, month, 0).getDate();
        return {
            mode: periodMode,
            marketDate: '',
            startDate: `${periodValue}-01`,
            endDate: `${periodValue}-${investmentPadDatePart(lastDay)}`,
            label: `${periodValue} 全月`,
        };
    }
    if (periodMode === 'year' && /^\d{4}$/.test(periodValue)) {
        return {
            mode: periodMode,
            marketDate: '',
            startDate: `${periodValue}-01-01`,
            endDate: `${periodValue}-12-31`,
            label: `${periodValue} 全年`,
        };
    }
    return {mode: 'all', marketDate: '', startDate: '', endDate: '', label: '全部历史'};
}

function scheduleInvestmentCacheFilterRefresh(delay = 260) {
    clearTimeout(investmentCacheFilterRefreshTimer);
    investmentCacheFilterRefreshTimer = setTimeout(() => {
        applyInvestmentCacheDate().catch(error => console.error('Investment generated content refresh failed:', error));
    }, delay);
}

function investmentChangeCachePeriodMode(mode) {
    investmentRecordsState.filters.cache.period_mode = ['all', 'day', 'month', 'year'].includes(mode) ? mode : 'all';
    syncInvestmentCachePeriodMode(investmentRecordsState.filters.cache.period_mode);
    scheduleInvestmentCacheFilterRefresh();
}

function syncInvestmentCachePeriodMode(mode) {
    const normalized = ['all', 'day', 'month', 'year'].includes(mode) ? mode : 'all';
    const dateField = document.getElementById('investment-content-period-date-field');
    const valueField = document.getElementById('investment-content-period-value-field');
    const valueInput = document.getElementById('investment-content-period-value');
    if (dateField) dateField.classList.toggle('hidden', normalized !== 'day');
    if (valueField) valueField.classList.toggle('hidden', !['month', 'year'].includes(normalized));
    if (normalized === 'day') {
        const dateInput = document.getElementById('investment-records-filter-market_date');
        if (dateInput && !dateInput.value) {
            investmentSetDatePickerValue('investment-records-filter-market_date', investmentTodayDate());
        }
    }
    if (valueField && ['month', 'year'].includes(normalized)) {
        valueField.innerHTML = renderInvestmentGeneratedPeriodValueControl(
            normalized,
            investmentRecordsState.data.cache?.market_dates || [],
            investmentRecordsState.data.cache?.entries || [],
        );
        initInvestmentDropdowns(valueField);
    }
    if (valueInput) {
        if (['month', 'year'].includes(normalized) && !valueInput.value) {
            valueInput.value = investmentGeneratedDefaultPeriodValue(normalized);
        }
    }
}

async function renderInvestmentGeneratedContent() {
    const element = investmentContentEl('invest-content-content');
    if (!element) return;
    element.innerHTML = `
        <div class="investment-content-workspace">
            <section class="investment-content-shell">
                <div class="investment-content-list" id="investment-content-list"></div>
            </section>
        </div>`;
    await loadInvestmentGeneratedContent();
}

async function loadInvestmentGeneratedContent() {
    const list = document.getElementById('investment-content-list');
    if (list) investmentLoading(list);
    try {
        const query = investmentRecordsQueryParams('cache');
        const range = investmentNormalizeCacheDateFilters();
        query.delete('market_date');
        query.delete('start_date');
        query.delete('end_date');
        if (range.marketDate) {
            query.set('start_date', range.marketDate);
            query.set('end_date', range.marketDate);
        }
        if (range.startDate) query.set('start_date', range.startDate);
        if (range.endDate) query.set('end_date', range.endDate);
        query.set('level', 'service');
        const data = await investmentFetchJson(query.toString() ? `/api/investment/artifact-folders?${query.toString()}` : '/api/investment/artifact-folders?level=service');
        const packages = (data.nodes || []).map(node => ({
            source_type: 'artifact_folder',
            service_type: node.key,
            request_count: node.count || 0,
            updated_at: node.updated_at || '',
        }));
        investmentRecordsState.data.cache = {
            entries: packages,
            packages,
            tree: data.nodes || [],
            market_dates: investmentGeneratedDateValues([], packages),
        };
        investmentRecordsApplyPagination('cache', data.pagination);
        if (list) list.innerHTML = renderInvestmentDailyGeneratedContent(investmentRecordsState.data.cache);
        syncInvestmentCachePeriodMode(investmentCachePeriodMode());
        if (investmentRecordsState.cacheCategory) await loadInvestmentArtifactRootNodes(investmentRecordsState.cacheCategory);
        closeInvestmentRecordDrawer();
    } catch (error) {
        investmentError(list, error);
    }
}

function renderInvestmentRecordsShell() {
    return `
        <div class="investment-records-workspace">
            <section class="investment-records-summary" id="investment-records-summary">${renderInvestmentRecordsSummary()}</section>
            <section class="investment-records-board">
                <div class="investment-records-tabs">
                    ${renderInvestmentRecordsTabButton('requests', '公众号请求', 'fa-message')}
                    ${renderInvestmentRecordsTabButton('contents', '后台生成', 'fa-gears')}
                    ${renderInvestmentRecordsTabButton('audits', '操作流水', 'fa-clock-rotate-left')}
                </div>
                <div class="investment-records-filters" id="investment-records-filters">${renderInvestmentRecordsFilters(investmentRecordsState.tab)}</div>
                <div class="investment-records-main">
                    <div class="investment-records-list" id="investment-records-list"></div>
                </div>
                <div id="investment-records-pagination"></div>
            </section>
        </div>`;
}

function investmentRequestExportDefaults() {
    const filters = investmentRecordsState.filters.requests || investmentRecordsDefaultFilters('requests');
    return {
        keyword: filters.keyword || '',
        service_type: filters.service_type || '',
        status: filters.status || '',
        customer: filters.customer || '',
        start_date: filters.start_date || '',
        end_date: filters.end_date || '',
        month: investmentTodayDate().slice(0, 7),
        quarter_year: String(new Date().getFullYear()),
        quarter: String(Math.floor(new Date().getMonth() / 3) + 1),
    };
}

function investmentRequestExportMonthOptions() {
    const todayMonth = investmentTodayDate().slice(0, 7);
    const [baseYear, baseMonth] = todayMonth.split('-').map(value => Number(value));
    const options = [];
    for (let offset = 0; offset < 18; offset += 1) {
        const monthIndex = baseYear * 12 + (baseMonth - 1) - offset;
        const year = Math.floor(monthIndex / 12);
        const month = monthIndex % 12 + 1;
        const value = `${year}-${String(month).padStart(2, '0')}`;
        const label = offset === 0 ? `${value}（本月）` : value;
        options.push([value, label]);
    }
    return options;
}

function renderInvestmentRequestExportDialogBody() {
    const mode = investmentRecordsState.exportMode || 'range';
    const values = investmentRequestExportDefaults();
    const serviceField = `
        <label class="investment-field">
            <span>投资服务</span>
            ${investmentDropdown('invest-export-service-type', [['', '全部'], ['technical_analysis', '技术分析'], ['rate', '利率'], ['convertible_bond', '转债'], ['unauthorized_request', '无权限请求']], values.service_type)}
        </label>`;
    const customerField = `<label class="investment-field"><span>客户/机构/OpenID/手机号</span><input id="invest-export-customer" type="text" value="${escapeHtml(values.customer)}" placeholder="留空表示全部客户"></label>`;
    const fieldsByMode = {
        full: `
            <div class="investment-request-export-note">可按下方条件缩小范围。</div>
            ${customerField}
            ${serviceField}`,
        range: `
            ${investmentField('开始日期', 'invest-export-start-date', values.start_date, 'date')}
            ${investmentField('结束日期', 'invest-export-end-date', values.end_date, 'date')}
            ${customerField}
            ${serviceField}`,
        month: `
            <label class="investment-field"><span>自然月</span>${investmentDropdown('invest-export-month', investmentRequestExportMonthOptions(), values.month)}</label>
            ${customerField}
            ${serviceField}`,
        quarter: `
            <label class="investment-field"><span>年度</span><input id="invest-export-quarter-year" type="number" min="2000" max="2100" value="${escapeHtml(values.quarter_year)}"></label>
            <label class="investment-field">
                <span>自然季度</span>
                ${investmentDropdown('invest-export-quarter', [['1', 'Q1（1-3月）'], ['2', 'Q2（4-6月）'], ['3', 'Q3（7-9月）'], ['4', 'Q4（10-12月）']], values.quarter)}
            </label>
            ${customerField}
            ${serviceField}`,
    };
    const actionsByMode = {
        full: investmentButtonIfCan('records.export', 'fa-download', '全量导出', 'exportInvestmentRequestRecordsFull()', 'primary'),
        range: investmentButtonIfCan('records.export', 'fa-download', '导出范围', 'exportInvestmentRequestRecordsByRange()', 'primary'),
        month: investmentButtonIfCan('records.export', 'fa-calendar-days', '导出月度', 'exportInvestmentRequestRecordsByMonth()', 'primary'),
        quarter: investmentButtonIfCan('records.export', 'fa-chart-pie', '导出季度', 'exportInvestmentRequestRecordsByQuarter()', 'primary'),
    };
    return `
        <section data-investment-request-export-dialog class="investment-request-export-dialog">
            <div class="investment-request-export-layout">
                <div class="investment-request-export-aside">
                    <div class="investment-panel-title"><i class="fas fa-file-export"></i><span>公众号请求导出</span></div>
                    <p>选择导出范围后下载 Excel 文件。客户和机构筛选会匹配 OpenID、手机号、姓名、机构。</p>
                    <div class="investment-request-export-format"><i class="fas fa-file-excel"></i><span>导出格式：Excel</span></div>
                </div>
                <div class="investment-request-export-main">
                    <div class="investment-request-export-mode-grid">
                        ${investmentRequestExportModeButton('full', '全量导出', 'fa-download')}
                        ${investmentRequestExportModeButton('range', '按时间范围导出', 'fa-calendar-days')}
                        ${investmentRequestExportModeButton('month', '按月度导出', 'fa-calendar')}
                        ${investmentRequestExportModeButton('quarter', '按季度导出', 'fa-chart-pie')}
                    </div>
                    <div class="investment-request-export-form">
                        <div class="investment-request-export-fields">
                            ${fieldsByMode[mode] || fieldsByMode.range}
                        </div>
                        <div class="investment-request-export-footer">
                            <div class="investment-request-export-note">月份和季度按自然月、自然季度处理；留空字段表示不限。</div>
                            <div class="investment-request-export-action">${actionsByMode[mode] || actionsByMode.range}</div>
                        </div>
                    </div>
                </div>
            </div>
        </section>`;
}

function openInvestmentRequestExportDialog() {
    investmentRecordsSetFilterValues('requests', {resetPage: false});
    investmentRecordsState.exportMode = investmentRecordsState.exportMode === 'current' ? 'range' : (investmentRecordsState.exportMode || 'range');
    showInvestmentModal('导出业务记录', renderInvestmentRequestExportDialogBody());
    initInvestmentDropdowns(document.getElementById('investment-modal-body'));
}

function investmentRequestExportModeButton(mode, label, icon) {
    const active = (investmentRecordsState.exportMode || 'range') === mode ? ' active' : '';
    return `<button class="investment-request-export-mode${active}" onclick="changeInvestmentRequestExportMode('${mode}')"><i class="fas ${icon}"></i><span>${label}</span></button>`;
}

function renderInvestmentRecordsTabButton(tab, label, icon) {
    const active = investmentRecordsState.tab === tab ? ' active' : '';
    return `<button class="investment-records-tab${active}" onclick="switchInvestmentRecordsTab('${tab}')"><i class="fas ${icon}"></i><span>${label}</span></button>`;
}

function renderInvestmentRecordsSummary() {
    const requests = investmentRecordsState.data.requests || [];
    const today = investmentTodayDate();
    const todays = requests.filter(record => String(investmentFormatBeijingTime(record.created_at)).slice(0, 10) === today);
    const failures = requests.filter(record => record.status === 'failed').length;
    const running = requests.filter(record => record.status === 'generating' || record.status_warning).length;
    const cacheHits = requests.filter(record => record.cache_hit).length;
    return `
        <div class="investment-records-stat"><span>今日请求</span><strong>${todays.length}</strong></div>
        <div class="investment-records-stat"><span>失败记录</span><strong>${failures}</strong></div>
        <div class="investment-records-stat"><span>生成中/超时</span><strong>${running}</strong></div>
        <div class="investment-records-stat"><span>缓存命中</span><strong>${cacheHits}</strong></div>`;
}

function renderInvestmentRecordsFilters(tab) {
    const filters = investmentRecordsState.filters[tab] || {};
    const field = (key, label, type = 'text') => `
        <label class="investment-field">
            <span>${label}</span>
            ${type === 'date'
                ? investmentRenderDateControl(`investment-records-filter-${key}`, filters[key] || '', {placeholder: '选择日期', attrs: `data-investment-records-filter="${key}"`})
                : `<input id="investment-records-filter-${key}" data-investment-records-filter="${key}" type="${type}" value="${escapeHtml(filters[key] || '')}">`}
        </label>`;
    const select = (key, label, options, attrs = '', onChange = '') => `
        <label class="investment-field">
            <span>${label}</span>
            ${investmentDropdown(`investment-records-filter-${key}`, options, filters[key] || '', `data-investment-records-filter="${key}" ${attrs}`, onChange)}
        </label>`;
    let controls = '';
    if (tab === 'requests') {
        const isMonthMode = (filters.date_mode || 'day') === 'month';
        controls = `
            <div class="investment-request-search-slot">${field('keyword', '客户/输入/错误')}</div>
            <div class="investment-request-filter-selects">
                ${select('service_type', '服务', [['', '全部'], ['technical_analysis', '技术分析'], ['rate', '利率'], ['convertible_bond', '转债'], ['unauthorized_request', '无权限请求']])}
                ${select('status', '状态', [['', '全部'], ['success', '成功'], ['failed', '失败'], ['generating', '生成中']])}
            </div>
            <div class="investment-request-date-panel">
                ${select('date_mode', '日期方式', [['day', '日'], ['month', '月']], '', 'changeInvestmentRequestDateMode(value)')}
                <div class="investment-request-date-controls">
                    <div class="request-date-range-field ${isMonthMode ? 'hidden' : ''}">${field('start_date', '开始日期', 'date')}</div>
                    <div class="request-date-range-field ${isMonthMode ? 'hidden' : ''}">${field('end_date', '结束日期', 'date')}</div>
                    <div class="record-month-field ${isMonthMode ? '' : 'hidden'}">${select('record_month', '月份', investmentRequestRecordMonthOptions())}</div>
                </div>
            </div>`;
    } else if (tab === 'contents') {
        const isMonthMode = (filters.date_mode || 'day') === 'month';
        controls = `
            <div class="investment-content-search-slot">${field('keyword', '内容/输入/输出/错误')}</div>
            <div class="investment-content-filter-selects">
                ${select('service_type', '服务', [['', '全部'], ['rate', '利率'], ['convertible_bond', '转债']])}
                ${select('status', '状态', [['', '全部'], ['running', '生成中'], ['success', '成功'], ['failed', '失败'], ['draft', '草稿'], ['generating', '旧生成中'], ['generated', '已生成'], ['generate_failed', '旧生成失败'], ['effective', '已生效'], ['archived', '已归档'], ['invalidated', '已失效']])}
            </div>
            <div class="investment-content-date-panel">
                ${select('date_mode', '日期方式', [['day', '日'], ['month', '月']], '', "changeInvestmentRecordDateMode('contents', value)")}
                <div class="investment-content-date-controls">
                    <div class="content-date-range-field ${isMonthMode ? 'hidden' : ''}">${field('start_date', '开始日期', 'date')}</div>
                    <div class="content-date-range-field ${isMonthMode ? 'hidden' : ''}">${field('end_date', '结束日期', 'date')}</div>
                    <div class="content-record-month-field ${isMonthMode ? '' : 'hidden'}">${select('record_month', '月份', investmentRecordMonthOptions())}</div>
                </div>
            </div>`;
    } else if (tab === 'cache') {
        controls = [
            select('include_invalidated', '状态范围', [['', '仅有效'], ['1', '含已失效']]),
        ].join('');
    } else {
        const isMonthMode = (filters.date_mode || 'day') === 'month';
        controls = `
            <div class="investment-audit-search-slot">${field('keyword', '关键字')}</div>
            <div class="investment-audit-meta-fields">
                ${field('action', '动作')}
                ${field('target_type', '对象类型')}
                ${field('operator', '操作人')}
            </div>
            <div class="investment-audit-date-panel">
                ${select('date_mode', '日期方式', [['day', '日'], ['month', '月']], '', "changeInvestmentRecordDateMode('audits', value)")}
                <div class="investment-audit-date-controls">
                    <div class="audit-date-range-field ${isMonthMode ? 'hidden' : ''}">${field('start_date', '开始日期', 'date')}</div>
                    <div class="audit-date-range-field ${isMonthMode ? 'hidden' : ''}">${field('end_date', '结束日期', 'date')}</div>
                    <div class="audit-record-month-field ${isMonthMode ? '' : 'hidden'}">${select('record_month', '月份', investmentRecordMonthOptions())}</div>
                </div>
            </div>`;
    }
    const toolbarClass = tab === 'requests'
        ? 'investment-records-toolbar investment-request-records-toolbar'
        : tab === 'contents'
            ? 'investment-records-toolbar investment-content-records-toolbar'
            : tab === 'audits'
                ? 'investment-records-toolbar investment-audit-records-toolbar'
                : 'investment-records-toolbar';
    const gridClass = tab === 'requests'
        ? 'investment-records-filter-grid investment-request-records-filter-grid'
        : tab === 'contents'
            ? 'investment-records-filter-grid investment-content-records-filter-grid'
            : tab === 'audits'
                ? 'investment-records-filter-grid investment-audit-records-filter-grid'
                : 'investment-records-filter-grid';
    return `
        <div class="${toolbarClass}">
            <div class="${gridClass}">${controls}</div>
            <div class="investment-records-filter-actions">
                ${investmentButton('fa-filter', '筛选', 'applyInvestmentRecordsFilters()', 'primary')}
                ${investmentButton('fa-rotate-right', '重置', 'resetInvestmentRecordsFilters()')}
                ${investmentButton('fa-arrows-rotate', '刷新', 'loadInvestmentRecordsTab()')}
                ${tab === 'requests' ? investmentButtonIfCan('records.export', 'fa-download', '导出当前结果', 'exportInvestmentRequestRecordsByCurrentFilters()', 'primary') : ''}
                ${tab === 'requests' ? investmentButtonIfCan('records.export', 'fa-file-export', '更多导出', 'openInvestmentRequestExportDialog()') : ''}
            </div>
        </div>`;
}

async function switchInvestmentRecordsTab(tab) {
    if (!['requests', 'contents', 'audits'].includes(tab)) tab = 'requests';
    investmentRecordsState.tab = tab;
    investmentRecordsState.filters[tab] = investmentRecordsState.filters[tab] || investmentRecordsDefaultFilters(tab);
    investmentRecordsState.selected = null;
    const root = investmentContentEl('invest-records-content');
    if (root) root.innerHTML = renderInvestmentRecordsShell();
    await loadInvestmentRecordsTab(tab);
}

async function applyInvestmentRecordsFilters() {
    const tab = investmentRecordsState.tab;
    investmentRecordsSetFilterValues(tab, {resetPage: true});
    await loadInvestmentRecordsTab(tab);
}

async function resetInvestmentRecordsFilters() {
    const tab = investmentRecordsState.tab;
    investmentRecordsState.filters[tab] = investmentRecordsDefaultFilters(tab);
    const filters = document.getElementById('investment-records-filters');
    if (filters) filters.innerHTML = renderInvestmentRecordsFilters(tab);
    await loadInvestmentRecordsTab(tab);
}

function investmentRecordsApplyPagination(tab, pagination = {}) {
    const current = investmentRecordsState.filters[tab] || investmentRecordsDefaultFilters(tab);
    const page = Number(pagination.page || current.page || 1);
    const pageSize = Number(pagination.page_size || current.page_size || investmentRecordsDefaultPageSize(tab));
    investmentRecordsState.pagination[tab] = {
        page,
        page_size: pageSize,
        total: Number(pagination.total || 0),
        total_pages: Math.max(1, Number(pagination.total_pages || 1)),
    };
    investmentRecordsState.filters[tab] = {
        ...current,
        page: String(page),
        page_size: String(pageSize),
    };
}

function renderInvestmentRecordsPagination(tab) {
    const meta = investmentRecordsState.pagination[tab] || {};
    const filters = investmentRecordsState.filters[tab] || {};
    const page = Number(meta.page || filters.page || 1);
    const pageSize = String(meta.page_size || filters.page_size || investmentRecordsDefaultPageSize(tab));
    const total = Number(meta.total || 0);
    const totalPages = Math.max(1, Number(meta.total_pages || 1));
    const pageSizes = [50, 80, 120, 200];
    return `
        <div class="investment-records-pagination">
            <div class="investment-records-pagination-summary">
                <span>共 ${escapeHtml(total)} 条</span>
                <span>第 ${escapeHtml(page)} / ${escapeHtml(totalPages)} 页</span>
            </div>
            <div class="investment-records-pagination-actions">
                <button class="investment-btn compact" onclick="changeInvestmentRecordsPage('${tab}', ${page - 1})" ${page <= 1 ? 'disabled' : ''}><i class="fas fa-chevron-left"></i><span>上一页</span></button>
                <button class="investment-btn compact" onclick="changeInvestmentRecordsPage('${tab}', ${page + 1})" ${page >= totalPages ? 'disabled' : ''}><span>下一页</span><i class="fas fa-chevron-right"></i></button>
                <label class="investment-records-page-size">
                    <span>每页</span>
                    ${investmentDropdown(`investment-records-page-size-${tab}`, pageSizes.map(size => [String(size), String(size)]), pageSize, '', `changeInvestmentRecordsPageSize('${tab}', value)`)}
                </label>
            </div>
        </div>`;
}

function renderInvestmentRecordsPagedList(tab, contentHtml) {
    return `${contentHtml}${renderInvestmentRecordsPagination(tab)}`;
}

async function changeInvestmentRecordsPage(tab, page) {
    const meta = investmentRecordsState.pagination[tab] || {};
    const totalPages = Math.max(1, Number(meta.total_pages || 1));
    const nextPage = Math.max(1, Math.min(Number(page || 1), totalPages));
    investmentRecordsState.filters[tab] = {
        ...(investmentRecordsState.filters[tab] || investmentRecordsDefaultFilters(tab)),
        page: String(nextPage),
    };
    if (tab === 'cache' && currentView === 'invest-content') {
        await loadInvestmentGeneratedContent();
        return;
    }
    await loadInvestmentRecordsTab(tab);
}

async function changeInvestmentRecordsPageSize(tab, pageSize) {
    investmentRecordsState.filters[tab] = {
        ...(investmentRecordsState.filters[tab] || investmentRecordsDefaultFilters(tab)),
        page: '1',
        page_size: String(pageSize || investmentRecordsDefaultPageSize(tab)),
    };
    if (tab === 'cache' && currentView === 'invest-content') {
        await loadInvestmentGeneratedContent();
        return;
    }
    await loadInvestmentRecordsTab(tab);
}

async function loadInvestmentRecordsTab(tab = investmentRecordsState.tab) {
    if (!['requests', 'contents', 'audits'].includes(tab)) tab = 'requests';
    investmentRecordsState.tab = tab;
    const currentPagination = investmentRecordsState.pagination[tab] || {};
    const list = document.getElementById('investment-records-list');
    const pagination = document.getElementById('investment-records-pagination');
    const filters = document.getElementById('investment-records-filters');
    if (filters) filters.innerHTML = renderInvestmentRecordsFilters(tab);
    if (list) investmentLoading(list);
    if (pagination) pagination.innerHTML = '';
    try {
        let html = '';
        if (tab === 'requests') {
            const data = await investmentFetchJson(`/api/investment/records/requests?${investmentRecordsQueryParams('requests').toString()}`);
            investmentRecordsState.data.requests = data.records || [];
            investmentRecordsApplyPagination('requests', data.pagination);
            html = renderInvestmentRequestRecordsTable(investmentRecordsState.data.requests);
            const summary = document.getElementById('investment-records-summary');
            if (summary) summary.innerHTML = renderInvestmentRecordsSummary();
        } else if (tab === 'contents') {
            const data = await investmentFetchJson(`/api/investment/records/contents?${investmentRecordsQueryParams('contents').toString()}`);
            investmentRecordsState.data.contents = data.records || [];
            investmentRecordsApplyPagination('contents', data.pagination);
            html = renderInvestmentContentRecordsTable(investmentRecordsState.data.contents);
        } else {
            const data = await investmentFetchJson(`/api/investment/audits?${investmentRecordsQueryParams('audits').toString()}`);
            investmentRecordsState.data.audits = data.audits || [];
            investmentRecordsApplyPagination('audits', data.pagination);
            html = renderInvestmentOperationAuditsTable(investmentRecordsState.data.audits);
        }
        if (list) list.innerHTML = html;
        if (pagination) pagination.innerHTML = renderInvestmentRecordsPagination(tab);
        closeInvestmentRecordDrawer();
    } catch (error) {
        investmentError(list, error);
    }
}

async function renderInvestmentRecords(options = {}) {
    const element = investmentContentEl('invest-records-content');
    if (!element) return;
    if (options.tab) investmentRecordsState.tab = options.tab;
    if (!['requests', 'contents', 'audits'].includes(investmentRecordsState.tab)) {
        investmentRecordsState.tab = 'requests';
    }
    element.innerHTML = renderInvestmentRecordsShell();
    await loadInvestmentRecordsTab(investmentRecordsState.tab);
}

function renderInvestmentRequestRecordsTable(records) {
    if (!records.length) return '<div class="investment-empty">暂无公众号请求记录</div>';
    const rows = records.map(record => `<tr>
        <td>${investmentCompactText(record.customer_display || record.openid || '', 24)}</td>
        <td>${investmentServiceLabel(record.service_type)}</td>
        <td>${investmentRecordClamp(record.stock_name || record.stock_code || record.normalized_target || record.raw_input || '-', 2, 46)}</td>
        <td><span class="investment-badge ${investmentStatusClass(record.status_warning === '未完成/可能超时' ? 'generating' : record.status)}">${investmentStatusLabel(record.status)}${record.status_warning === '未完成/可能超时' ? ' / 可能超时' : ''}</span></td>
        <td><span class="investment-badge ${investmentDeliveryStatusClass(record.delivery_status)}">${escapeHtml(record.delivery_status || '-')}</span></td>
        <td>${investmentRecordClamp(record.status_warning === '未完成/可能超时' ? record.status_warning : (record.user_prompt || record.delivery_status || '正常'), 1, 54)}</td>
        <td>${record.cache_hit ? '<span class="investment-badge ok">命中</span>' : '<span class="investment-badge">未命中</span>'}</td>
        <td>${escapeHtml(record.elapsed_ms == null ? '-' : `${record.elapsed_ms} ms`)}</td>
        <td>${escapeHtml(investmentFormatBeijingTime(record.created_at))}</td>
        <td class="investment-row-actions">${investmentIconButton('fa-circle-info', '详情', `openInvestmentRecordDrawer('request', '${investmentEncodedRecord(record)}')`)}</td>
    </tr>`).join('');
    return investmentRecordTableShell(`<table class="investment-table investment-records-table">
        <thead><tr><th>客户</th><th>服务</th><th>标的/输入</th><th>生成</th><th>交付</th><th>提示摘要</th><th>缓存</th><th>耗时</th><th>时间</th><th>详情</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function renderInvestmentContentRecordsTable(records) {
    if (!records.length) return '<div class="investment-empty">暂无后台生成记录</div>';
    const rows = records.map(record => {
        if (record.record_type === 'generation') {
            return `<tr>
                <td>${investmentServiceLabel(record.service_type)}</td>
                <td>${investmentRecordClamp(record.generation_id || '-', 1, 18)}</td>
                <td>${escapeHtml(record.operator_name || '-')}</td>
                <td><span class="investment-badge ${investmentStatusClass(record.result || record.status)}">${investmentStatusLabel(record.result || record.status)}</span></td>
                <td><span class="investment-muted-inline">后台生成</span></td>
                <td>${investmentRecordFileSummary(record.outputs || [], '未生成')}</td>
                <td>${investmentRecordClamp(record.error || record.output_text || '正常', 2, 54)}</td>
                <td>${escapeHtml(record.elapsed_ms == null ? '-' : `${record.elapsed_ms} ms`)}</td>
                <td>${escapeHtml(investmentFormatBeijingTime(record.created_at))}</td>
                <td class="investment-row-actions">${investmentIconButton('fa-circle-info', '详情', `openInvestmentRecordDrawer('content', '${investmentEncodedRecord(record)}')`)}</td>
            </tr>`;
        }
        return `<tr>
            <td>${investmentServiceLabel(record.service_type)}</td>
            <td>${escapeHtml(record.effective_date || '-')}</td>
            <td>v${escapeHtml(record.content_version || 1)}</td>
            <td><span class="investment-badge ${investmentStatusClass(record.status)}">${investmentStatusLabel(record.status)}</span></td>
            <td><span class="investment-muted-inline">AI+渲染</span></td>
            <td>${record.output_image ? investmentRecordFileSummary([record.output_image], '未生成') : '<span class="investment-muted-inline">未生成</span>'}</td>
            <td>${investmentRecordClamp(record.status_warning || record.error_message || '正常', 2, 54)}</td>
            <td>${escapeHtml(investmentFormatBeijingTime(record.created_at))}</td>
            <td class="investment-row-actions">
                ${investmentIconButton('fa-circle-info', '详情', `openInvestmentRecordDrawer('content', '${investmentEncodedRecord(record)}')`)}
                ${record.status !== 'generating' ? investmentIconButtonIfCan('content.generate', 'fa-rotate', '生成', `generateInvestmentContent('${record.content_id}', '${escapeHtml(record.service_type || '')}')`) : ''}
                ${record.output_image ? investmentIconButtonIfCan('content.publish', 'fa-circle-check', '设为生效', `effectiveInvestmentContent('${record.content_id}', '${escapeHtml(record.service_type || '')}')`, 'primary') : ''}
            </td>
        </tr>`;
    }).join('');
    return investmentRecordTableShell(`<table class="investment-table investment-records-table">
        <thead><tr><th>服务</th><th>ID/日期</th><th>操作人/版本</th><th>状态</th><th>模式</th><th>输出摘要</th><th>摘要</th><th>耗时</th><th>北京时间</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function renderInvestmentCacheTable(entries) {
    return renderInvestmentDailyGeneratedContent({entries, market_dates: []});
}

function renderInvestmentRecordsCacheTab(cacheData = {}) {
    return renderInvestmentDailyGeneratedContent(cacheData);
}

function renderInvestmentDailyGeneratedContent(cacheData = {}) {
    const values = Array.isArray(cacheData.entries) ? cacheData.entries : [];
    const marketDates = cacheData.market_dates || [];
    const dateRange = investmentNormalizeCacheDateFilters();
    const selectedDate = dateRange.marketDate;
    const keyword = investmentCacheKeyword().trim().toLowerCase();
    const visibleEntries = selectedDate ? values.filter(entry => (entry.market_date || '') === selectedDate) : values;
    const categories = ['technical_analysis', 'rate', 'convertible_bond'];
    const selectedCategory = categories.includes(investmentRecordsState.cacheCategory) ? investmentRecordsState.cacheCategory : '';
    const body = selectedCategory
        ? renderInvestmentGeneratedContentCategoryDetail(selectedCategory, visibleEntries.filter(entry => entry.service_type === selectedCategory))
        : renderInvestmentGeneratedContentHome(categories, visibleEntries);
    const pagination = selectedCategory ? renderInvestmentRecordsPagination('cache') : '';
    return `
        <div class="investment-generated-content">
            <div class="investment-generated-content-toolbar">
                <div class="investment-generated-content-title">
                    <h3>生成内容</h3>
                    <span>${escapeHtml(dateRange.label)}</span>
                </div>
                <div class="investment-generated-content-filters">
                    <label class="investment-field compact investment-generated-period-mode">
                        <span>日期范围</span>
                        ${investmentDropdown('investment-content-period-mode', [['all', '全部'], ['day', '按日'], ['month', '按月'], ['year', '按年']], dateRange.mode || 'all', '', 'investmentChangeCachePeriodMode(value)')}
                    </label>
                    <label id="investment-content-period-date-field" class="investment-field compact ${dateRange.mode === 'day' ? '' : 'hidden'}">
                        <span>日期</span>
                        ${investmentRenderDateControl('investment-records-filter-market_date', selectedDate || investmentTodayDate(), {placeholder: '当前日期', attrs: 'data-investment-records-filter="market_date"'})}
                    </label>
                    <label id="investment-content-period-value-field" class="investment-field compact investment-generated-period-value ${['month', 'year'].includes(dateRange.mode) ? '' : 'hidden'}">
                        ${renderInvestmentGeneratedPeriodValueControl(dateRange.mode, marketDates, values)}
                    </label>
                    <label class="investment-field compact keyword">
                        <span>关键词</span>
                        <input id="investment-content-filter-keyword" type="search" value="${escapeHtml(keyword)}" placeholder="类型/标的/文件" onkeydown="if(event.key === 'Enter') applyInvestmentCacheDate()">
                    </label>
                    ${investmentButton('fa-filter', '查看', 'applyInvestmentCacheDate()')}
                </div>
            </div>
            ${body}
            ${pagination}
        </div>`;
}

function renderInvestmentGeneratedContentHome(categories, entries) {
    return `
        <div class="investment-generated-library">
            <section class="investment-generated-category-strip">
                <div class="investment-generated-date-heading">
                    <strong>内容分类</strong>
                    <span>${entries.length} 条内容</span>
                </div>
                <div class="investment-generated-content-home">${renderInvestmentGeneratedCategoryCards(categories, entries)}</div>
            </section>
        </div>`;
}

function renderInvestmentGeneratedCategoryCards(categories, entriesForScope) {
    return categories.map(serviceType => {
        const entries = entriesForScope.filter(entry => entry.service_type === serviceType);
        const hitCount = entries.reduce((sum, entry) => sum + Number(entry.request_count || entry.hit_count || 0), 0);
        const contentCount = entries.reduce((sum, entry) => sum + Number(entry.request_count || entry.count || 0), 0);
        const latest = entries.map(entry => entry.updated_at).filter(Boolean).sort().pop();
        return `
            <button class="investment-generated-content-entry" onclick="selectInvestmentCacheCategory('${serviceType}')">
                <div class="investment-generated-entry-icon"><i class="fas ${serviceType === 'technical_analysis' ? 'fa-chart-line' : serviceType === 'rate' ? 'fa-percent' : 'fa-file-invoice-dollar'}"></i></div>
                <div class="investment-generated-entry-main">
                    <strong>${investmentServiceLabel(serviceType)}</strong>
                    <span>${contentCount ? `${contentCount} 条内容` : '暂无内容'}</span>
                </div>
                <div class="investment-generated-entry-meta">
                    <span>${hitCount} 次命中</span>
                    <span>${escapeHtml(investmentFormatBeijingTime(latest) || '未更新')}</span>
                </div>
            </button>`;
    }).join('');
}

function investmentGeneratedEntryIsActive(entry) {
    if (!entry) return false;
    if (entry.status === 'invalidated') return false;
    if (entry.source_type === 'content') return ['generated', 'effective'].includes(entry.status);
    return entry.status === 'active';
}

function investmentGeneratedRecordDrawerType(entry) {
    if (entry?.source_type === 'content') return 'content';
    return 'cache';
}

function investmentGeneratedEntryStatus(entry) {
    const status = entry?.status || '';
    const label = entry?.source_type === 'content' ? investmentStatusLabel(status) : status;
    const badgeClass = entry?.source_type === 'content' ? investmentStatusClass(status) : (status === 'active' ? 'ok' : 'fail');
    return `<span class="investment-badge ${badgeClass}">${escapeHtml(label || '-')}</span>`;
}

function investmentGeneratedEntryActions(entry) {
    if ((entry?.source_type === 'cache' || (!entry?.source_type && entry?.cache_key)) && entry.cache_key) {
        return investmentTextButtonIfCan('cache.write', '失效', `invalidateInvestmentCache('${encodeURIComponent(entry.cache_key || '')}')`, 'danger');
    }
    return '<span class="investment-muted-inline">查看详情</span>';
}

function renderInvestmentGeneratedContentCategoryDetail(serviceType, entries) {
    return `
        <div class="investment-generated-content-detail">
            <div class="investment-generated-content-detail-header">
                ${investmentButton('fa-arrow-left', '返回分类', 'backInvestmentCacheCategoryMenu()')}
                <div class="investment-generated-content-detail-title">
                    <h3>${investmentServiceLabel(serviceType)}</h3>
                    <span class="investment-generated-content-detail-count">${entries.length} 条</span>
                </div>
            </div>
            <div class="investment-artifact-browser">
                <aside class="investment-artifact-tree" id="investment-artifact-tree">${renderInvestmentArtifactLazyTree(serviceType)}</aside>
                <section class="investment-artifact-viewer" id="investment-artifact-viewer">${renderInvestmentArtifactViewer()}</section>
            </div>
        </div>`;
}

function renderInvestmentArtifactLazyTree(serviceType) {
    const range = investmentNormalizeCacheDateFilters();
    const root = investmentArtifactRootNode(range);
    if (!root) return '<div class="investment-history-empty investment-generated-history-empty">选择日期范围查看目录</div>';
    return renderInvestmentArtifactFolderNode(root, serviceType, true, 0);
}

function investmentArtifactRootNode(range) {
    if (range.mode === 'year' && /^\d{4}$/.test(investmentCachePeriodValue())) {
        const key = investmentCachePeriodValue();
        return {level: 'year', key, label: key, count: ''};
    }
    if (range.mode === 'month' && /^\d{4}-\d{2}$/.test(investmentCachePeriodValue())) {
        const key = investmentCachePeriodValue();
        return {level: 'month', key, label: key, count: ''};
    }
    if (range.mode === 'day' && range.marketDate) {
        return {level: 'date', key: range.marketDate, label: range.marketDate, count: ''};
    }
    return {level: 'all', key: 'all', label: '全部', count: ''};
}

function investmentArtifactDepthClass(depth) {
    const safeDepth = Math.max(0, Math.min(4, Number(depth) || 0));
    return `investment-artifact-depth-${safeDepth}-btn`;
}

function renderInvestmentArtifactFolderNode(node, serviceType, open = false, depth = 0) {
    const level = node.level || 'year';
    const key = node.key || node.label || '';
    const count = node.count === '' || node.count == null ? '' : `<span class="ml-auto text-[10px] text-slate-400">${escapeHtml(node.count)}</span>`;
    const buttonClass = `${investmentArtifactDepthClass(depth)} investment-artifact-${level === 'package' ? 'package' : level === 'date' ? 'folder' : 'package'}-btn`;
    return `
        <div class="knowledge-tree-group investment-artifact-${escapeHtml(level)} ${open ? 'open' : ''}" data-artifact-level="${escapeHtml(level)}" data-artifact-key="${escapeHtml(key)}" data-artifact-depth="${escapeHtml(depth)}" data-artifact-loaded="0">
            <button class="knowledge-tree-group-btn ${buttonClass}" onclick="toggleInvestmentArtifactNode(this, '${escapeHtml(serviceType)}', '${escapeHtml(level)}', '${escapeHtml(key)}')">
                <i class="fas fa-chevron-right chevron"></i><i class="fas ${level === 'package' ? 'fa-box-archive text-slate-400' : 'fa-folder text-amber-400'} text-[11px]"></i><span>${escapeHtml(node.label || key)}</span>${count}
            </button>
            <div class="knowledge-tree-group-items">${open ? '<div class="investment-muted-inline">加载中...</div>' : ''}</div>
        </div>`;
}

function renderInvestmentArtifactPackageTree(pkg = {}) {
    const groups = {input: [], output: [], intermediate: []};
    (pkg.files || []).forEach(file => {
        const group = file.group || 'intermediate';
        if (!groups[group]) groups[group] = [];
        groups[group].push(file);
    });
    const encodedPackage = investmentEncodedRecord(pkg);
    return `
        <div class="knowledge-tree-group investment-artifact-package">
            <button class="knowledge-tree-group-btn investment-artifact-package-btn" onclick="this.parentElement.classList.toggle('open')">
                <i class="fas fa-chevron-right chevron"></i><i class="fas fa-box-archive text-[11px] text-slate-400"></i><span>${escapeHtml(pkg.display_name || pkg.package_id || '产物包')}</span><span class="ml-auto text-[10px] text-slate-400">${escapeHtml(pkg.request_count || 0)}</span>
            </button>
            <div class="knowledge-tree-group-items">
                ${['input', 'output', 'intermediate'].map(group => renderInvestmentArtifactGroupTree(group, groups[group] || [], encodedPackage)).join('')}
            </div>
        </div>`;
}

function renderInvestmentArtifactGroupTree(group, files, encodedPackage, depth = 3) {
    if (!files.length) return '';
    const label = group === 'input' ? 'input' : group === 'output' ? 'output' : 'intermediate';
    return `
        <div class="knowledge-tree-group investment-artifact-folder">
            <button class="knowledge-tree-group-btn investment-artifact-folder-btn ${investmentArtifactDepthClass(depth)}" onclick="this.parentElement.classList.toggle('open')">
                <i class="fas fa-chevron-right chevron"></i><i class="fas fa-folder text-amber-400 text-[11px]"></i><span>${label}</span><span class="ml-auto text-[10px] text-slate-400">${files.length}</span>
            </button>
            <div class="knowledge-tree-group-items">
                ${files.map(file => {
                    const encodedFile = investmentEncodedRecord(file);
                    const fileName = file.file_name || (file.kind === 'virtual_text' ? 'raw_input.txt' : '') || file.virtual_path || 'artifact';
                    return `<button class="knowledge-tree-file investment-artifact-file-btn ${investmentArtifactDepthClass(depth + 1)}" onclick="openInvestmentArtifactFile('${encodedPackage}', '${encodedFile}', this)">
                        <i class="fas ${investmentArtifactFileIcon(file)} text-[10px] text-slate-400"></i><span class="truncate">${escapeHtml(fileName)}</span>
                    </button>`;
                }).join('')}
            </div>
        </div>`;
}

async function loadInvestmentArtifactRootNodes(serviceType) {
    const tree = document.getElementById('investment-artifact-tree');
    if (!tree) return;
    const root = tree.querySelector('.knowledge-tree-group');
    if (!root) return;
    const button = root.querySelector('.knowledge-tree-group-btn');
    if (button) await toggleInvestmentArtifactNode(button, serviceType, root.dataset.artifactLevel || 'all', root.dataset.artifactKey || 'all', true);
}

function investmentArtifactFolderQuery(serviceType, level, key) {
    const query = new URLSearchParams();
    query.set('service_type', serviceType);
    query.set('page_size', '100');
    if (level === 'all') {
        query.set('level', 'year');
    } else if (level === 'year') {
        query.set('level', 'month');
        query.set('year', key);
    } else if (level === 'month') {
        query.set('level', 'date');
        query.set('month', key);
    } else if (level === 'date') {
        query.set('level', 'package');
        query.set('date', key);
    }
    const keyword = investmentCacheKeyword().trim();
    if (keyword) query.set('keyword', keyword);
    return query;
}

function investmentArtifactNextLevel(level) {
    if (level === 'all') return 'year';
    if (level === 'year') return 'month';
    if (level === 'month') return 'date';
    if (level === 'date') return 'package';
    return '';
}

async function toggleInvestmentArtifactNode(button, serviceType, level, key, forceLoad = false) {
    const group = button.closest('.knowledge-tree-group');
    if (!group) return;
    const items = group.querySelector(':scope > .knowledge-tree-group-items');
    if (!items) return;
    group.classList.toggle('open', forceLoad || !group.classList.contains('open'));
    if (!forceLoad && group.dataset.artifactLoaded === '1') return;
    if (level === 'package') {
        await loadInvestmentArtifactPackage(group, key);
        return;
    }
    items.innerHTML = '<div class="investment-muted-inline">加载中...</div>';
    try {
        const query = investmentArtifactFolderQuery(serviceType, level, key);
        const data = await investmentFetchJson(`/api/investment/artifact-folders?${query.toString()}`);
        const nextLevel = investmentArtifactNextLevel(level);
        const depth = Number(group.dataset.artifactDepth || 0);
        const nodes = data.nodes || [];
        items.innerHTML = nodes.length
            ? nodes.map(node => renderInvestmentArtifactFolderNode({...node, level: node.level || nextLevel}, serviceType, false, depth + 1)).join('')
            : '<div class="investment-history-empty investment-generated-history-empty">暂无历史内容</div>';
        group.dataset.artifactLoaded = '1';
    } catch (error) {
        items.innerHTML = `<div class="investment-history-empty investment-generated-history-empty">${escapeHtml(error.message || error)}</div>`;
    }
}

async function loadInvestmentArtifactPackage(group, packageId) {
    const items = group.querySelector(':scope > .knowledge-tree-group-items');
    if (!items) return;
    items.innerHTML = '<div class="investment-muted-inline">加载中...</div>';
    try {
        const data = await investmentFetchJson(`/api/investment/artifacts?package_id=${encodeURIComponent(packageId)}&page_size=1`);
        const pkg = (data.packages || [])[0];
        if (!pkg) {
            items.innerHTML = '<div class="investment-history-empty investment-generated-history-empty">暂无文件</div>';
            return;
        }
        const encodedPackage = investmentEncodedRecord(pkg);
        const groups = {input: [], output: [], intermediate: []};
        (pkg.files || []).forEach(file => {
            const fileGroup = file.group || 'intermediate';
            if (!groups[fileGroup]) groups[fileGroup] = [];
            groups[fileGroup].push(file);
        });
        const depth = Number(group.dataset.artifactDepth || 0);
        items.innerHTML = ['input', 'output', 'intermediate'].map(folder => renderInvestmentArtifactGroupTree(folder, groups[folder] || [], encodedPackage, depth + 1)).join('');
        group.dataset.artifactLoaded = '1';
    } catch (error) {
        items.innerHTML = `<div class="investment-history-empty investment-generated-history-empty">${escapeHtml(error.message || error)}</div>`;
    }
}

function investmentArtifactFileIcon(file = {}) {
    const fileType = file.file_type || '';
    if (fileType === 'image') return 'fa-image';
    if (fileType === 'markdown' || fileType === 'text') return 'fa-file-lines';
    return 'fa-file';
}

function openInvestmentArtifactFile(encodedPackage, encodedFile, button = null) {
    const pkg = JSON.parse(decodeURIComponent(encodedPackage));
    const file = JSON.parse(decodeURIComponent(encodedFile));
    document.querySelectorAll('.investment-artifact-tree .knowledge-tree-file').forEach(el => el.classList.remove('active'));
    if (button) button.classList.add('active');
    const viewer = document.getElementById('investment-artifact-viewer');
    if (viewer) viewer.innerHTML = renderInvestmentArtifactViewer(pkg, file);
}

function renderInvestmentArtifactViewer(pkg = null, file = null) {
    if (!pkg || !file) {
        return `<div class="investment-artifact-viewer-empty"><i class="fas fa-file-lines"></i><span>选择文件查看内容</span></div>`;
    }
    const title = file.file_name || file.virtual_path || 'artifact';
    const meta = `
        <div class="investment-artifact-viewer-meta">
            <span>${escapeHtml(pkg.display_name || '')}</span>
            <span>${escapeHtml(pkg.market_date || '')}</span>
            <span>${escapeHtml(file.virtual_path || '')}</span>
        </div>`;
    const actions = file.file_url
        ? `<a class="investment-btn secondary" href="${investmentFileUrl(file)}" target="_blank" rel="noopener noreferrer" download><i class="fas fa-download"></i><span>下载</span></a>`
        : '';
    let body = '';
    if (file.kind === 'virtual_text') {
        body = `<pre class="investment-artifact-text">${escapeHtml(file.content || '')}</pre>`;
    } else if (file.file_type === 'image') {
        body = `<div class="investment-artifact-image-wrap"><img src="${investmentFileUrl(file)}" alt="${escapeHtml(title)}"></div>`;
    } else if (file.file_type === 'markdown') {
        body = `<div class="investment-artifact-download-card"><i class="fas fa-file-lines"></i><div><strong>${escapeHtml(title)}</strong><span>Markdown 报告可下载查看</span></div></div>`;
    } else {
        body = `<div class="investment-artifact-download-card"><i class="fas fa-file"></i><div><strong>${escapeHtml(title)}</strong><span>文件可下载查看</span></div></div>`;
    }
    return `
        <div class="investment-artifact-viewer-header">
            <div><h4>${escapeHtml(title)}</h4>${meta}</div>
            <div class="investment-row-actions">${actions}</div>
        </div>
        <div class="investment-artifact-viewer-body">${body}</div>`;
}

function renderInvestmentCacheCategory(serviceType, entries) {
    return `
        <div class="investment-cache-category">
            ${entries.length ? renderInvestmentCacheCompactRows(entries) : '<div class="investment-history-empty investment-generated-history-empty">暂无历史内容</div>'}
        </div>`;
}

function renderInvestmentCacheCompactRows(entries) {
    const header = `
        <div class="investment-generated-content-header">
            <span>标的</span>
            <span>状态</span>
            <span>命中</span>
            <span>更新时间</span>
            <span>产物</span>
            <span>操作</span>
        </div>`;
    const rows = entries.map(entry => {
        const drawerType = investmentGeneratedRecordDrawerType(entry);
        return `
        <div class="investment-generated-content-row">
            <button class="investment-generated-content-row-main" onclick="openInvestmentRecordDrawer('${drawerType}', '${investmentEncodedRecord(entry)}')" title="查看详情">
                <span class="investment-generated-target">${investmentRecordClamp(entry.normalized_target || '全市场/当日内容', 1, 34)}</span>
                <span>${investmentGeneratedEntryStatus(entry)}</span>
                <span><b>${escapeHtml(entry.hit_count ?? 0)}</b> 次命中</span>
                <span>${escapeHtml(investmentFormatBeijingTime(entry.updated_at) || '-')}</span>
                <span>${investmentGeneratedOutputState(entry)}</span>
            </button>
            <div class="investment-row-actions">${investmentGeneratedEntryActions(entry)}</div>
        </div>`;
    }).join('');
    return `<div class="investment-generated-content-entries">${header}${rows}</div>`;
}

function investmentGeneratedOutputState(entry) {
    const files = Array.isArray(entry.output_files) ? entry.output_files.filter(Boolean) : [];
    if (!files.length) return '<span class="investment-muted-inline">无输出</span>';
    return files.length > 1 ? `${files.length} 个输出` : '已生成';
}

function renderInvestmentCacheEntryRows(entries) {
    return renderInvestmentCacheCompactRows(entries);
}

async function selectInvestmentCacheDate(date) {
    investmentRecordsState.filters.cache.market_date = date;
    investmentRecordsState.filters.cache.page = '1';
    investmentRecordsState.cacheCategory = '';
    await loadInvestmentGeneratedContent();
}

async function applyInvestmentCacheDate() {
    const range = investmentNormalizeCacheDateFilters();
    investmentRecordsState.filters.cache.market_date = range.marketDate || '';
    investmentRecordsState.filters.cache.period_mode = investmentCachePeriodMode();
    investmentRecordsState.filters.cache.period_value = investmentCachePeriodValue();
    investmentRecordsState.filters.cache.start_date = range.startDate;
    investmentRecordsState.filters.cache.end_date = range.endDate;
    investmentRecordsState.filters.cache.keyword = document.getElementById('investment-content-filter-keyword')?.value || '';
    investmentRecordsState.filters.cache.page = '1';
    await loadInvestmentGeneratedContent();
}

async function selectInvestmentCacheCategory(serviceType) {
    investmentRecordsState.cacheCategory = serviceType;
    investmentRecordsState.filters.cache.service_type = serviceType;
    investmentRecordsState.filters.cache.page = '1';
    scheduleInvestmentCacheFilterRefresh();
}

async function backInvestmentCacheCategoryMenu() {
    investmentRecordsState.cacheCategory = '';
    delete investmentRecordsState.filters.cache.service_type;
    investmentRecordsState.filters.cache.page = '1';
    await loadInvestmentGeneratedContent();
}

async function clearInvestmentGeneratedContentCacheByDate() {
    const today = investmentCacheMarketDate() || investmentTodayDate();
    const marketDate = prompt('清理生成内容日期', today);
    if (!marketDate) return;
    try {
        await investmentFetchJson('/api/investment/cache/clear', {
            method: 'POST',
            body: JSON.stringify({market_date: marketDate}),
        });
        await loadInvestmentGeneratedContent();
    } catch (error) {
        showInvestmentToast(`生成内容清理失败：${String(error.message || error)}`, 'error');
    }
}

function renderInvestmentOperationAuditsTable(audits) {
    if (!audits.length) return '<div class="investment-empty">暂无操作流水</div>';
    const rows = audits.map(audit => {
        const detailText = JSON.stringify(audit.detail || {}, null, 2);
        return `<tr>
            <td>${escapeHtml(audit.action || '-')}</td>
            <td>${investmentCompactText(`${audit.target_type || '-'}${audit.target_id ? ' / ' + audit.target_id : ''}`, 42)}</td>
            <td>${escapeHtml(audit.operator || '-')}</td>
            <td>${investmentRecordClamp(detailText, 2, 58)}</td>
            <td>${escapeHtml(investmentFormatBeijingTime(audit.created_at) || '-')}</td>
            <td class="investment-row-actions">${investmentIconButton('fa-circle-info', '详情', `openInvestmentRecordDrawer('audit', '${investmentEncodedRecord(audit)}')`)}</td>
        </tr>`;
    }).join('');
    return investmentRecordTableShell(`<table class="investment-table investment-records-table">
        <thead><tr><th>动作</th><th>对象</th><th>操作人</th><th>摘要</th><th>北京时间</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function investmentDrawerSection(title, body) {
    return `<section class="investment-records-drawer-section"><h4>${escapeHtml(title)}</h4>${body}</section>`;
}

function investmentDrawerFacts(items) {
    return `<div class="investment-detail-grid">${items.map(([label, value]) => `
        <div><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`).join('')}</div>`;
}

function investmentDrawerPre(label, value) {
    return investmentDrawerSection(label, `<pre>${escapeHtml(value || '无')}</pre>`);
}

function openInvestmentRecordDrawer(type, encodedOrRecord) {
    const record = typeof encodedOrRecord === 'string' ? JSON.parse(decodeURIComponent(encodedOrRecord)) : (encodedOrRecord || {});
    investmentRecordsState.selected = {type, record};
    const drawer = document.getElementById('investment-records-drawer');
    if (!drawer) {
        if (type === 'audit') showInvestmentAuditDetail(investmentEncodedRecord(record));
        else showInvestmentModal('记录详情', renderInvestmentRecordDrawerBody(type, record));
        return;
    }
    drawer.innerHTML = renderInvestmentRecordDrawerBody(type, record);
    drawer.classList.add('active');
}

function closeInvestmentRecordDrawer() {
    const drawer = document.getElementById('investment-records-drawer');
    if (!drawer) return;
    drawer.classList.remove('active');
    drawer.innerHTML = `
        <div class="investment-records-drawer-empty">
            <i class="fas fa-circle-info"></i>
            <span>选择记录查看详情</span>
        </div>`;
}

function renderInvestmentRecordDrawerBody(type, record) {
    const titleMap = {request: '公众号请求详情', content: '后台生成详情', cache: '生成内容详情', audit: '操作流水详情'};
    return `
        <div class="investment-records-drawer-header">
            <div>
                <h3>${escapeHtml(titleMap[type] || '记录详情')}</h3>
                <span>${escapeHtml(investmentFormatBeijingTime(record.created_at || record.updated_at) || '-')}</span>
            </div>
            <button class="investment-btn investment-icon-btn" onclick="closeInvestmentRecordDrawer()" title="关闭"><i class="fas fa-xmark"></i></button>
        </div>
        <div class="investment-records-drawer-body">
            ${type === 'request' ? renderInvestmentRequestDrawer(record) : ''}
            ${type === 'content' ? renderInvestmentContentDrawer(record) : ''}
            ${type === 'cache' ? renderInvestmentCacheDrawer(record) : ''}
            ${type === 'audit' ? renderInvestmentAuditDrawer(record) : ''}
        </div>`;
}

function renderInvestmentRequestDrawer(record) {
    return `
        ${investmentDrawerSection('基础信息', investmentDrawerFacts([
            ['请求 ID', escapeHtml(record.request_id || '-')],
            ['客户', escapeHtml(record.customer_display || record.openid || '-')],
            ['OpenID', escapeHtml(record.openid || '-')],
            ['手机号', escapeHtml(record.customer_mobile || '-')],
            ['服务', investmentServiceLabel(record.service_type)],
            ['生成状态', investmentStatusLabel(record.status)],
            ['交付状态', `<span class="investment-badge ${investmentDeliveryStatusClass(record.delivery_status)}">${escapeHtml(record.delivery_status || '-')}</span>`],
            ['耗时', escapeHtml(record.elapsed_ms == null ? '-' : `${record.elapsed_ms} ms`)],
            ['北京时间', escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')],
        ]))}
        ${investmentDrawerPre('原始输入', record.raw_input || '')}
        ${investmentDrawerPre('用户提示', record.user_prompt || '')}
        ${investmentDrawerPre('错误/警告详情', record.status_warning || record.delivery_detail || record.error_message || '')}
        ${investmentDrawerSection('审计字段', investmentDrawerFacts([
            ['规范标的', escapeHtml(record.normalized_target || '-')],
            ['证券代码', escapeHtml(record.stock_code || '-')],
            ['证券名称', escapeHtml(record.stock_name || '-')],
            ['市场日期', escapeHtml(record.market_date || '-')],
            ['缓存 Key', escapeHtml(record.cache_key || '-')],
            ['程序版本', escapeHtml(record.program_version || '-')],
            ['TA 版本', escapeHtml(record.ta_version || '-')],
            ['渲染版本', escapeHtml(record.renderer_version || '-')],
            ['模板版本', escapeHtml(record.template_version || '-')],
        ]))}
        ${investmentDrawerSection('输出文件', `<div class="investment-detail-links">${investmentFileLinks(record.output_files || [])}</div>`)}
        ${renderInvestmentRequestEventTimeline(record.events || [])}
    `;
}

function renderInvestmentRequestEventTimeline(events) {
    if (!events.length) return investmentDrawerSection('请求流程', '<span class="investment-muted-inline">暂无流程事件</span>');
    const rows = events.map(event => `
        <div class="investment-audit-item">
            <div>
                <strong>${escapeHtml(event.event_type || '-')}</strong>
                <span>${escapeHtml(event.message_type || event.channel || '-')}</span>
            </div>
            <div>
                <span>${escapeHtml(event.result || '-')}</span>
                <span>${escapeHtml(investmentFormatBeijingTime(event.created_at) || '-')}</span>
            </div>
            ${event.content || event.file_path || event.error ? `<pre>${escapeHtml([event.content, event.file_path, event.error].filter(Boolean).join('\n'))}</pre>` : ''}
        </div>`).join('');
    return investmentDrawerSection('请求流程', `<div class="investment-audit-list">${rows}</div>`);
}

function renderInvestmentContentDrawer(record) {
    if (record.record_type === 'generation') {
        return `
            ${investmentDrawerSection('基础信息', investmentDrawerFacts([
                ['生成 ID', escapeHtml(record.generation_id || '-')],
                ['内容 ID', escapeHtml(record.content_id || '-')],
                ['服务', investmentServiceLabel(record.service_type)],
                ['结果', investmentStatusLabel(record.result || record.status)],
                ['操作人', escapeHtml(record.operator_name || '-')],
                ['角色', escapeHtml(record.operator_role || '-')],
                ['耗时', escapeHtml(record.elapsed_ms == null ? '-' : `${record.elapsed_ms} ms`)],
                ['创建时间', escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')],
                ['更新时间', escapeHtml(investmentFormatBeijingTime(record.updated_at) || '-')],
            ]))}
            ${investmentDrawerSection('输入文件', `<div class="investment-detail-links">${investmentFileLinks(record.sources || [])}</div>`)}
            ${investmentDrawerSection('输出文件', `<div class="investment-detail-links">${investmentFileLinks(record.outputs || [])}</div>`)}
            ${investmentDrawerPre('输入文本', record.input_text || '')}
            ${investmentDrawerPre('生成文本', record.output_text || '')}
            ${investmentDrawerPre('错误详情', record.error || '')}
        `;
    }
    return `
        ${investmentDrawerSection('基础信息', investmentDrawerFacts([
            ['内容 ID', escapeHtml(record.content_id || '-')],
            ['服务', investmentServiceLabel(record.service_type)],
            ['状态', investmentStatusLabel(record.status)],
            ['操作人', escapeHtml(record.operator || '-')],
            ['生效日期', escapeHtml(record.effective_date || '-')],
            ['版本', `v${escapeHtml(record.content_version || 1)}`],
            ['模式', 'AI+渲染'],
            ['创建时间', escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')],
        ]))}
        ${investmentDrawerSection('输入图片', `<div class="investment-drawer-file-grid">${renderInvestmentSourcePreviews(investmentContentSourceFiles(record))}</div>`)}
        ${investmentDrawerSection('输出图片', investmentContentOutputImage(record) ? renderInvestmentFilePreview(investmentContentOutputImage(record), '输出图片') : '<span class="investment-muted-inline">未生成</span>')}
        ${investmentDrawerPre('错误/警告', record.status_warning || record.error_message || '')}
        ${investmentDrawerPre('资料文本', record.source_text || '')}
        ${investmentDrawerPre('生成文本', record.generated_text || '')}
    `;
}

function renderInvestmentCacheDrawer(record) {
    return `
        ${investmentDrawerSection('基础信息', investmentDrawerFacts([
            ['服务', investmentServiceLabel(record.service_type)],
            ['标的', escapeHtml(record.normalized_target || '全市场/当日内容')],
            ['状态', escapeHtml(record.status || '-')],
            ['命中次数', escapeHtml(record.hit_count ?? 0)],
            ['市场日期', escapeHtml(record.market_date || '-')],
            ['更新时间', escapeHtml(investmentFormatBeijingTime(record.updated_at) || '-')],
        ]))}
    `;
}

function renderInvestmentAuditDrawer(record) {
    return `
        ${investmentDrawerSection('基础信息', investmentDrawerFacts([
            ['动作', escapeHtml(record.action || '-')],
            ['对象类型', escapeHtml(record.target_type || '-')],
            ['对象 ID', escapeHtml(record.target_id || '-')],
            ['操作人', escapeHtml(record.operator || '-')],
            ['北京时间', escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')],
        ]))}
        ${investmentDrawerSection('详情', `<pre>${escapeHtml(JSON.stringify(record.detail || {}, null, 2))}</pre>`)}
        ${investmentDrawerSection('修改前', `<pre>${escapeHtml(JSON.stringify(record.before_state || {}, null, 2))}</pre>`)}
        ${investmentDrawerSection('修改后', `<pre>${escapeHtml(JSON.stringify(record.after_state || {}, null, 2))}</pre>`)}
    `;
}

function showInvestmentAuditDetail(encoded) {
    const audit = JSON.parse(decodeURIComponent(encoded));
    showInvestmentModal('操作流水详情', renderInvestmentAuditDrawer(audit));
}

function hideInvestmentDetail(button) {
    if (!button) {
        hideInvestmentModal();
        return;
    }
    const panel = button.closest('[data-investment-detail-panel]');
    if (panel) {
        panel.classList.add('hidden');
        panel.innerHTML = '';
    }
}

async function renderInvestmentConfig() {
    const element = investmentContentEl('invest-config-content');
    investmentLoading(element);
    try {
        const canReadConfig = investmentCan('config.read');
        const canReadStocks = investmentCan('stocks.read');
        const [data, stockData] = await Promise.all([
            canReadConfig ? investmentFetchJson('/api/investment/config') : Promise.resolve({configs: {}}),
            canReadStocks ? investmentFetchJson('/api/investment/stocks?limit=5') : Promise.resolve({stats: {}}),
        ]);
        element.innerHTML = renderInvestmentConfigShell(data, stockData);
    } catch (error) {
        investmentError(element, error);
    }
}

function investmentConfigTabDefinitions(canReadConfig, canReadStocks) {
    return [
        {key: 'stock-data', label: '股票数据', icon: 'fa-chart-line', visible: canReadConfig || canReadStocks},
        {key: 'reply-texts', label: '公众号回复词', icon: 'fa-comments', visible: canReadConfig},
        {key: 'generation', label: '业务生成配置', icon: 'fa-wand-magic-sparkles', visible: canReadConfig},
        {key: 'web-chat', label: '后台 Web 对话', icon: 'fa-message', visible: canReadConfig},
    ].filter(tab => tab.visible);
}

function renderInvestmentConfigShell(data = {}, stockData = {}) {
    const canReadConfig = investmentCan('config.read');
    const canReadStocks = investmentCan('stocks.read');
    const configs = data.configs || {};
    const tabs = investmentConfigTabDefinitions(canReadConfig, canReadStocks);
    if (!tabs.some(tab => tab.key === currentInvestmentConfigPanel)) {
        currentInvestmentConfigPanel = tabs[0]?.key || 'stock-data';
    }
    const panelHtml = renderInvestmentConfigPanel(currentInvestmentConfigPanel, data, stockData, configs, canReadConfig, canReadStocks);
    return `
        <div class="investment-config-page investment-settings-page">
            <div class="investment-config-nav">
                ${tabs.map(tab => `
                    <button class="investment-config-tab ${currentInvestmentConfigPanel === tab.key ? 'active' : ''}" onclick="switchInvestmentConfigPanel('${escapeHtml(tab.key)}')">
                        <i class="fas ${escapeHtml(tab.icon)}"></i><span>${escapeHtml(tab.label)}</span>
                    </button>`).join('')}
            </div>
            <div id="invest-config-save-result" class="investment-muted"></div>
            <div id="investment-config-panel-content">${panelHtml}</div>
        </div>`;
}

function renderInvestmentConfigPanel(panel, data, stockData, configs, canReadConfig, canReadStocks) {
    if (panel === 'reply-texts') {
        return canReadConfig ? renderInvestmentConfigReplyTextsPanel(data, configs) : '<div class="investment-empty">暂无配置权限</div>';
    }
    if (panel === 'generation') {
        return canReadConfig ? renderInvestmentConfigGenerationPanel(configs) : '<div class="investment-empty">暂无配置权限</div>';
    }
    if (panel === 'web-chat') {
        return canReadConfig ? renderInvestmentConfigWebChatPanel(configs) : '<div class="investment-empty">暂无配置权限</div>';
    }
    return renderInvestmentConfigStockDataPanel(configs, stockData, canReadConfig, canReadStocks);
}

function renderInvestmentConfigStockDataPanel(configs, stockData, canReadConfig, canReadStocks) {
    return `
        <div class="investment-config-grid investment-config-panel investment-settings-panel investment-stock-data-panel">
            ${investmentStockTools(stockData.stats || {}, configs, canReadConfig, canReadStocks)}
        </div>`;
}

function renderInvestmentConfigReplyTextsPanel(data, configs) {
    return `
        <div class="investment-config-grid investment-config-panel investment-settings-panel">
            ${renderInvestmentReplyConfigGroups(data.reply_texts || {}, configs)}
        </div>`;
}

function renderInvestmentConfigGenerationPanel(configs) {
    return `
        <div class="investment-config-grid investment-config-panel investment-settings-panel">
            ${renderInvestmentConfigGroupByTitle('技术分析参数', configs, {sectionClass: 'investment-config-section'})}
            ${renderInvestmentConfigGroupByTitle('图片生成模板', configs, {sectionClass: 'investment-config-section'})}
            ${renderInvestmentConfigGroupByTitle('存储与提示词', configs, {sectionClass: 'investment-config-section'})}
        </div>`;
}

function renderInvestmentConfigWebChatPanel(configs) {
    return `
        <div class="investment-config-grid investment-config-panel investment-settings-panel">
            ${renderInvestmentConfigGroupByTitle('后台Web对话', configs, {sectionClass: 'investment-config-section investment-workbench-full'})}
        </div>`;
}

function switchInvestmentConfigPanel(panel) {
    currentInvestmentConfigPanel = ['stock-data', 'reply-texts', 'generation', 'web-chat'].includes(panel) ? panel : 'stock-data';
    renderInvestmentConfig();
}

async function renderInvestmentSkills() {
    const element = investmentContentEl('invest-skills-content');
    if (!element) return;
    const manager = renderInvestmentSkillManager;
    const loader = loadInvestmentSkillVersions;
    element.innerHTML = `
        <div class="investment-workbench">
            ${manager()}
        </div>`;
    await loader();
}

function renderInvestmentSkillManager() {
    return `
        <section class="investment-panel investment-workbench-full investment-skill-manager">
            <div class="investment-panel-heading">
                <div>
                    <div class="investment-panel-title"><i class="fas fa-code-branch"></i><span>skill配置</span></div>
                    <div class="investment-subtitle">当前仅启用 technical-analysis 和 signal-card-renderer 两个投研组件，可上传版本、切换版本或删除上传版本。</div>
                </div>
                <div class="investment-panel-actions">
                    ${investmentButton('fa-arrows-rotate', '刷新版本', 'loadInvestmentSkillVersions()')}
                </div>
            </div>
            <div id="invest-skill-result" class="investment-muted"></div>
            <div id="invest-skill-versions" class="investment-skill-version-list">
                <div class="investment-empty"><i class="fas fa-spinner fa-spin"></i><span>加载版本中...</span></div>
            </div>
        </section>`;
}

async function loadInvestmentSkillVersions() {
    const target = document.getElementById('invest-skill-versions');
    if (!target) return;
    target.innerHTML = '<div class="investment-empty"><i class="fas fa-spinner fa-spin"></i><span>加载版本中...</span></div>';
    try {
        const data = await investmentFetchJson('/api/investment/skills/versions');
        currentInvestmentSkills = data.skills || [];
        target.innerHTML = renderInvestmentSkillConfigTable(data.skills || []);
    } catch (error) {
        target.innerHTML = `<div class="investment-alert error">${escapeHtml(String(error.message || error))}</div>`;
    }
}

function renderInvestmentSkillConfigTable(skills = []) {
    if (!skills.length) return '<div class="investment-empty">暂无投研组件</div>';
    const rows = skills.map(item => renderInvestmentSkillConfigRow(item.skill || {}, item.versions || [])).join('');
    return investmentTableWrap(`<table class="investment-table investment-skill-config-table">
        <thead><tr><th>Skill 名字</th><th>状态</th><th>版本</th><th>来源</th><th>文件</th><th>上传时间</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
    </table>`);
}

function renderInvestmentSkillConfigRow(skill, versions = []) {
    const skillKey = skill.skill_key || '';
    const active = versions.find(version => version.active) || versions[0] || {};
    const source = active.source === 'builtin' ? '内置' : '上传';
    const versionOptions = versions.map(version => [
        version.version_id || '',
        `${version.version_id || ''} / ${version.source === 'builtin' ? '内置' : '上传'}`,
    ]);
    return `<tr data-skill-key="${escapeHtml(skillKey)}">
        <td>
            <strong>${escapeHtml(skill.label || skillKey)}</strong>
            <div class="investment-muted">${escapeHtml(skillKey)}</div>
        </td>
        <td><span class="investment-badge ${active.active ? 'ok' : 'fail'}">${active.active ? '生效中' : '未生效'}</span></td>
        <td>
            ${investmentDropdown(`invest-skill-version-${escapeHtml(skillKey)}`, versionOptions, active.version_id || '', '', '')}
        </td>
        <td>${escapeHtml(source)}</td>
        <td>${investmentCompactText(active.original_filename || '', 34)}</td>
        <td>${escapeHtml(investmentFormatBeijingTime(active.uploaded_at) || '-')}</td>
        <td class="investment-row-actions investment-skill-config-actions">
            ${investmentIconButtonIfCan('skills.write', 'fa-pen', '编辑', `openInvestmentSkillDialog('${escapeHtml(skillKey)}')`, 'primary')}
        </td>
    </tr>`;
}

function investmentSkillDialogItem(label, body) {
    return `<div class="investment-detail-block"><span>${escapeHtml(label)}</span>${body}</div>`;
}

function renderInvestmentSkillDialogBody(skill, versions = []) {
    const skillKey = skill.skill_key || currentInvestmentSkillDialogKey;
    const active = versions.find(version => version.active) || versions[0] || {};
    const versionOptions = versions.map(version => [
        version.version_id || '',
        `${version.version_id || ''} / ${version.source === 'builtin' ? '内置' : '上传'}`,
    ]);
    return `
        ${investmentSkillDialogItem('Skill', `<strong>${escapeHtml(skill.label || skillKey)}</strong><div class="investment-muted">${escapeHtml(skillKey)}</div>`)}
        ${investmentSkillDialogItem('版本', investmentDropdown('invest-skill-dialog-version', versionOptions, active.version_id || '', '', ''))}
        ${investmentSkillDialogItem('上传', `<input id="invest-skill-dialog-file" type="file" accept=".py,.zip">`)}
        <div class="investment-actions investment-modal-actions">
            ${investmentButtonIfCan('skills.write', 'fa-floppy-disk', '保存', `saveInvestmentSkillDialog('${escapeHtml(skillKey)}')`, 'primary')}
        </div>`;
}

function openInvestmentSkillDialog(skillKey) {
    currentInvestmentSkillDialogKey = skillKey;
    const item = currentInvestmentSkills.find(row => (row.skill || {}).skill_key === skillKey) || {skill: {skill_key: skillKey}, versions: []};
    showInvestmentModal('编辑投资Skill', renderInvestmentSkillDialogBody(item.skill || {}, item.versions || []));
}

async function saveInvestmentSkillDialog(skillKey) {
    await saveInvestmentSkillSettings(skillKey);
    const file = document.getElementById('invest-skill-dialog-file');
    if (file?.files?.length) {
        await uploadInvestmentSkill(skillKey, file);
    }
    const selectedVersion = document.getElementById('invest-skill-dialog-version')?.value || '';
    if (selectedVersion) {
        await activateInvestmentSkillVersion(skillKey, selectedVersion);
    }
    hideInvestmentModal();
}

async function saveInvestmentSkillSettings(skillKey) {
    await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/settings`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({}),
    });
}

function investmentSkillVersionActivateUrl(skillKey, versionId) {
    return `/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/activate`;
}

function selectedInvestmentSkillVersion(skillKey) {
    const select = document.getElementById(`invest-skill-version-${skillKey}`);
    return select ? select.value : '';
}

async function uploadInvestmentSkill(skillKey, fileInput = null) {
    const input = fileInput || document.getElementById(`invest-skill-file-${skillKey}`);
    const result = document.getElementById('invest-skill-result');
    if (!input || !input.files.length) {
        if (result) result.textContent = '请选择 .py 或 .zip 文件';
        return;
    }
    const form = new FormData();
    form.append('file', input.files[0]);
    if (result) result.textContent = '上传中...';
    try {
        await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/upload`, {method: 'POST', body: form});
        input.value = '';
        if (result) result.textContent = 'Skill 已上传并设为生效';
        showInvestmentToast('Skill 已上传并生效');
        await loadInvestmentSkillVersions();
    } catch (error) {
        if (result) result.textContent = String(error.message || error);
        showInvestmentToast('Skill 上传失败', 'error');
    }
}

async function uploadInvestmentSkillPackage() {
    const input = document.getElementById('invest-skill-package-file');
    if (!input || !input.files.length) return;
    const form = new FormData();
    form.append('file', input.files[0]);
    await investmentFetchJson('/api/investment/skills/packages/upload', {method: 'POST', body: form});
    await loadInvestmentSkillVersions();
}

async function activateInvestmentSkillVersion(skillKey, selectedVersion) {
    if (!selectedVersion) return;
    try {
        await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(selectedVersion)}/activate`, {
            method: 'POST',
        });
        showInvestmentToast('Skill 版本已生效');
        await loadInvestmentSkillVersions();
    } catch (error) {
        showInvestmentToast(`切换版本失败：${String(error.message || error)}`, 'error');
    }
}

async function deleteInvestmentSkillVersion(skillKey, versionId) {
    if (!versionId) return;
    if (versionId === 'builtin-default') {
        showInvestmentToast('内置版本不能删除', 'error');
        return;
    }
    try {
        await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/versions/${encodeURIComponent(versionId)}/delete`, {
            method: 'POST',
        });
        showInvestmentToast('Skill 版本已删除');
        await loadInvestmentSkillVersions();
    } catch (error) {
        showInvestmentToast(`删除版本失败：${String(error.message || error)}`, 'error');
    }
}

function renderInvestmentConfigGroup(group, configs, options = {}) {
    const hasTextarea = group.keys.some(([, , type]) => type === 'textarea');
    const sectionClass = options.sectionClass || '';
    return `
        <section class="investment-panel ${sectionClass} ${hasTextarea ? 'investment-workbench-full' : ''}">
            <div class="investment-panel-title"><i class="fas fa-sliders"></i><span>${escapeHtml(group.title)}</span></div>
            <div class="investment-grid ${hasTextarea ? 'cols-1' : 'cols-2'}">
                ${group.keys.map(([key, label, type]) => renderInvestmentConfigField(key, label, type, configs[key])).join('')}
            </div>
        </section>`;
}

function renderInvestmentConfigGroupByTitle(title, configs, options = {}) {
    const group = INVEST_CONFIG_GROUPS.find(item => item.title === title);
    return group ? renderInvestmentConfigGroup(group, configs, options) : '';
}

function renderInvestmentReplyConfigGroups(replyTexts, configs) {
    const groups = replyTexts.groups || [];
    const definitions = replyTexts.definitions || {};
    if (!groups.length) return '';
    const renderedGroups = groups.map(group => `
        <section class="investment-panel investment-workbench-full">
            <div class="investment-panel-title"><i class="fas fa-message"></i><span>${escapeHtml(group.title || '公众号回复词')}</span></div>
            <div class="investment-grid cols-1">
                ${(group.keys || []).map(key => renderInvestmentReplyConfigField(key, definitions[key] || {}, configs[key])).join('')}
            </div>
        </section>`).join('');
    return `
        <section class="investment-panel investment-workbench-full">
            <div class="investment-panel-heading">
                <div>
                    <div class="investment-panel-title"><i class="fas fa-comments"></i><span>公众号回复词</span></div>
                    <div class="investment-subtitle">这些文案会直接展示给公众号客户。带 {} 的文案请保留占位符，系统会自动替换股票或状态名称。</div>
                </div>
            </div>
        </section>
        ${renderedGroups}`;
}

function renderInvestmentReplyConfigField(key, definition, value = '') {
    const label = definition.label || key;
    const description = definition.description || '';
    return `
        <div>
            ${renderInvestmentConfigField(key, label, 'textarea', value, {showSaveButton: true})}
            ${description ? `<div class="investment-config-description">${escapeHtml(description)}</div>` : ''}
        </div>`;
}

function investmentConfigElementId(key) {
    return `invest-config-${String(key || '').replaceAll('.', '-')}`;
}

function investmentJsString(value) {
    return JSON.stringify(String(value || ''));
}

function investmentCanEditConfig(key) {
    if (INVEST_ADMIN_ONLY_CONFIG_KEYS.has(key)) {
        return currentInvestmentAdmin?.role === 'admin' || investmentCan('config.write');
    }
    return investmentCan('config.write');
}

function renderInvestmentConfigField(key, label, type, value = '', options = {}) {
    const id = investmentConfigElementId(key);
    const eventName = type === 'checkbox' ? 'onchange' : 'oninput';
    const canEdit = investmentCanEditConfig(key);
    const showSaveButton = options.showSaveButton === true;
    const keyArg = investmentJsString(key);
    const typeArg = investmentJsString(type);
    const safeId = escapeHtml(id);
    const safeLabel = escapeHtml(label);
    const saveHandler = `saveInvestmentConfigKey(${keyArg}, ${typeArg})`;
    const dirtyHandler = `markInvestmentConfigDirty(${keyArg})`;
    const saveButton = canEdit ? `<button id="${safeId}-save" class="investment-btn investment-config-save${showSaveButton ? '' : ' hidden'}" type="button" onclick='${saveHandler}'><i class="fas fa-floppy-disk"></i><span>保存</span></button>` : '';
    const status = `<span id="${safeId}-status" class="investment-config-status"></span>`;
    const fieldClass = type === 'textarea' ? 'investment-config-field textarea-config' : 'investment-config-field';
    let control = '';
    if (type === 'textarea') {
        control = `<label class="investment-field textarea"><span>${safeLabel}</span><textarea id="${safeId}" rows="4" ${canEdit ? `${eventName}='${dirtyHandler}'` : 'disabled'}>${escapeHtml(value || '')}</textarea></label>`;
    } else if (type === 'checkbox') {
        const checked = value === true || value === 'true' || value === '1';
        control = investmentSwitch(label, id, checked, {attrs: canEdit ? `${eventName}='${dirtyHandler}'` : 'disabled'});
    } else {
        control = `<label class="investment-field"><span>${safeLabel}</span><input id="${safeId}" type="${type}" value="${escapeHtml(value || '')}" ${canEdit ? `${eventName}='${dirtyHandler}'` : 'disabled'}></label>`;
    }
    return `
        <div class="${fieldClass}" data-config-key="${escapeHtml(key)}">
            ${control}
            <div class="investment-config-actions">${saveButton}${status}</div>
        </div>`;
}

function markInvestmentConfigDirty(key) {
    const id = investmentConfigElementId(key);
    const button = document.getElementById(`${id}-save`);
    const status = document.getElementById(`${id}-status`);
    if (button) button.classList.remove('hidden');
    if (status) status.textContent = '未保存';
}

function investmentConfigValue(key, type) {
    const el = document.getElementById(investmentConfigElementId(key));
    return type === 'checkbox' ? el.checked : el.value;
}

async function saveInvestmentConfigKey(key, type) {
    const id = investmentConfigElementId(key);
    const button = document.getElementById(`${id}-save`);
    const status = document.getElementById(`${id}-status`);
    if (button) button.disabled = true;
    if (status) status.textContent = '保存中...';
    try {
        await investmentFetchJson('/api/investment/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                configs: {[key]: investmentConfigValue(key, type)},
            }),
        });
        if (button) button.classList.add('hidden');
        if (status) status.textContent = '已保存';
        showInvestmentToast('配置已保存');
    } catch (error) {
        if (status) status.textContent = String(error.message || error);
        showInvestmentToast('配置保存失败', 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

async function saveInvestmentConfig() {
    const configs = {};
    INVEST_CONFIG_GROUPS.forEach(group => {
        group.keys.forEach(([key, , type]) => {
            const el = document.getElementById(investmentConfigElementId(key));
            configs[key] = type === 'checkbox' ? el.checked : el.value;
        });
    });
    await investmentFetchJson('/api/investment/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({configs}),
    });
    document.getElementById('invest-config-save-result').textContent = '配置已保存';
    await renderInvestmentConfig();
}

async function refreshInvestmentStocks() {
    const resultEl = document.getElementById('invest-stock-action-result');
    const source = document.getElementById('invest-stock-refresh-source')?.value || 'auto';
    if (resultEl) resultEl.textContent = '刷新中...';
    try {
        const data = await investmentFetchJson('/api/investment/stocks/refresh', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({source}),
        });
        const message = `刷新完成：${JSON.stringify(data.result || {})}`;
        await renderInvestmentConfig();
        const nextResultEl = document.getElementById('invest-stock-action-result');
        if (nextResultEl) nextResultEl.textContent = message;
    } catch (error) {
        if (resultEl) resultEl.textContent = String(error.message || error);
    }
}

async function queryInvestmentStocks() {
    const resultEl = document.getElementById('invest-stock-query-result');
    const name = document.getElementById('invest-stock-query-name')?.value || '';
    if (resultEl) resultEl.innerHTML = '<div class="investment-muted">查询中...</div>';
    try {
        const data = await investmentFetchJson(`/api/investment/stocks?name=${encodeURIComponent(name)}&limit=20`);
        if (resultEl) resultEl.innerHTML = renderInvestmentStockRows(data.stocks || []);
    } catch (error) {
        if (resultEl) resultEl.innerHTML = `<div class="investment-alert error">${escapeHtml(String(error.message || error))}</div>`;
    }
}

function investmentHealthLevelLabel(level) {
    if (level === 'error') return '错误';
    if (level === 'warning') return '警告';
    return '正常';
}

function investmentHealthLevelClass(level) {
    if (level === 'error') return 'fail';
    if (level === 'warning') return 'warning';
    return 'ok';
}

async function renderInvestmentHealth(runSmoke = false) {
    const element = investmentContentEl('invest-health-content');
    investmentLoading(element);
    try {
        const data = await investmentFetchJson(runSmoke ? '/api/investment/health?smoke=1' : '/api/investment/health');
        const summaryLevel = data.level || (data.ok ? 'ok' : 'error');
        const summaryClass = investmentHealthLevelClass(summaryLevel);
        const summaryText = summaryLevel === 'error'
            ? '存在错误，当前状态不可上线'
            : (summaryLevel === 'warning' ? '存在警告，可启动但上线前建议处理' : '关键依赖检查通过');
        const summaryIcon = summaryLevel === 'error'
            ? 'fa-triangle-exclamation'
            : (summaryLevel === 'warning' ? 'fa-circle-exclamation' : 'fa-circle-check');
        const rows = (data.checks || []).map(check => `
            <tr>
                <td>${escapeHtml(check.name)}</td>
                <td><span class="investment-badge ${investmentHealthLevelClass(check.level || (check.ok ? 'ok' : 'error'))}">${investmentHealthLevelLabel(check.level || (check.ok ? 'ok' : 'error'))}</span></td>
                <td class="investment-wide">${escapeHtml(check.detail || '')}</td>
            </tr>`).join('');
        element.innerHTML = `
            <div class="investment-layout">
                <section class="investment-panel full">
                    <div class="investment-panel-title"><i class="fas fa-heart-pulse"></i><span>上线前检查</span></div>
                    <div class="investment-health-summary ${summaryClass}">
                        <i class="fas ${summaryIcon}"></i>
                        <span>${summaryText}</span>
                    </div>
                    <div class="investment-actions">
                        ${investmentButton('fa-vial-circle-check', '运行完整检查', 'runInvestmentFullHealthCheck()', 'primary')}
                    </div>
                </section>
                <section class="investment-table-panel full">
                    <div class="investment-panel-title"><i class="fas fa-heart-pulse"></i><span>检查项详情</span></div>
                    ${investmentTableWrap(`<table class="investment-table">
                        <thead><tr><th>检查项</th><th>状态</th><th>详情</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>`)}
                </section>
            </div>`;
    } catch (error) {
        investmentError(element, error);
    }
}

async function runInvestmentFullHealthCheck() {
    await renderInvestmentHealth(true);
}

window.resetInvestmentUserForm = resetInvestmentUserForm;
window.editInvestmentUser = editInvestmentUser;
window.openInvestmentUserDialog = openInvestmentUserDialog;
window.openInvestmentAdminUserDialog = openInvestmentAdminUserDialog;
window.openInvestmentUsersImportDialog = openInvestmentUsersImportDialog;
window.openInvestmentCustomerExportDialog = openInvestmentCustomerExportDialog;
window.downloadInvestmentUsersExport = downloadInvestmentUsersExport;
window.exportInvestmentUsers = exportInvestmentUsers;
window.parseInvestmentUsersImport = parseInvestmentUsersImport;
window.confirmInvestmentUsersImport = confirmInvestmentUsersImport;
window.applyInvestmentCustomerSearch = applyInvestmentCustomerSearch;
window.clearInvestmentCustomerSearch = clearInvestmentCustomerSearch;
window.applyInvestmentAdminSearch = applyInvestmentAdminSearch;
window.changeInvestmentUserPage = changeInvestmentUserPage;
window.handleInvestmentUserServiceToggle = handleInvestmentUserServiceToggle;
window.saveInvestmentUser = saveInvestmentUser;
window.setInvestmentUserStatus = setInvestmentUserStatus;
window.disableInvestmentUser = disableInvestmentUser;
window.importInvestmentUsers = importInvestmentUsers;
window.createInvestmentContent = createInvestmentContent;
window.switchInvestmentUploadMode = switchInvestmentUploadMode;
window.updateInvestmentUploadFileSummary = updateInvestmentUploadFileSummary;
window.investmentShouldAutoEffectiveAfterGenerate = investmentShouldAutoEffectiveAfterGenerate;
window.syncInvestmentDefaultExpiresAt = syncInvestmentDefaultExpiresAt;
window.changeInvestmentExpiresMode = changeInvestmentExpiresMode;
window.toggleInvestmentExpiresAt = toggleInvestmentExpiresAt;
window.investmentToggleTimePicker = investmentToggleTimePicker;
window.investmentSetTimePickerValue = investmentSetTimePickerValue;
window.investmentSelectTime = investmentSelectTime;
window.generateInvestmentContent = generateInvestmentContent;
window.effectiveInvestmentContent = effectiveInvestmentContent;
window.renderInvestmentOperationAudits = renderInvestmentOperationAudits;
window.refreshInvestmentContentAction = refreshInvestmentContentAction;
window.runInvestmentFullHealthCheck = runInvestmentFullHealthCheck;
window.switchInvestmentContentPanel = switchInvestmentContentPanel;
window.renderInvestmentRecords = renderInvestmentRecords;
window.switchInvestmentRecordsTab = switchInvestmentRecordsTab;
window.applyInvestmentRecordsFilters = applyInvestmentRecordsFilters;
window.resetInvestmentRecordsFilters = resetInvestmentRecordsFilters;
window.loadInvestmentRecordsTab = loadInvestmentRecordsTab;
window.changeInvestmentRecordsPage = changeInvestmentRecordsPage;
window.changeInvestmentRecordsPageSize = changeInvestmentRecordsPageSize;
window.openInvestmentRequestExportDialog = openInvestmentRequestExportDialog;
window.changeInvestmentRequestExportMode = changeInvestmentRequestExportMode;
window.exportInvestmentRequestRecordsByCurrentFilters = exportInvestmentRequestRecordsByCurrentFilters;
window.exportInvestmentRequestRecordsFull = exportInvestmentRequestRecordsFull;
window.exportInvestmentRequestRecordsByRange = exportInvestmentRequestRecordsByRange;
window.exportInvestmentRequestRecordsByMonth = exportInvestmentRequestRecordsByMonth;
window.exportInvestmentRequestRecordsByQuarter = exportInvestmentRequestRecordsByQuarter;
window.openInvestmentRecordDrawer = openInvestmentRecordDrawer;
window.closeInvestmentRecordDrawer = closeInvestmentRecordDrawer;
window.selectInvestmentCacheDate = selectInvestmentCacheDate;
window.applyInvestmentCacheDate = applyInvestmentCacheDate;
window.selectInvestmentCacheCategory = selectInvestmentCacheCategory;
window.backInvestmentCacheCategoryMenu = backInvestmentCacheCategoryMenu;
window.showInvestmentContentDetail = showInvestmentContentDetail;
window.showInvestmentRequestDetail = showInvestmentRequestDetail;
window.invalidateInvestmentCache = invalidateInvestmentCache;
window.clearInvestmentTechnicalAnalysisCacheByDate = clearInvestmentTechnicalAnalysisCacheByDate;
window.clearInvestmentGeneratedContentCacheByDate = clearInvestmentGeneratedContentCacheByDate;
window.hideInvestmentDetail = hideInvestmentDetail;
window.hideInvestmentModal = hideInvestmentModal;
window.saveInvestmentConfig = saveInvestmentConfig;
window.switchInvestmentConfigPanel = switchInvestmentConfigPanel;
window.markInvestmentConfigDirty = markInvestmentConfigDirty;
window.saveInvestmentConfigKey = saveInvestmentConfigKey;
window.loadInvestmentSkillVersions = loadInvestmentSkillVersions;
window.uploadInvestmentSkill = uploadInvestmentSkill;
window.uploadInvestmentSkillPackage = uploadInvestmentSkillPackage;
window.openInvestmentSkillDialog = openInvestmentSkillDialog;
window.saveInvestmentSkillSettings = saveInvestmentSkillSettings;
window.saveInvestmentSkillDialog = saveInvestmentSkillDialog;
window.activateInvestmentSkillVersion = activateInvestmentSkillVersion;
window.deleteInvestmentSkillVersion = deleteInvestmentSkillVersion;
window.selectedInvestmentSkillVersion = selectedInvestmentSkillVersion;
window.refreshInvestmentStocks = refreshInvestmentStocks;
window.queryInvestmentStocks = queryInvestmentStocks;

document.querySelectorAll('.menu-group > button').forEach(btn => {
    btn.addEventListener('click', () => {
        btn.parentElement.classList.toggle('open');
    });
});

document.querySelectorAll('.sidebar-item').forEach(item => {
    item.addEventListener('click', () => navigateTo(item.dataset.view));
});

window.addEventListener('resize', () => {
    if (window.innerWidth >= 1024) {
        document.getElementById('sidebar').classList.remove('-translate-x-full');
        document.getElementById('sidebar-overlay').classList.add('hidden');
    } else {
        if (!document.getElementById('sidebar').classList.contains('-translate-x-full')) {
            closeSidebar();
        }
    }
});

// =====================================================================
// Markdown Renderer
// =====================================================================
const FALLBACK_HLJS = {
    getLanguage() { return false; },
    highlight(str) { return { value: escapeHtml(str) }; },
    highlightAuto(str) { return { value: escapeHtml(str) }; },
    highlightElement() {},
};

function getHljs() {
    return window.hljs || FALLBACK_HLJS;
}

function createMd() {
    const hljsLib = getHljs();
    const mdFactory = window.markdownit;
    if (typeof mdFactory !== 'function') {
        return {
            render(text) {
                return `<p>${escapeHtml(text || '')}</p>`;
            }
        };
    }
    const md = mdFactory({
        html: false, breaks: true, linkify: true, typographer: true,
        highlight: function(str, lang) {
            if (lang && hljsLib.getLanguage(lang)) {
                try { return hljsLib.highlight(str, { language: lang }).value; } catch (_) {}
            }
            return hljsLib.highlightAuto(str).value;
        }
    });
    const defaultLinkOpen = md.renderer.rules.link_open || function(tokens, idx, options, env, self) {
        return self.renderToken(tokens, idx, options);
    };
    md.renderer.rules.link_open = function(tokens, idx, options, env, self) {
        tokens[idx].attrPush(['target', '_blank']);
        tokens[idx].attrPush(['rel', 'noopener noreferrer']);
        return defaultLinkOpen(tokens, idx, options, env, self);
    };
    return md;
}

const md = createMd();

const VIDEO_EXT_RE = /\.(?:mp4|webm|mov|avi|mkv)$/i;  // tested against URL without query string
const IMAGE_EXT_RE = /\.(?:jpg|jpeg|png|gif|webp|bmp|svg)$/i;  // tested against URL without query string

function _toWebUrl(url) {
    if (/^\/[A-Za-z]/.test(url) && !url.startsWith('/api/')) {
        return '/api/file?path=' + encodeURIComponent(url);
    }
    if (/^file:\/\/\//i.test(url)) {
        return '/api/file?path=' + encodeURIComponent(url.replace(/^file:\/\/\//i, '/'));
    }
    return url;
}

function _buildVideoHtml(url) {
    const webUrl = _toWebUrl(url);
    const fileName = url.split('/').pop().split('?')[0];
    return `<div style="margin:10px 0;">` +
        `<video controls preload="metadata" ` +
        `style="max-width:100%;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.15);display:block;">` +
        `<source src="${webUrl}"></video>` +
        `<a href="${webUrl}" target="_blank" ` +
        `style="display:inline-flex;align-items:center;gap:4px;margin-top:4px;font-size:12px;color:#8b8fa8;text-decoration:none;">` +
        `<i class="fas fa-download"></i> ${escapeHtml(fileName)}</a></div>`;
}

function _openImageLightbox(src) {
    let overlay = document.getElementById('cow-lightbox');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'cow-lightbox';
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;cursor:zoom-out;opacity:0;transition:opacity .2s';
        overlay.onclick = () => { overlay.style.opacity = '0'; setTimeout(() => overlay.style.display = 'none', 200); };
        const img = document.createElement('img');
        img.id = 'cow-lightbox-img';
        img.style.cssText = 'max-width:92vw;max-height:92vh;border-radius:8px;box-shadow:0 4px 24px rgba(0,0,0,0.5);object-fit:contain;';
        img.onclick = (e) => e.stopPropagation();
        overlay.appendChild(img);
        document.body.appendChild(overlay);
    }
    overlay.querySelector('#cow-lightbox-img').src = src;
    overlay.style.display = 'flex';
    requestAnimationFrame(() => overlay.style.opacity = '1');
}

function _buildImageHtml(url) {
    const webUrl = _toWebUrl(url);
    const safeUrl = webUrl.replace(/"/g, '&quot;');
    return `<div style="margin:10px 0;">` +
        `<img src="${safeUrl}" alt="image" loading="lazy" ` +
        `onclick="_openImageLightbox(this.src)" ` +
        `style="max-width:520px;width:100%;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.15);display:block;cursor:zoom-in;">` +
        `</div>`;
}

function injectVideoPlayers(html) {
    // Step 1: replace markdown-it anchor tags whose href points to a video file.
    const step1 = html.replace(
        /<a\s+href="(https?:\/\/[^"]+)"[^>]*>[^<]*<\/a>/gi,
        (match, url) => VIDEO_EXT_RE.test(url.split('?')[0]) ? _buildVideoHtml(url) : match
    );
    // Step 2: replace any remaining bare video URLs in text nodes (not inside HTML tags).
    // Split on HTML tags to avoid touching src/href attributes already in markup.
    return step1.split(/(<[^>]+>)/).map((chunk, idx) => {
        // Even indices are text nodes; odd indices are HTML tags — leave them untouched.
        if (idx % 2 !== 0) return chunk;
        return chunk.replace(/https?:\/\/\S+/gi, (url) => {
            const bare = url.replace(/[),.\s]+$/, '');  // strip trailing punctuation
            return VIDEO_EXT_RE.test(bare.split('?')[0]) ? _buildVideoHtml(bare) : url;
        });
    }).join('');
}

// Convert image URLs into inline <img> previews. Mirrors injectVideoPlayers but for images.
// Handles three cases produced by markdown-it:
//   1. <a href="...image.jpg">...</a>  (bare URL or autolink that linkify turned into an anchor)
//   2. <img src="...">                  (markdown image syntax) — leave as-is, but normalize style
//   3. raw URL still present in a text node                    — only as a safety net
function injectImagePreviews(html) {
    // Step 1: anchor whose href points to an image file -> replace with <img> preview.
    const step1 = html.replace(
        /<a\s+href="(https?:\/\/[^"]+)"[^>]*>[^<]*<\/a>/gi,
        (match, url) => IMAGE_EXT_RE.test(url.split('?')[0]) ? _buildImageHtml(url) : match
    );
    // Step 2: bare image URLs left in text nodes (rare — markdown-it's linkify usually catches them).
    return step1.split(/(<[^>]+>)/).map((chunk, idx) => {
        if (idx % 2 !== 0) return chunk;
        return chunk.replace(/https?:\/\/\S+/gi, (url) => {
            const bare = url.replace(/[),.\s]+$/, '');
            return IMAGE_EXT_RE.test(bare.split('?')[0]) ? _buildImageHtml(bare) : url;
        });
    }).join('');
}

function _rewriteLocalImgSrc(html) {
    return html.replace(/<img\s([^>]*?)src="([^"]+)"([^>]*?)>/gi, (match, pre, src, post) => {
        const webSrc = _toWebUrl(src);
        const safeSrc = webSrc.replace(/"/g, '&quot;');
        const hasClick = /onclick/i.test(pre + post);
        const clickAttr = hasClick ? '' : ` onclick="_openImageLightbox(this.src)" style="cursor:zoom-in;"`;
        return `<img ${pre}src="${safeSrc}"${post}${clickAttr}>`;
    });
}

function renderMarkdown(text) {
    try {
        let html = md.render(text);
        html = _rewriteLocalImgSrc(html);
        // Order matters: video first (more specific), then image.
        return injectImagePreviews(injectVideoPlayers(html));
    }
    catch (e) { return text.replace(/\n/g, '<br>'); }
}

// =====================================================================
// Chat Module
// =====================================================================
let isPolling = false;
let pollGeneration = 0;   // incremented on each restart to cancel stale poll loops
let loadingContainers = {};
let activeStreams = {};   // request_id -> EventSource
let isComposing = false;
let appConfig = { use_agent: false, title: '智能投研辅助系统', subtitle: '', providers: {}, api_bases: {} };

const SESSION_ID_KEY = 'cow_session_id';

function generateSessionId() {
    return 'session_' + ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
        (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    );
}

// Restore session_id from localStorage so conversation history survives page refresh.
// A new id is only generated when the user explicitly starts a new chat.
function loadOrCreateSessionId() {
    const stored = localStorage.getItem(SESSION_ID_KEY);
    if (stored) return stored;
    const fresh = generateSessionId();
    localStorage.setItem(SESSION_ID_KEY, fresh);
    return fresh;
}

let sessionId = loadOrCreateSessionId();

// ---- Conversation history state ----
let historyPage = 0;       // last page fetched (0 = nothing fetched yet)
let historyHasMore = false;
let historyLoading = false;

fetch('/config').then(r => r.json()).then(data => {
    if (data.status === 'success') {
        appConfig = data;
        const title = data.title || '智能投研辅助系统';
        document.getElementById('welcome-title').textContent = title;
        initConfigView(data);
    }
    loadHistory(1);
}).catch(() => { loadHistory(1); });

// Start polling immediately so scheduler/push messages are received at any time
startPolling();

const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const messagesDiv = document.getElementById('chat-messages');
const fileInput = document.getElementById('file-input');
const folderInput = document.getElementById('folder-input');
const attachBtn = document.getElementById('attach-btn');
const attachMenu = document.getElementById('attach-menu');
const attachFolderOption = document.getElementById('attach-folder-option');
const supportsDirectoryUpload = !!folderInput && 'webkitdirectory' in folderInput;

if (!supportsDirectoryUpload && attachFolderOption) {
    attachFolderOption.classList.add('hidden');
}

// Smart auto-scroll: pause when user scrolls up, resume when near bottom
let _autoScrollEnabled = true;
const _SCROLL_THRESHOLD = 80; // px from bottom to re-enable auto-scroll

messagesDiv.addEventListener('scroll', () => {
    const distFromBottom = messagesDiv.scrollHeight - messagesDiv.scrollTop - messagesDiv.clientHeight;
    _autoScrollEnabled = distFromBottom <= _SCROLL_THRESHOLD;
    _updateScrollToBottomBtn();
});

// Intercept internal navigation links in chat messages
messagesDiv.addEventListener('click', (e) => {
    const copyBtn = e.target.closest('.copy-msg-btn');
    if (copyBtn) {
        e.preventDefault();
        const msgRoot = copyBtn.closest('.flex.gap-3');
        const answerEl = msgRoot && msgRoot.querySelector('.answer-content');
        const rawMd = answerEl && answerEl.dataset.rawMd;
        if (rawMd) {
            navigator.clipboard.writeText(rawMd).then(() => {
                const icon = copyBtn.querySelector('i');
                if (icon) { icon.className = 'fas fa-check'; setTimeout(() => { icon.className = 'fas fa-copy'; }, 1500); }
            });
        }
        return;
    }
});
const attachmentPreview = document.getElementById('attachment-preview');

// Pending attachments: [{file_path, file_name, file_type, preview_url}]
// Items with _uploading=true are still in flight.
let pendingAttachments = [];
let uploadingCount = 0;

// Input history (like terminal arrow-key recall)
const inputHistory = [];
let historyIdx = -1;
let historySavedDraft = '';

function updateSendBtnState() {
    sendBtn.disabled = uploadingCount > 0 || (!chatInput.value.trim() && pendingAttachments.length === 0);
}

function renderAttachmentPreview() {
    if (pendingAttachments.length === 0) {
        attachmentPreview.classList.add('hidden');
        attachmentPreview.innerHTML = '';
        updateSendBtnState();
        return;
    }
    attachmentPreview.classList.remove('hidden');
    attachmentPreview.innerHTML = pendingAttachments.map((att, idx) => {
        if (att._uploading) {
            const suffix = att.file_type === 'directory' && att.file_count
                ? ` (${att.file_count})`
                : '';
            return `<div class="att-chip att-uploading" data-idx="${idx}">
                <i class="fas fa-spinner fa-spin"></i>
                <span class="att-name">${escapeHtml(att.file_name)}${suffix}</span>
            </div>`;
        }
        if (att.file_type === 'image') {
            return `<div class="att-thumb" data-idx="${idx}">
                <img src="${att.preview_url}" alt="${escapeHtml(att.file_name)}">
                <button class="att-remove" onclick="removeAttachment(${idx})">&times;</button>
            </div>`;
        }
        const icon = att.file_type === 'video'
            ? 'fa-film'
            : (att.file_type === 'directory' ? 'fa-folder-tree' : 'fa-file-alt');
        const suffix = att.file_type === 'directory' && att.file_count
            ? ` (${att.file_count})`
            : '';
        return `<div class="att-chip" data-idx="${idx}">
            <i class="fas ${icon}"></i>
            <span class="att-name">${escapeHtml(att.file_name)}${suffix}</span>
            <button class="att-remove" onclick="removeAttachment(${idx})">&times;</button>
        </div>`;
    }).join('');
    updateSendBtnState();
}

function removeAttachment(idx) {
    if (pendingAttachments[idx]?._uploading) return;
    pendingAttachments.splice(idx, 1);
    renderAttachmentPreview();
}

function isAttachMenuVisible() {
    return attachMenu && !attachMenu.classList.contains('hidden');
}

function hideAttachMenu() {
    if (attachMenu) attachMenu.classList.add('hidden');
}

function toggleAttachMenu(event) {
    if (!attachMenu) return;
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    attachMenu.classList.toggle('hidden');
}

function triggerFileUpload() {
    hideAttachMenu();
    fileInput?.click();
}

function triggerFolderUpload() {
    if (!supportsDirectoryUpload) return;
    hideAttachMenu();
    folderInput?.click();
}

async function handleFileSelect(files) {
    if (!files || files.length === 0) return;
    const tasks = [];
    for (const file of files) {
        const placeholder = { file_name: file.name, file_type: 'file', _uploading: true };
        pendingAttachments.push(placeholder);
        uploadingCount++;
        renderAttachmentPreview();

        tasks.push((async () => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('session_id', sessionId);
            try {
                const resp = await fetch('/upload', { method: 'POST', body: formData });
                const data = await resp.json();
                if (data.status === 'success') {
                    placeholder.file_path = data.file_path;
                    placeholder.file_name = data.file_name;
                    placeholder.file_type = data.file_type;
                    placeholder.preview_url = data.preview_url;
                    delete placeholder._uploading;
                } else {
                    const i = pendingAttachments.indexOf(placeholder);
                    if (i !== -1) pendingAttachments.splice(i, 1);
                }
            } catch (e) {
                console.error('Upload failed:', e);
                const i = pendingAttachments.indexOf(placeholder);
                if (i !== -1) pendingAttachments.splice(i, 1);
            }
            uploadingCount--;
            renderAttachmentPreview();
        })());
    }
    await Promise.all(tasks);
}

function _makeUploadId() {
    return `dir_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function _groupDirectoryFiles(files) {
    const groups = new Map();
    for (const file of Array.from(files || [])) {
        const relPath = file.webkitRelativePath || file.name;
        const parts = relPath.split('/').filter(Boolean);
        const rootName = parts[0] || file.name;
        if (!groups.has(rootName)) groups.set(rootName, []);
        groups.get(rootName).push({ file, relPath });
    }
    return groups;
}

async function handleFolderSelect(files) {
    if (!files || files.length === 0) return;
    const groups = _groupDirectoryFiles(files);
    const groupTasks = [];

    for (const [rootName, entries] of groups.entries()) {
        const placeholder = {
            file_name: rootName,
            file_type: 'directory',
            file_count: entries.length,
            _uploading: true,
        };
        pendingAttachments.push(placeholder);
        uploadingCount++;
        renderAttachmentPreview();

        const uploadId = _makeUploadId();
        groupTasks.push((async () => {
            try {
                const formData = new FormData();
                formData.append('session_id', sessionId);
                formData.append('upload_id', uploadId);
                for (const { file, relPath } of entries) {
                    formData.append('files', file);
                    formData.append('relative_paths', relPath);
                }

                const resp = await fetch('/upload', { method: 'POST', body: formData });
                const data = await resp.json();
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Upload failed');
                }
                if (!data.root_path) {
                    throw new Error('Directory root path missing');
                }
                placeholder.file_path = data.root_path;
                placeholder.file_name = data.root_name || rootName;
                delete placeholder._uploading;
            } catch (e) {
                console.error('Directory upload failed:', e);
                const i = pendingAttachments.indexOf(placeholder);
                if (i !== -1) pendingAttachments.splice(i, 1);
            } finally {
                uploadingCount--;
            }
            renderAttachmentPreview();
        })());
    }

    await Promise.all(groupTasks);
}

fileInput.addEventListener('change', function() {
    handleFileSelect(this.files);
    this.value = '';
});

folderInput.addEventListener('change', function() {
    handleFolderSelect(this.files);
    this.value = '';
});

document.addEventListener('click', (e) => {
    if (!isAttachMenuVisible()) return;
    if (attachMenu.contains(e.target) || attachBtn.contains(e.target)) return;
    hideAttachMenu();
});

// Drag-and-drop support on chat input area
const chatInputArea = chatInput.closest('.flex-shrink-0');
chatInputArea.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); chatInputArea.classList.add('drag-over'); });
chatInputArea.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); chatInputArea.classList.remove('drag-over'); });
chatInputArea.addEventListener('drop', (e) => {
    e.preventDefault(); e.stopPropagation();
    chatInputArea.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files);
});

// Paste image support
chatInput.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files = [];
    for (const item of items) {
        if (item.kind === 'file') {
            files.push(item.getAsFile());
        }
    }
    if (files.length) {
        e.preventDefault();
        handleFileSelect(files);
    }
});

chatInput.addEventListener('compositionstart', () => { isComposing = true; });
chatInput.addEventListener('compositionend', () => { setTimeout(() => { isComposing = false; }, 100); });

// ── Slash Command Menu ───────────────────────────────────────
const SLASH_COMMANDS = [
    { cmd: '/help',                desc: '显示命令帮助' },
    { cmd: '/status',              desc: '查看运行状态' },
    { cmd: '/context',             desc: '查看对话上下文' },
    { cmd: '/context clear',       desc: '清除对话上下文' },
    { cmd: '/skill list',          desc: '查看已安装技能' },
    { cmd: '/skill list --remote', desc: '浏览技能广场' },
    { cmd: '/skill search ',       desc: '搜索技能' },
    { cmd: '/skill install ',      desc: '安装技能 (名称或 GitHub URL)' },
    { cmd: '/skill uninstall ',    desc: '卸载技能' },
    { cmd: '/skill info ',         desc: '查看技能详情' },
    { cmd: '/skill enable ',       desc: '启用技能' },
    { cmd: '/skill disable ',      desc: '禁用技能' },
    { cmd: '/config',              desc: '查看当前配置' },
    { cmd: '/logs',                desc: '查看最近日志' },
    { cmd: '/version',             desc: '查看版本' },
];

const slashMenu = document.getElementById('slash-menu');
let slashActiveIdx = 0;
let slashFiltered = [];
let slashJustSelected = false;
let slashLastFilter = '';
let slashLastMouseX = -1;
let slashLastMouseY = -1;

function showSlashMenu(filter) {
    const q = filter.toLowerCase();
    if (q === slashLastFilter && !slashMenu.classList.contains('hidden')) return;
    slashLastFilter = q;

    const newFiltered = SLASH_COMMANDS.filter(c => c.cmd.toLowerCase().startsWith(q));
    if (newFiltered.length === 0) {
        hideSlashMenu();
        return;
    }

    const changed = newFiltered.length !== slashFiltered.length ||
        newFiltered.some((c, i) => c.cmd !== slashFiltered[i]?.cmd);
    slashFiltered = newFiltered;
    if (changed) slashActiveIdx = 0;
    slashActiveIdx = Math.min(slashActiveIdx, slashFiltered.length - 1);

    slashNavByKeyboard = true;
    renderSlashItems();
    slashMenu.classList.remove('hidden');
}

function hideSlashMenu() {
    slashMenu.classList.add('hidden');
    slashMenu.innerHTML = '';
    slashFiltered = [];
    slashActiveIdx = -1;
    slashLastFilter = '';
    slashNavByKeyboard = false;
    slashLastMouseX = -1;
    slashLastMouseY = -1;
}

function isSlashMenuVisible() {
    return !slashMenu.classList.contains('hidden') && slashFiltered.length > 0;
}

function renderSlashItems() {
    slashMenu.innerHTML =
        '<div class="slash-menu-header">Commands</div>' +
        slashFiltered.map((c, i) =>
            `<div class="slash-menu-item${i === slashActiveIdx ? ' active' : ''}" data-idx="${i}">` +
            `<span class="cmd">${escapeHtml(c.cmd)}</span>` +
            `<span class="desc">${escapeHtml(c.desc)}</span></div>`
        ).join('');

    const activeEl = slashMenu.querySelector('.slash-menu-item.active');
    if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });
}

// Delegated events on the persistent slashMenu container (not destroyed by innerHTML)
// Use coordinate comparison to distinguish real mouse movement from DOM-rebuild phantom events.
slashMenu.addEventListener('mousemove', (e) => {
    if (e.clientX === slashLastMouseX && e.clientY === slashLastMouseY) return;
    slashLastMouseX = e.clientX;
    slashLastMouseY = e.clientY;
    if (!slashNavByKeyboard) return;
    slashNavByKeyboard = false;
    const item = e.target.closest('.slash-menu-item');
    if (!item) return;
    const idx = parseInt(item.dataset.idx);
    if (idx === slashActiveIdx) return;
    slashActiveIdx = idx;
    slashMenu.querySelectorAll('.slash-menu-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.idx) === idx);
    });
});

slashMenu.addEventListener('mouseover', (e) => {
    if (slashNavByKeyboard) return;
    const item = e.target.closest('.slash-menu-item');
    if (!item) return;
    const idx = parseInt(item.dataset.idx);
    if (idx === slashActiveIdx) return;
    slashActiveIdx = idx;
    slashMenu.querySelectorAll('.slash-menu-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.idx) === idx);
    });
});

slashMenu.addEventListener('mousedown', (e) => {
    const item = e.target.closest('.slash-menu-item');
    if (!item) return;
    e.preventDefault();
    selectSlashCommand(parseInt(item.dataset.idx));
});

function selectSlashCommand(idx) {
    if (idx < 0 || idx >= slashFiltered.length) return;
    const chosen = slashFiltered[idx].cmd;
    slashJustSelected = true;
    chatInput.value = chosen;
    chatInput.dispatchEvent(new Event('input'));
    hideSlashMenu();
    chatInput.focus();
    chatInput.selectionStart = chatInput.selectionEnd = chosen.length;
}

chatInput.addEventListener('input', function() {
    this.style.height = '42px';
    const scrollH = this.scrollHeight;
    const newH = Math.min(scrollH, 180);
    this.style.height = newH + 'px';
    this.style.overflowY = scrollH > 180 ? 'auto' : 'hidden';
    updateSendBtnState();

    const val = this.value;
    if (slashJustSelected) {
        slashJustSelected = false;
    } else if (val.startsWith('/')) {
        showSlashMenu(val);
    } else {
        hideSlashMenu();
    }
});

chatInput.addEventListener('keydown', function(e) {
    if (e.keyCode === 229 || e.isComposing || isComposing) return;

    if (e.key === 'Escape' && isAttachMenuVisible()) {
        hideAttachMenu();
        return;
    }

    if (isSlashMenuVisible()) {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            slashNavByKeyboard = true;
            slashActiveIdx = Math.min(slashActiveIdx + 1, slashFiltered.length - 1);
            renderSlashItems();
            return;
        }
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            slashNavByKeyboard = true;
            slashActiveIdx = Math.max(slashActiveIdx - 1, 0);
            renderSlashItems();
            return;
        }
        if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            selectSlashCommand(slashActiveIdx);
            return;
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            hideSlashMenu();
            return;
        }
        if (e.key === 'Tab') {
            e.preventDefault();
            selectSlashCommand(slashActiveIdx);
            return;
        }
    }

    // Arrow-key history recall (only when input is empty or already browsing history)
    if (e.key === 'ArrowUp' && inputHistory.length > 0 && !isSlashMenuVisible()) {
        const curVal = this.value.trim();
        const isSingleLine = !this.value.includes('\n');
        if (isSingleLine && (curVal === '' || historyIdx >= 0)) {
            e.preventDefault();
            if (historyIdx < 0) {
                historySavedDraft = this.value;
                historyIdx = inputHistory.length - 1;
            } else if (historyIdx > 0) {
                historyIdx--;
            }
            this.value = inputHistory[historyIdx];
            slashJustSelected = true;
            this.dispatchEvent(new Event('input'));
            hideSlashMenu();
            this.selectionStart = this.selectionEnd = this.value.length;
            return;
        }
    }
    if (e.key === 'ArrowDown' && historyIdx >= 0 && !isSlashMenuVisible()) {
        const isSingleLine = !this.value.includes('\n');
        if (isSingleLine) {
            e.preventDefault();
            if (historyIdx < inputHistory.length - 1) {
                historyIdx++;
                this.value = inputHistory[historyIdx];
            } else {
                historyIdx = -1;
                this.value = historySavedDraft;
                historySavedDraft = '';
            }
            slashJustSelected = true;
            this.dispatchEvent(new Event('input'));
            hideSlashMenu();
            this.selectionStart = this.selectionEnd = this.value.length;
            return;
        }
    }

    if ((e.ctrlKey || e.shiftKey) && e.key === 'Enter') {
        const start = this.selectionStart;
        const end = this.selectionEnd;
        this.value = this.value.substring(0, start) + '\n' + this.value.substring(end);
        this.selectionStart = this.selectionEnd = start + 1;
        this.dispatchEvent(new Event('input'));
        e.preventDefault();
    } else if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
        sendMessage();
        e.preventDefault();
    }
});

chatInput.addEventListener('blur', () => {
    setTimeout(hideSlashMenu, 150);
});

document.querySelectorAll('.example-card').forEach(card => {
    card.addEventListener('click', () => {
        // data-send overrides the visible text (e.g. show "查看全部命令" but send "/help")
        const sendText = card.dataset.send;
        if (sendText) {
            chatInput.value = sendText;
            chatInput.dispatchEvent(new Event('input'));
            chatInput.focus();
            return;
        }
        const textEl = card.querySelector('[data-i18n*="text"]');
        if (textEl) {
            chatInput.value = textEl.textContent;
            chatInput.dispatchEvent(new Event('input'));
            chatInput.focus();
        }
    });
});

function sendMessage() {
    const text = chatInput.value.trim();
    if (!text && pendingAttachments.length === 0) return;

    if (text) {
        inputHistory.push(text);
        historyIdx = -1;
        historySavedDraft = '';
    }

    const ws = document.getElementById('welcome-screen');
    const isFirstMessage = !!ws;
    if (ws) ws.remove();

    const titleInfo = (isFirstMessage && text) ? { sid: sessionId, userMsg: text } : null;

    const timestamp = new Date();
    const attachments = [...pendingAttachments];
    addUserMessage(text, timestamp, attachments);

    const loadingEl = addLoadingIndicator();

    chatInput.value = '';
    chatInput.style.height = '42px';
    chatInput.style.overflowY = 'hidden';
    pendingAttachments = [];
    renderAttachmentPreview();
    sendBtn.disabled = true;

    const body = { session_id: sessionId, message: text, stream: true, timestamp: timestamp.toISOString() };
    if (attachments.length > 0) {
        body.attachments = attachments.map(a => ({
            file_path: a.file_path,
            file_name: a.file_name,
            file_type: a.file_type,
            file_count: a.file_count,
        }));
    }

    const MAX_RETRIES = 2;
    const RETRY_DELAY_MS = 1000;

    function postWithRetry(attempt) {
        fetch('/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                if (data.stream) {
                    startSSE(data.request_id, loadingEl, timestamp, titleInfo);
                } else {
                    loadingContainers[data.request_id] = loadingEl;
                }
            } else {
                loadingEl.remove();
                addBotMessage(t('error_send'), new Date());
            }
        })
        .catch(err => {
            if (err.name === 'AbortError') {
                loadingEl.remove();
                addBotMessage(t('error_timeout'), new Date());
                return;
            }
            if (attempt < MAX_RETRIES) {
                console.warn(`[sendMessage] attempt ${attempt + 1} failed, retrying...`, err);
                setTimeout(() => postWithRetry(attempt + 1), RETRY_DELAY_MS * (attempt + 1));
                return;
            }
            loadingEl.remove();
            addBotMessage(t('error_send'), new Date());
        });
    }

    postWithRetry(0);
}

function startSSE(requestId, loadingEl, timestamp, titleInfo) {
    let botEl = null;
    let stepsEl = null;    // .agent-steps  (thinking summaries + tool indicators)
    let contentEl = null;  // .answer-content (final streaming answer)
    let mediaEl = null;    // .media-content (images & file attachments)
    let accumulatedText = '';
    let currentToolEl = null;
    let currentReasoningEl = null;  // live reasoning bubble
    let reasoningText = '';
    let reasoningStartTime = 0;
    let done = false;

    const MAX_RECONNECTS = 10;
    const RECONNECT_BASE_MS = 1000;
    let reconnectCount = 0;

    function ensureBotEl() {
        if (botEl) return;
        if (loadingEl) { loadingEl.remove(); loadingEl = null; }
        botEl = document.createElement('div');
        botEl.className = 'flex gap-3 px-4 sm:px-6 py-3';
        botEl.dataset.requestId = requestId;
        botEl.innerHTML = `
            <img src="assets/logo.jpg" alt="智能投研辅助系统" class="w-8 h-8 rounded-lg flex-shrink-0">
            <div class="min-w-0 flex-1 max-w-[85%]">
                <div class="bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-2xl px-4 py-3 text-sm leading-relaxed msg-content text-slate-700 dark:text-slate-200">
                    <div class="agent-steps"></div>
                    <div class="answer-content sse-streaming"></div>
                    <div class="media-content"></div>
                </div>
                <div class="flex items-center gap-2 mt-1.5">
                    <span class="text-xs text-slate-400 dark:text-slate-500">${formatTime(timestamp)}</span>
                    <button class="copy-msg-btn text-xs text-slate-300 dark:text-slate-600 hover:text-slate-500 dark:hover:text-slate-400 transition-colors cursor-pointer" title="${currentLang === 'zh' ? '复制' : 'Copy'}" style="display:none">
                        <i class="fas fa-copy"></i>
                    </button>
                </div>
            </div>
        `;
        messagesDiv.appendChild(botEl);
        stepsEl = botEl.querySelector('.agent-steps');
        contentEl = botEl.querySelector('.answer-content');
        mediaEl = botEl.querySelector('.media-content');
    }

    function connect() {
        const es = new EventSource(`/stream?request_id=${encodeURIComponent(requestId)}`);
        activeStreams[requestId] = es;

        es.onmessage = function(e) {
            let item;
            try { item = JSON.parse(e.data); } catch (_) { return; }

            // Successful data received, reset reconnect counter
            reconnectCount = 0;

            if (item.type === 'reasoning') {
                ensureBotEl();
                reasoningText += item.content;
                if (!currentReasoningEl) {
                    reasoningStartTime = Date.now();
                    currentReasoningEl = document.createElement('div');
                    currentReasoningEl.className = 'agent-step agent-thinking-step';
                    // During streaming, use a <pre> with a single text node and
                    // append-only updates. This avoids re-parsing markdown and
                    // re-setting innerHTML on every chunk, which is what causes
                    // the page to crash on long chains-of-thought.
                    currentReasoningEl.innerHTML = `
                        <div class="thinking-header" onclick="this.parentElement.classList.toggle('expanded')">
                            <i class="fas fa-lightbulb text-amber-400 flex-shrink-0"></i>
                            <span class="thinking-summary">${t('thinking_in_progress')}</span>
                            <i class="fas fa-chevron-right thinking-chevron"></i>
                        </div>
                        <div class="thinking-full"><pre class="thinking-stream-pre"></pre></div>`;
                    stepsEl.appendChild(currentReasoningEl);
                    const preEl = currentReasoningEl.querySelector('.thinking-stream-pre');
                    preEl.appendChild(document.createTextNode(''));
                    currentReasoningEl._streamTextNode = preEl.firstChild;
                    currentReasoningEl._streamPendingText = '';
                    currentReasoningEl._streamRafScheduled = false;
                    currentReasoningEl._streamCharsRendered = 0;
                    currentReasoningEl._streamCapped = false;
                }
                // Hard cap: once REASONING_RENDER_CAP chars are in the DOM, stop
                // appending further deltas. The full text is still kept in
                // `reasoningText` for finalize-time head+tail rendering.
                if (!currentReasoningEl._streamCapped) {
                    currentReasoningEl._streamPendingText += item.content;
                    if (!currentReasoningEl._streamRafScheduled) {
                        currentReasoningEl._streamRafScheduled = true;
                        const elRef = currentReasoningEl;
                        requestAnimationFrame(() => {
                            elRef._streamRafScheduled = false;
                            if (!elRef.isConnected || !elRef._streamTextNode) return;
                            let pending = elRef._streamPendingText;
                            elRef._streamPendingText = '';
                            if (!pending) return;
                            const remaining = REASONING_RENDER_CAP - elRef._streamCharsRendered;
                            if (remaining <= 0) {
                                elRef._streamCapped = true;
                            } else {
                                if (pending.length > remaining) {
                                    pending = pending.slice(0, remaining);
                                    elRef._streamCapped = true;
                                }
                                elRef._streamTextNode.appendData(pending);
                                elRef._streamCharsRendered += pending.length;
                                if (elRef._streamCapped) {
                                    elRef._streamTextNode.appendData(
                                        '\n\n... [reasoning truncated for display] ...'
                                    );
                                }
                            }
                            scrollChatToBottom();
                        });
                    }
                }

            } else if (item.type === 'delta') {
                ensureBotEl();
                if (currentReasoningEl) {
                    finalizeThinking(currentReasoningEl, reasoningStartTime, reasoningText);
                    currentReasoningEl = null;
                    reasoningText = '';
                }
                accumulatedText += item.content;
                contentEl.innerHTML = renderMarkdown(accumulatedText);
                scrollChatToBottom();

            } else if (item.type === 'message_end') {
                if (item.has_tool_calls && accumulatedText.trim()) {
                    ensureBotEl();
                    const frozenEl = document.createElement('div');
                    frozenEl.className = 'agent-step agent-content-step';
                    frozenEl.innerHTML = `<div class="agent-content-body">${renderMarkdown(accumulatedText.trim())}</div>`;
                    stepsEl.appendChild(frozenEl);
                    accumulatedText = '';
                    contentEl.innerHTML = '';
                    scrollChatToBottom();
                }

            } else if (item.type === 'tool_start') {
                ensureBotEl();
                if (currentReasoningEl) {
                    finalizeThinking(currentReasoningEl, reasoningStartTime, reasoningText);
                    currentReasoningEl = null;
                    reasoningText = '';
                }
                accumulatedText = '';
                contentEl.innerHTML = '';

                // Add tool execution indicator (collapsible)
                currentToolEl = document.createElement('div');
                currentToolEl.className = 'agent-step agent-tool-step';
                const argsStr = formatToolArgs(item.arguments || {});
                currentToolEl.innerHTML = `
                    <div class="tool-header" onclick="this.parentElement.classList.toggle('expanded')">
                        <i class="fas fa-cog fa-spin text-primary-400 flex-shrink-0 tool-icon"></i>
                        <span class="tool-name">${item.tool}</span>
                        <i class="fas fa-chevron-right tool-chevron"></i>
                    </div>
                    <div class="tool-detail">
                        <div class="tool-detail-section">
                            <div class="tool-detail-label">Input</div>
                            <pre class="tool-detail-content">${argsStr}</pre>
                        </div>
                        <div class="tool-detail-section tool-output-section"></div>
                    </div>`;
                stepsEl.appendChild(currentToolEl);

                scrollChatToBottom();

            } else if (item.type === 'tool_end') {
                if (currentToolEl) {
                    const isError = item.status !== 'success';
                    const icon = currentToolEl.querySelector('.tool-icon');
                    icon.className = isError
                        ? 'fas fa-times text-red-400 flex-shrink-0 tool-icon'
                        : 'fas fa-check text-primary-400 flex-shrink-0 tool-icon';

                    // Show execution time
                    const nameEl = currentToolEl.querySelector('.tool-name');
                    if (item.execution_time !== undefined) {
                        nameEl.innerHTML += ` <span class="tool-time">${item.execution_time}s</span>`;
                    }

                    // Fill output section
                    const outputSection = currentToolEl.querySelector('.tool-output-section');
                    if (outputSection && item.result) {
                        outputSection.innerHTML = `
                            <div class="tool-detail-label">${isError ? 'Error' : 'Output'}</div>
                            <pre class="tool-detail-content ${isError ? 'tool-error-text' : ''}">${escapeHtml(String(item.result))}</pre>`;
                    }

                    if (isError) currentToolEl.classList.add('tool-failed');
                    currentToolEl = null;
                }

            } else if (item.type === 'image') {
                ensureBotEl();
                const imgEl = document.createElement('img');
                imgEl.src = item.content;
                imgEl.alt = 'screenshot';
                imgEl.style.cssText = 'max-width:600px;border-radius:8px;margin:8px 0;cursor:zoom-in;box-shadow:0 1px 4px rgba(0,0,0,0.1);';
                imgEl.onclick = () => _openImageLightbox(imgEl.src);
                mediaEl.appendChild(imgEl);
                scrollChatToBottom();

            } else if (item.type === 'text') {
                // Intermediate text sent before media items; display it but keep SSE open.
                ensureBotEl();
                contentEl.classList.remove('sse-streaming');
                const textContent = item.content || accumulatedText;
                if (textContent) contentEl.innerHTML = renderMarkdown(textContent);
                applyHighlighting(botEl);
                scrollChatToBottom();

            } else if (item.type === 'video') {
                ensureBotEl();
                const wrapper = document.createElement('div');
                wrapper.innerHTML = _buildVideoHtml(item.content);
                mediaEl.appendChild(wrapper.firstElementChild || wrapper);
                scrollChatToBottom();

            } else if (item.type === 'file') {
                ensureBotEl();
                const fileName = item.file_name || item.content.split('/').pop();
                const fileEl = document.createElement('a');
                fileEl.href = item.content;
                fileEl.download = fileName;
                fileEl.target = '_blank';
                fileEl.className = 'file-attachment';
                fileEl.style.cssText = 'display:inline-flex;align-items:center;gap:6px;padding:8px 14px;margin:8px 0;border-radius:8px;background:var(--bg-secondary,#f3f4f6);color:var(--text-primary,#374151);text-decoration:none;font-size:14px;border:1px solid var(--border-color,#e5e7eb);';
                fileEl.innerHTML = `<i class="fas fa-file-download" style="color:#6b7280;"></i> ${fileName}`;
                mediaEl.appendChild(fileEl);
                scrollChatToBottom();

            } else if (item.type === 'phase') {
                // Coarse progress (e.g. cow install-browser); must not close SSE (unlike "done")
                ensureBotEl();
                const wrap = document.createElement('div');
                wrap.className = 'text-xs sm:text-sm text-slate-600 dark:text-slate-400 border-l-2 border-primary-400 pl-2 py-1 my-0.5';
                wrap.textContent = String(item.content || '');
                stepsEl.appendChild(wrap);
                scrollChatToBottom();

            } else if (item.type === 'done') {
                done = true;
                es.close();
                delete activeStreams[requestId];

                // item.content may be empty when "done" is only a stream-close signal after media.
                const finalText = item.content || accumulatedText;

                if (!botEl && finalText) {
                    if (loadingEl) { loadingEl.remove(); loadingEl = null; }
                    addBotMessage(finalText, new Date((item.timestamp || Date.now() / 1000) * 1000), requestId);
                } else if (botEl) {
                    contentEl.classList.remove('sse-streaming');
                    if (finalText) contentEl.innerHTML = renderMarkdown(finalText);
                    contentEl.dataset.rawMd = finalText || '';
                    const copyBtn = botEl.querySelector('.copy-msg-btn');
                    if (copyBtn && finalText) copyBtn.style.display = '';
                    applyHighlighting(botEl);
                }
                scrollChatToBottom();

                if (titleInfo) {
                    generateSessionTitle(titleInfo.sid, titleInfo.userMsg, '');
                    titleInfo = null;
                } else if (sessionPanelOpen) {
                    loadSessionList();
                }

            } else if (item.type === 'error') {
                done = true;
                es.close();
                delete activeStreams[requestId];
                if (loadingEl) { loadingEl.remove(); loadingEl = null; }
                addBotMessage(t('error_send'), new Date());
            }
        };

        es.onerror = function() {
            es.close();
            delete activeStreams[requestId];

            if (done) return;

            if (currentReasoningEl) {
                finalizeThinking(currentReasoningEl, reasoningStartTime, reasoningText);
                currentReasoningEl = null;
                reasoningText = '';
            }

            if (reconnectCount < MAX_RECONNECTS) {
                reconnectCount++;
                const delay = Math.min(RECONNECT_BASE_MS * reconnectCount, 5000);
                console.warn(`[SSE] connection lost for ${requestId}, reconnecting in ${delay}ms (attempt ${reconnectCount}/${MAX_RECONNECTS})`);
                setTimeout(connect, delay);
                return;
            }

            // Exhausted retries, show whatever we have
            if (loadingEl) { loadingEl.remove(); loadingEl = null; }
            if (!botEl) {
                addBotMessage(t('error_send'), new Date());
            } else if (accumulatedText) {
                contentEl.classList.remove('sse-streaming');
                contentEl.innerHTML = renderMarkdown(accumulatedText);
                applyHighlighting(botEl);
                bindChatKnowledgeLinks(botEl);
            }
        };
    }

    connect();
}

function startPolling() {
    const gen = ++pollGeneration;
    isPolling = true;
    let pollInFlight = false;

    function poll() {
        if (gen !== pollGeneration) return;
        if (pollInFlight) return;
        if (document.hidden) { setTimeout(poll, 10000); return; }

        pollInFlight = true;
        fetch('/poll', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        })
        .then(r => r.json())
        .then(data => {
            pollInFlight = false;
            if (gen !== pollGeneration) return;
            if (data.status === 'success' && data.has_content) {
                const rid = data.request_id;
                if (loadingContainers[rid]) {
                    loadingContainers[rid].remove();
                    delete loadingContainers[rid];
                }
                const welcomeScreen = document.getElementById('welcome-screen');
                if (welcomeScreen) welcomeScreen.remove();
                addBotMessage(data.content, new Date(data.timestamp * 1000), rid);
                scrollChatToBottom();
            }
            const delay = (data.status === 'success' && data.has_content) ? 5000 : 10000;
            setTimeout(poll, delay);
        })
        .catch(() => { pollInFlight = false; setTimeout(poll, 10000); });
    }
    poll();
}

function createUserMessageEl(content, timestamp, attachments) {
    const el = document.createElement('div');
    el.className = 'flex justify-end px-4 sm:px-6 py-3';

    let attachHtml = '';
    if (attachments && attachments.length > 0) {
        const items = attachments.map(a => {
            if (a.file_type === 'image') {
                return `<img src="${a.preview_url}" alt="${escapeHtml(a.file_name)}" class="user-msg-image">`;
            }
            const icon = a.file_type === 'video'
                ? 'fa-film'
                : (a.file_type === 'directory' ? 'fa-folder-tree' : 'fa-file-alt');
            const suffix = a.file_type === 'directory' && a.file_count
                ? ` (${a.file_count})`
                : '';
            return `<div class="user-msg-file"><i class="fas ${icon}"></i> ${escapeHtml(a.file_name)}${suffix}</div>`;
        }).join('');
        attachHtml = `<div class="user-msg-attachments">${items}</div>`;
    }

    const textHtml = content ? renderMarkdown(content) : '';
    el.innerHTML = `
        <div class="max-w-[75%] sm:max-w-[60%]">
            <div class="bg-primary-400 text-white rounded-2xl px-4 py-2.5 text-sm leading-relaxed msg-content user-bubble">
                ${attachHtml}${textHtml}
            </div>
            <div class="text-xs text-slate-400 dark:text-slate-500 mt-1.5 text-right">${formatTime(timestamp)}</div>
        </div>
    `;
    return el;
}

function renderToolCallsHtml(toolCalls) {
    if (!toolCalls || toolCalls.length === 0) return '';
    return toolCalls.map(tc => {
        const argsStr = formatToolArgs(tc.arguments || {});
        const resultStr = tc.result ? escapeHtml(String(tc.result)) : '';
        const hasResult = !!resultStr;
        return `
<div class="agent-step agent-tool-step">
    <div class="tool-header" onclick="this.parentElement.classList.toggle('expanded')">
        <i class="fas fa-check text-primary-400 flex-shrink-0 tool-icon"></i>
        <span class="tool-name">${escapeHtml(tc.name || '')}</span>
        <i class="fas fa-chevron-right tool-chevron"></i>
    </div>
    <div class="tool-detail">
        <div class="tool-detail-section">
            <div class="tool-detail-label">Input</div>
            <pre class="tool-detail-content">${argsStr}</pre>
        </div>
        ${hasResult ? `
        <div class="tool-detail-section tool-output-section">
            <div class="tool-detail-label">Output</div>
            <pre class="tool-detail-content">${resultStr}</pre>
        </div>` : ''}
    </div>
</div>`;
    }).join('');
}

// Cap for rendering reasoning content in the bubble. Beyond this size,
// we skip markdown rendering entirely and show plain text head + tail to
// keep the page responsive (very long chains-of-thought can otherwise
// stall or crash the browser when re-parsed by marked.js).
// Keep this in sync with backend MAX_STORED_REASONING_CHARS and
// MAX_REASONING_STREAM_CHARS so storage / SSE / display stay aligned.
const REASONING_RENDER_CAP = 4 * 1024; // 4 KB

function _truncateReasoningForDisplay(text) {
    if (!text || text.length <= REASONING_RENDER_CAP) return { text, truncated: false, omitted: 0 };
    const half = Math.floor(REASONING_RENDER_CAP / 2);
    const head = text.slice(0, half);
    const tail = text.slice(-half);
    return {
        text: head + '\n\n... [' + (text.length - head.length - tail.length) + ' chars omitted] ...\n\n' + tail,
        truncated: true,
        omitted: text.length - head.length - tail.length,
    };
}

function _renderReasoningBody(text) {
    // For short reasoning, render as markdown. For long ones, fall back to
    // an escaped <pre> block to avoid expensive markdown parsing.
    const { text: shown, truncated } = _truncateReasoningForDisplay(text);
    if (truncated || shown.length > REASONING_RENDER_CAP) {
        return '<pre class="thinking-stream-pre">' + escapeHtml(shown) + '</pre>';
    }
    return renderMarkdown(shown);
}

function finalizeThinking(el, startTime, text) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    el.querySelector('.thinking-summary').textContent = t('thinking_done');
    const fullDiv = el.querySelector('.thinking-full');
    fullDiv.innerHTML = `<div class="thinking-duration">${t('thinking_duration')} ${elapsed}s</div>` + _renderReasoningBody(text);
}

function renderThinkingHtml(text) {
    if (!text || !text.trim()) return '';
    const full = text.trim();
    return `
<div class="agent-step agent-thinking-step">
    <div class="thinking-header" onclick="this.parentElement.classList.toggle('expanded')">
        <i class="fas fa-lightbulb text-amber-400 flex-shrink-0"></i>
        <span class="thinking-summary">${t('thinking_done')}</span>
        <i class="fas fa-chevron-right thinking-chevron"></i>
    </div>
    <div class="thinking-full">${_renderReasoningBody(full)}</div>
</div>`;
}

function renderStepsHtml(steps) {
    if (!steps || steps.length === 0) return { stepsHtml: '', finalContent: '' };

    // Find the index of the last content step — it becomes the main answer, not a step
    let lastContentIdx = -1;
    for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].type === 'content') { lastContentIdx = i; break; }
    }

    let html = '';
    let lastContentText = '';
    for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        if (step.type === 'thinking') {
            html += renderThinkingHtml(step.content);
        } else if (step.type === 'content') {
            if (i === lastContentIdx) {
                lastContentText = step.content;
            } else {
                html += `<div class="agent-step agent-content-step"><div class="agent-content-body">${renderMarkdown(step.content)}</div></div>`;
            }
        } else if (step.type === 'tool') {
            const argsStr = formatToolArgs(step.arguments || {});
            const resultStr = step.result ? escapeHtml(String(step.result)) : '';
            const isErr = step.is_error === true;
            const iconClass = isErr
                ? 'fas fa-times text-red-400 flex-shrink-0 tool-icon'
                : 'fas fa-check text-primary-400 flex-shrink-0 tool-icon';
            html += `
<div class="agent-step agent-tool-step${isErr ? ' tool-failed' : ''}">
    <div class="tool-header" onclick="this.parentElement.classList.toggle('expanded')">
        <i class="${iconClass}"></i>
        <span class="tool-name">${escapeHtml(step.name || '')}</span>
        <i class="fas fa-chevron-right tool-chevron"></i>
    </div>
    <div class="tool-detail">
        <div class="tool-detail-section">
            <div class="tool-detail-label">Input</div>
            <pre class="tool-detail-content">${argsStr}</pre>
        </div>
        ${resultStr ? `
        <div class="tool-detail-section tool-output-section">
            <div class="tool-detail-label">${isErr ? 'Error' : 'Output'}</div>
            <pre class="tool-detail-content${isErr ? ' tool-error-text' : ''}">${resultStr}</pre>
        </div>` : ''}
    </div>
</div>`;
            // If this tool sent a file (send/read tool), render the media inline
            // so it persists across page refreshes (SSE-only file events are not stored).
            const mediaHtml = _renderSentFileFromToolResult(step);
            if (mediaHtml) html += mediaHtml;
        }
    }
    return { stepsHtml: html, lastContentText };
}

// Extract file-to-send metadata from a tool's result and render an inline preview.
// Returns '' if the result isn't a file_to_send payload.
function _renderSentFileFromToolResult(step) {
    if (!step || !step.result) return '';
    let payload;
    try {
        payload = typeof step.result === 'string' ? JSON.parse(step.result) : step.result;
    } catch (_) { return ''; }
    if (!payload || payload.type !== 'file_to_send' || !payload.path) return '';
    const webUrl = _toWebUrl(payload.path);
    const fileType = payload.file_type || 'file';
    const fileName = payload.file_name || payload.path.split('/').pop();
    if (fileType === 'image') {
        return `<div class="agent-step">${_buildImageHtml(webUrl)}</div>`;
    }
    if (fileType === 'video') {
        return `<div class="agent-step">${_buildVideoHtml(webUrl)}</div>`;
    }
    return `<div class="agent-step"><a href="${webUrl}" download="${escapeHtml(fileName)}" target="_blank" ` +
        `style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;margin:8px 0;border-radius:8px;` +
        `background:var(--bg-secondary,#f3f4f6);color:var(--text-primary,#374151);text-decoration:none;font-size:14px;` +
        `border:1px solid var(--border-color,#e5e7eb);">` +
        `<i class="fas fa-file-download" style="color:#6b7280;"></i> ${escapeHtml(fileName)}</a></div>`;
}

function createBotMessageEl(content, timestamp, requestId, msg) {
    const el = document.createElement('div');
    el.className = 'flex gap-3 px-4 sm:px-6 py-3';
    if (requestId) el.dataset.requestId = requestId;

    let stepsHtml = '';
    let displayContent = content;

    if (msg && msg.steps && msg.steps.length > 0) {
        // New format: ordered steps with interleaved content
        const result = renderStepsHtml(msg.steps);
        stepsHtml = result.stepsHtml;
        // The final content (last text after all steps) is the main answer
        displayContent = content || result.lastContentText;
    } else {
        // Legacy format: separate tool_calls + optional reasoning
        const toolCalls = msg && msg.tool_calls;
        const reasoning = msg && msg.reasoning;
        stepsHtml = renderThinkingHtml(reasoning) + renderToolCallsHtml(toolCalls);
    }

    el.innerHTML = `
        <img src="assets/logo.jpg" alt="智能投研辅助系统" class="w-8 h-8 rounded-lg flex-shrink-0">
        <div class="min-w-0 flex-1 max-w-[85%]">
            <div class="bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-2xl px-4 py-3 text-sm leading-relaxed msg-content text-slate-700 dark:text-slate-200">
                ${stepsHtml ? `<div class="agent-steps">${stepsHtml}</div>` : ''}
                <div class="answer-content">${renderMarkdown(displayContent)}</div>
            </div>
            <div class="flex items-center gap-2 mt-1.5">
                <span class="text-xs text-slate-400 dark:text-slate-500">${formatTime(timestamp)}</span>
                <button class="copy-msg-btn text-xs text-slate-300 dark:text-slate-600 hover:text-slate-500 dark:hover:text-slate-400 transition-colors cursor-pointer" title="${currentLang === 'zh' ? '复制' : 'Copy'}">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
        </div>
    `;
    el.querySelector('.answer-content').dataset.rawMd = displayContent;
    applyHighlighting(el);
    bindChatKnowledgeLinks(el);
    return el;
}

function addUserMessage(content, timestamp, attachments) {
    const el = createUserMessageEl(content, timestamp, attachments);
    messagesDiv.appendChild(el);
    _autoScrollEnabled = true;
    scrollChatToBottom(true);
}

function addBotMessage(content, timestamp, requestId) {
    const el = createBotMessageEl(content, timestamp, requestId);
    messagesDiv.appendChild(el);
    scrollChatToBottom();
}

// Load conversation history from the server (page 1 = most recent messages).
// Subsequent pages prepend older messages when the user scrolls to the top.
function loadHistory(page) {
    if (historyLoading) return;
    historyLoading = true;

    fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}&page=${page}&page_size=20`)
        .then(r => r.json())
        .then(data => {
            if (data.status !== 'success' || data.messages.length === 0) return;

            const prevScrollHeight = messagesDiv.scrollHeight;
            const isFirstLoad = page === 1;

            // On first load, remove the welcome screen if history exists
            if (isFirstLoad) {
                const ws = document.getElementById('welcome-screen');
                if (ws) ws.remove();
            }

            // Build a fragment of history message elements in chronological order
            const fragment = document.createDocumentFragment();

            if (data.has_more && page > 1) {
                // Keep the "load more" sentinel in place (inserted below)
            }

            const ctxStartSeq = data.context_start_seq || 0;
            let dividerInserted = false;

            data.messages.forEach(msg => {
                const hasContent = msg.content && msg.content.trim();
                const hasToolCalls = msg.role === 'assistant' && msg.tool_calls && msg.tool_calls.length > 0;
                if (!hasContent && !hasToolCalls) return;

                // Insert context divider when transitioning from above to below boundary
                if (ctxStartSeq > 0 && !dividerInserted && msg._seq !== undefined && msg._seq >= ctxStartSeq) {
                    dividerInserted = true;
                    const divider = document.createElement('div');
                    divider.className = 'context-divider';
                    divider.innerHTML = `<span>${t('context_cleared')}</span>`;
                    fragment.appendChild(divider);
                }

                const ts = new Date(msg.created_at * 1000);
                const el = msg.role === 'user'
                    ? createUserMessageEl(msg.content, ts)
                    : createBotMessageEl(msg.content || '', ts, null, msg);
                fragment.appendChild(el);
            });

            // If context was cleared but no new messages exist yet, append divider at the end
            if (ctxStartSeq > 0 && !dividerInserted) {
                const divider = document.createElement('div');
                divider.className = 'context-divider';
                divider.innerHTML = `<span>${t('context_cleared')}</span>`;
                fragment.appendChild(divider);
            }

            // Prepend history above any existing messages
            const sentinel = document.getElementById('history-load-more');
            const insertBefore = sentinel ? sentinel.nextSibling : messagesDiv.firstChild;
            messagesDiv.insertBefore(fragment, insertBefore);

            // Manage the "load more" sentinel at the very top
            if (data.has_more) {
                if (!document.getElementById('history-load-more')) {
                    const btn = document.createElement('div');
                    btn.id = 'history-load-more';
                    btn.className = 'flex justify-center py-3';
                    btn.innerHTML = `<button class="text-xs text-slate-400 dark:text-slate-500 hover:text-primary-400 transition-colors" onclick="loadHistory(historyPage + 1)">Load earlier messages</button>`;
                    messagesDiv.insertBefore(btn, messagesDiv.firstChild);
                }
            } else {
                const sentinel = document.getElementById('history-load-more');
                if (sentinel) sentinel.remove();
            }

            historyHasMore = data.has_more;
            historyPage = page;

            if (isFirstLoad) {
                // Use requestAnimationFrame to ensure the DOM has fully rendered
                // before scrolling, otherwise scrollHeight may not reflect new content.
                requestAnimationFrame(() => scrollChatToBottom(true));
            } else {
                // Restore scroll position so loading older messages doesn't jump the view
                messagesDiv.scrollTop = messagesDiv.scrollHeight - prevScrollHeight;
            }
        })
        .catch(() => {})
        .finally(() => { historyLoading = false; });
}

function addLoadingIndicator() {
    const el = document.createElement('div');
    el.className = 'flex gap-3 px-4 sm:px-6 py-3';
    el.innerHTML = `
        <img src="assets/logo.jpg" alt="智能投研辅助系统" class="w-8 h-8 rounded-lg flex-shrink-0">
        <div class="bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-2xl px-4 py-3">
            <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-primary-400 animate-pulse-dot" style="animation-delay: 0s"></span>
                <span class="w-2 h-2 rounded-full bg-primary-400 animate-pulse-dot" style="animation-delay: 0.2s"></span>
                <span class="w-2 h-2 rounded-full bg-primary-400 animate-pulse-dot" style="animation-delay: 0.4s"></span>
            </div>
        </div>
    `;
    messagesDiv.appendChild(el);
    scrollChatToBottom();
    return el;
}

function newChat() {
    // Close all active SSE connections for the current session
    Object.values(activeStreams).forEach(es => { try { es.close(); } catch (_) {} });
    activeStreams = {};

    // Generate a fresh session and persist it so the next page load also starts clean
    sessionId = generateSessionId();
    localStorage.setItem(SESSION_ID_KEY, sessionId);
    loadingContainers = {};
    startPolling();  // bump generation so old loop self-cancels, new loop uses fresh sessionId
    messagesDiv.innerHTML = '';
    const ws = document.createElement('div');
    ws.id = 'welcome-screen';
    ws.className = 'flex flex-col items-center justify-center h-full px-6 pb-16';
    ws.style.paddingTop = '6vh';
    ws.innerHTML = `
        <img src="assets/logo.jpg" alt="智能投研辅助系统" class="w-16 h-16 rounded-2xl mb-6 shadow-lg shadow-primary-500/20">
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-3">${appConfig.title || '智能投研辅助系统'}</h1>
        <p class="text-slate-500 dark:text-slate-400 text-center max-w-lg mb-10 leading-relaxed" data-i18n="welcome_subtitle">${t('welcome_subtitle')}</p>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full max-w-2xl">
            <div class="example-card group bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-xl p-4 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all duration-200">
                <div class="flex items-center gap-2 mb-2">
                    <div class="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center">
                        <i class="fas fa-folder-open text-blue-500 text-xs"></i>
                    </div>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200" data-i18n="example_sys_title">${t('example_sys_title')}</span>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed" data-i18n="example_sys_text">${t('example_sys_text')}</p>
            </div>
            <div class="example-card group bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-xl p-4 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all duration-200">
                <div class="flex items-center gap-2 mb-2">
                    <div class="w-7 h-7 rounded-lg bg-amber-50 dark:bg-amber-900/30 flex items-center justify-center">
                        <i class="fas fa-clock text-amber-500 text-xs"></i>
                    </div>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200" data-i18n="example_task_title">${t('example_task_title')}</span>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed" data-i18n="example_task_text">${t('example_task_text')}</p>
            </div>
            <div class="example-card group bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-xl p-4 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all duration-200">
                <div class="flex items-center gap-2 mb-2">
                    <div class="w-7 h-7 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center">
                        <i class="fas fa-code text-emerald-500 text-xs"></i>
                    </div>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200" data-i18n="example_code_title">${t('example_code_title')}</span>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed" data-i18n="example_code_text">${t('example_code_text')}</p>
            </div>
            <div class="example-card group bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-xl p-4 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all duration-200">
                <div class="flex items-center gap-2 mb-2">
                    <div class="w-7 h-7 rounded-lg bg-violet-50 dark:bg-violet-900/30 flex items-center justify-center">
                        <i class="fas fa-book text-violet-500 text-xs"></i>
                    </div>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200" data-i18n="example_knowledge_title">${t('example_knowledge_title')}</span>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed" data-i18n="example_knowledge_text">${t('example_knowledge_text')}</p>
            </div>
            <div class="example-card group bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-xl p-4 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all duration-200">
                <div class="flex items-center gap-2 mb-2">
                    <div class="w-7 h-7 rounded-lg bg-rose-50 dark:bg-rose-900/30 flex items-center justify-center">
                        <i class="fas fa-puzzle-piece text-rose-500 text-xs"></i>
                    </div>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200" data-i18n="example_skill_title">${t('example_skill_title')}</span>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed" data-i18n="example_skill_text">${t('example_skill_text')}</p>
            </div>
            <div class="example-card group bg-white dark:bg-[#1A1A1A] border border-slate-200 dark:border-white/10 rounded-xl p-4 cursor-pointer hover:border-primary-300 dark:hover:border-primary-600 hover:shadow-md transition-all duration-200" data-send="/help">
                <div class="flex items-center gap-2 mb-2">
                    <div class="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                        <i class="fas fa-terminal text-slate-500 text-xs"></i>
                    </div>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200" data-i18n="example_web_title">${t('example_web_title')}</span>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed" data-i18n="example_web_text">${t('example_web_text')}</p>
            </div>
        </div>
    `;
    messagesDiv.appendChild(ws);
    ws.querySelectorAll('.example-card').forEach(card => {
        card.addEventListener('click', () => {
            const sendText = card.dataset.send;
            if (sendText) {
                chatInput.value = sendText;
                chatInput.dispatchEvent(new Event('input'));
                chatInput.focus();
                return;
            }
            const textEl = card.querySelector('[data-i18n*="text"]');
            if (textEl) {
                chatInput.value = textEl.textContent;
                chatInput.dispatchEvent(new Event('input'));
                chatInput.focus();
            }
        });
    });
    if (currentView !== 'chat') navigateTo('chat');

    // Show panel and load full session list, then prepend the new session on top
    const panel = document.getElementById('session-panel');
    if (panel && !sessionPanelOpen) {
        sessionPanelOpen = true;
        panel.classList.remove('hidden');
        _showSessionOverlay();
        _persistPanelState();
    }
    const newSid = sessionId;
    loadSessionList(() => _addOptimisticSessionItem(newSid));
}

// =====================================================================
// Session Panel
// =====================================================================

const SESSION_PANEL_KEY = 'cow_session_panel_open';
let sessionPanelOpen = localStorage.getItem(SESSION_PANEL_KEY) === '1';

function _persistPanelState() {
    localStorage.setItem(SESSION_PANEL_KEY, sessionPanelOpen ? '1' : '0');
}

function _isMobileView() {
    return window.innerWidth <= 768;
}

function _showSessionOverlay() {
    if (!_isMobileView()) return;
    const overlay = document.getElementById('session-panel-overlay');
    if (overlay) overlay.classList.remove('hidden');
}

function _hideSessionOverlay() {
    const overlay = document.getElementById('session-panel-overlay');
    if (overlay) overlay.classList.add('hidden');
}

function closeSessionPanel() {
    const panel = document.getElementById('session-panel');
    if (!panel || !sessionPanelOpen) return;
    sessionPanelOpen = false;
    panel.classList.add('hidden');
    _hideSessionOverlay();
    _persistPanelState();
}

function toggleSessionPanel() {
    const panel = document.getElementById('session-panel');
    if (!panel) return;
    sessionPanelOpen = !sessionPanelOpen;
    panel.classList.toggle('hidden', !sessionPanelOpen);
    if (sessionPanelOpen) {
        _showSessionOverlay();
    } else {
        _hideSessionOverlay();
    }
    _persistPanelState();
    if (sessionPanelOpen) loadSessionList();
}

function openSessionPanel() {
    const panel = document.getElementById('session-panel');
    if (!panel || sessionPanelOpen) return;
    sessionPanelOpen = true;
    panel.classList.remove('hidden');
    _showSessionOverlay();
    _persistPanelState();
    loadSessionList();
}

function _restoreSessionPanel() {
    const panel = document.getElementById('session-panel');
    if (!panel) return;
    if (sessionPanelOpen && !_isMobileView()) {
        panel.classList.remove('hidden');
        _showSessionOverlay();
        loadSessionList();
    } else {
        panel.classList.add('hidden');
        _hideSessionOverlay();
    }
}

function _applyInputTooltips() {
    const set = (id, key, pos) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.setAttribute('data-tooltip', t(key));
        el.removeAttribute('title');
        if (pos) el.setAttribute('data-tooltip-pos', pos);
    };
    set('new-chat-btn', 'tip_new_chat');
    set('clear-context-btn', 'tip_clear_context');
    set('attach-btn', 'tip_attach');
    set('session-toggle-btn', 'session_history', 'bottom');
}

function _addOptimisticSessionItem(sid) {
    const container = document.getElementById('session-list');
    if (!container) return;

    const emptyEl = container.querySelector('.session-empty');
    if (emptyEl) emptyEl.remove();

    document.querySelectorAll('.session-item.active').forEach(el => el.classList.remove('active'));

    const todayLabel = t('today');
    let firstGroup = container.querySelector('.session-group-label');
    if (!firstGroup || firstGroup.textContent !== todayLabel) {
        const header = document.createElement('div');
        header.className = 'session-group-label';
        header.textContent = todayLabel;
        container.prepend(header);
        firstGroup = header;
    }

    const title = t('new_chat');
    const item = document.createElement('div');
    item.className = 'session-item active';
    item.dataset.sessionId = sid;
    item.innerHTML = `
        <i class="fas fa-message session-icon"></i>
        <span class="session-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
        <button class="session-delete" onclick="event.stopPropagation(); deleteSession('${sid}')" title="Delete">
            <i class="fas fa-trash-can"></i>
        </button>
    `;
    item.addEventListener('click', () => switchSession(sid));
    firstGroup.insertAdjacentElement('afterend', item);
}

function _sessionTimeGroup(ts) {
    const now = new Date();
    const d = new Date(ts * 1000);
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
    if (d >= today) return t('today');
    if (d >= yesterday) return t('yesterday');
    return t('earlier');
}

let _sessionPage = 1;
let _sessionHasMore = false;
let _sessionLoading = false;
const _SESSION_PAGE_SIZE = 50;

function loadSessionList(onDone) {
    const container = document.getElementById('session-list');
    if (!container) return;

    _sessionPage = 1;
    _sessionHasMore = false;

    _fetchSessionPage(1, true, onDone);
}

function _fetchSessionPage(page, clear, onDone) {
    if (_sessionLoading) return;
    _sessionLoading = true;

    const container = document.getElementById('session-list');
    if (!container) { _sessionLoading = false; return; }

    // Remove existing "load more" sentinel before fetching
    const oldSentinel = container.querySelector('.session-load-more');
    if (oldSentinel) oldSentinel.remove();

    fetch(`/api/sessions?page=${page}&page_size=${_SESSION_PAGE_SIZE}`)
        .then(r => r.json())
        .then(data => {
            _sessionLoading = false;
            if (data.status !== 'success') return;

            if (clear) container.innerHTML = '';

            const sessions = data.sessions || [];
            _sessionPage = page;
            _sessionHasMore = !!data.has_more;

            if (sessions.length === 0 && page === 1) {
                container.innerHTML = '<div class="session-empty">' + t('untitled_session') + '</div>';
                if (typeof onDone === 'function') onDone();
                return;
            }

            // Track last group label already in the container
            const existingLabels = container.querySelectorAll('.session-group-label');
            let lastGroup = existingLabels.length > 0
                ? existingLabels[existingLabels.length - 1].textContent
                : '';

            sessions.forEach(s => {
                const group = _sessionTimeGroup(s.last_active);
                if (group !== lastGroup) {
                    lastGroup = group;
                    const header = document.createElement('div');
                    header.className = 'session-group-label';
                    header.textContent = group;
                    container.appendChild(header);
                }

                const item = document.createElement('div');
                const isActive = s.session_id === sessionId;
                item.className = 'session-item' + (isActive ? ' active' : '');
                item.dataset.sessionId = s.session_id;

                const title = s.title || t('untitled_session');
                item.innerHTML = `
                    <i class="fas fa-message session-icon"></i>
                    <span class="session-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
                    <button class="session-delete" onclick="event.stopPropagation(); deleteSession('${s.session_id}')" title="Delete">
                        <i class="fas fa-trash-can"></i>
                    </button>
                `;
                item.addEventListener('click', () => switchSession(s.session_id));
                container.appendChild(item);
            });

            if (typeof onDone === 'function') onDone();
        })
        .catch(() => { _sessionLoading = false; });
}

function _onSessionListScroll() {
    if (!_sessionHasMore || _sessionLoading) return;
    const container = document.getElementById('session-list');
    if (!container) return;
    // Trigger when scrolled near the bottom (within 60px)
    if (container.scrollHeight - container.scrollTop - container.clientHeight < 60) {
        _fetchSessionPage(_sessionPage + 1, false);
    }
}

// Attach scroll listener once DOM is ready
(function _initSessionScroll() {
    const el = document.getElementById('session-list');
    if (el) {
        el.addEventListener('scroll', _onSessionListScroll);
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            const el2 = document.getElementById('session-list');
            if (el2) el2.addEventListener('scroll', _onSessionListScroll);
        });
    }
})();

function switchSession(newSessionId) {
    if (newSessionId === sessionId) {
        if (currentView !== 'chat') navigateTo('chat');
        return;
    }

    Object.values(activeStreams).forEach(es => { try { es.close(); } catch (_) {} });
    activeStreams = {};
    loadingContainers = {};

    sessionId = newSessionId;
    localStorage.setItem(SESSION_ID_KEY, sessionId);

    historyPage = 0;
    historyHasMore = false;
    historyLoading = false;

    messagesDiv.innerHTML = '';
    loadHistory(1);
    startPolling();

    document.querySelectorAll('.session-item').forEach(el => {
        el.classList.toggle('active', el.dataset.sessionId === sessionId);
    });

    if (_isMobileView()) closeSessionPanel();
    if (currentView !== 'chat') navigateTo('chat');
}

function deleteSession(sid) {
    showConfirmModal(t('delete_session_title'), t('delete_session_confirm'), () => {
        fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' })
            .then(r => r.json())
            .then(data => {
                if (data.status !== 'success') return;
                if (sid === sessionId) {
                    newChat();
                } else {
                    loadSessionList();
                }
            })
            .catch(() => {});
    });
}

function showConfirmModal(title, message, onConfirm) {
    let overlay = document.getElementById('confirm-modal-overlay');
    if (overlay) overlay.remove();

    overlay = document.createElement('div');
    overlay.id = 'confirm-modal-overlay';
    overlay.className = 'confirm-overlay';

    const modal = document.createElement('div');
    modal.className = 'confirm-modal';
    modal.innerHTML = `
        <div class="confirm-title">${escapeHtml(title)}</div>
        <div class="confirm-message">${escapeHtml(message)}</div>
        <div class="confirm-actions">
            <button class="confirm-btn confirm-btn-cancel">${t('confirm_cancel')}</button>
            <button class="confirm-btn confirm-btn-ok">${t('confirm_yes')}</button>
        </div>
    `;
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => overlay.classList.add('visible'));

    const close = () => {
        overlay.classList.remove('visible');
        setTimeout(() => overlay.remove(), 200);
    };

    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    modal.querySelector('.confirm-btn-cancel').addEventListener('click', close);
    modal.querySelector('.confirm-btn-ok').addEventListener('click', () => {
        close();
        onConfirm();
    });
}

function clearContext() {
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}/clear_context`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status !== 'success') return;
            // Insert a visual divider in the chat
            const divider = document.createElement('div');
            divider.className = 'context-divider';
            divider.innerHTML = `<span>${t('context_cleared')}</span>`;
            messagesDiv.appendChild(divider);
            scrollChatToBottom();
        })
        .catch(() => {});
}

function generateSessionTitle(sid, userMsg, assistantReply) {
    fetch(`/api/sessions/${encodeURIComponent(sid)}/generate_title`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_message: userMsg, assistant_reply: assistantReply }),
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success' && sessionPanelOpen) {
                loadSessionList();
            }
        })
        .catch(() => {});
}

// =====================================================================
// Utilities
// =====================================================================
function formatTime(date) {
    const now = new Date();
    const sameDay = date.getFullYear() === now.getFullYear()
        && date.getMonth() === now.getMonth()
        && date.getDate() === now.getDate();
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (sameDay) return time;
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    if (date.getFullYear() === now.getFullYear()) return `${m}-${d} ${time}`;
    return `${date.getFullYear()}-${m}-${d} ${time}`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function ChannelsHandler_maskSecret(val) {
    if (!val || val.length <= 8) return val;
    return val.slice(0, 4) + '*'.repeat(val.length - 8) + val.slice(-4);
}

function formatToolArgs(args) {
    if (!args || Object.keys(args).length === 0) return '(none)';
    try {
        return escapeHtml(JSON.stringify(args, null, 2));
    } catch (_) {
        return escapeHtml(String(args));
    }
}

function scrollChatToBottom(force) {
    if (force || _autoScrollEnabled) {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
}

function _updateScrollToBottomBtn() {
    const btn = document.getElementById('scroll-to-bottom-btn');
    if (!btn) return;
    const distFromBottom = messagesDiv.scrollHeight - messagesDiv.scrollTop - messagesDiv.clientHeight;
    btn.classList.toggle('hidden', distFromBottom <= _SCROLL_THRESHOLD);
}

function applyHighlighting(container) {
    const root = container || document;
    setTimeout(() => {
        const hljsLib = getHljs();
        root.querySelectorAll('pre code').forEach(block => {
            if (!block.classList.contains('hljs')) {
                hljsLib.highlightElement(block);
            }
        });
    }, 0);
}

// =====================================================================
// Config View
// =====================================================================
let configProviders = {};
let configApiBases = {};
let configApiKeys = {};
let configCurrentModel = '';
let cfgProviderValue = '';
let cfgModelValue = '';

// --- Custom dropdown helper ---
function initDropdown(el, options, selectedValue, onChange) {
    const textEl = el.querySelector('.cfg-dropdown-text');
    const menuEl = el.querySelector('.cfg-dropdown-menu');
    const selEl = el.querySelector('.cfg-dropdown-selected');

    el._ddValue = selectedValue || '';
    el._ddOnChange = onChange;

    function render() {
        menuEl.innerHTML = '';
        options.forEach(opt => {
            const item = document.createElement('div');
            item.className = 'cfg-dropdown-item' + (opt.value === el._ddValue ? ' active' : '');
            item.textContent = opt.label;
            item.dataset.value = opt.value;
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                el._ddValue = opt.value;
                textEl.textContent = opt.label;
                menuEl.querySelectorAll('.cfg-dropdown-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                el.classList.remove('open');
                if (el._ddOnChange) el._ddOnChange(opt.value);
            });
            menuEl.appendChild(item);
        });
        const sel = options.find(o => o.value === el._ddValue);
        textEl.textContent = sel ? sel.label : (options[0] ? options[0].label : '--');
        if (!sel && options[0]) el._ddValue = options[0].value;
    }

    render();

    if (!el._ddBound) {
        selEl.addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.cfg-dropdown.open').forEach(d => { if (d !== el) d.classList.remove('open'); });
            el.classList.toggle('open');
        });
        el._ddBound = true;
    }
}

document.addEventListener('click', () => {
    document.querySelectorAll('.cfg-dropdown.open').forEach(d => d.classList.remove('open'));
});

function getDropdownValue(el) { return el._ddValue || ''; }

// --- Config init ---
function initConfigView(data) {
    configProviders = data.providers || {};
    configApiBases = data.api_bases || {};
    configApiKeys = data.api_keys || {};
    configCurrentModel = data.model || '';

    const providerEl = document.getElementById('cfg-provider');
    const providerOpts = Object.entries(configProviders).map(([pid, p]) => ({ value: pid, label: p.label }));

    // if use_linkai is enabled, always select linkai as the provider
    // Otherwise prefer bot_type from config, fall back to model-based detection
    const detected = data.use_linkai ? 'linkai'
        : (data.bot_type && configProviders[data.bot_type] ? data.bot_type : detectProvider(configCurrentModel));
    cfgProviderValue = detected || (providerOpts[0] ? providerOpts[0].value : '');

    initDropdown(providerEl, providerOpts, cfgProviderValue, onProviderChange);

    onProviderChange(cfgProviderValue);
    syncModelSelection(configCurrentModel);

    document.getElementById('cfg-max-tokens').value = data.agent_max_context_tokens || 50000;
    document.getElementById('cfg-max-turns').value = data.agent_max_context_turns || 20;
    document.getElementById('cfg-max-steps').value = data.agent_max_steps || 20;
    document.getElementById('cfg-enable-thinking').checked = data.enable_thinking === true;

    const pwdInput = document.getElementById('cfg-password');
    const maskedPwd = data.web_password_masked || '';
    pwdInput.value = maskedPwd;
    pwdInput.dataset.masked = maskedPwd ? '1' : '';
    pwdInput.dataset.maskedVal = maskedPwd;
    pwdInput.classList.toggle('cfg-key-masked', !!maskedPwd);

    if (maskedPwd) {
        pwdInput.placeholder = '••••••••';
    } else {
        pwdInput.placeholder = '';
    }

    if (!pwdInput._cfgBound) {
        pwdInput.addEventListener('focus', function() {
            if (this.dataset.masked === '1') {
                this.value = '';
                this.dataset.masked = '';
                this.classList.remove('cfg-key-masked');
            }
        });
        pwdInput.addEventListener('input', function() {
            this.dataset.masked = '';
        });
        pwdInput._cfgBound = true;
    }
}

function detectProvider(model) {
    if (!model) return Object.keys(configProviders)[0] || '';
    for (const [pid, p] of Object.entries(configProviders)) {
        if (pid === 'linkai') continue;
        if (p.models && p.models.includes(model)) return pid;
    }
    return Object.keys(configProviders)[0] || '';
}

function onProviderChange(pid) {
    cfgProviderValue = pid || getDropdownValue(document.getElementById('cfg-provider'));
    const p = configProviders[cfgProviderValue];
    if (!p) return;

    const customTip = document.getElementById('cfg-custom-tip');
    if (customTip) customTip.classList.toggle('hidden', cfgProviderValue !== 'custom');

    const modelEl = document.getElementById('cfg-model-select');
    const modelOpts = (p.models || []).map(m => ({ value: m, label: m }));
    modelOpts.push({ value: '__custom__', label: t('config_custom_option') });

    initDropdown(modelEl, modelOpts, modelOpts[0] ? modelOpts[0].value : '', onModelSelectChange);

    // API Key
    const keyField = p.api_key_field;
    const keyWrap = document.getElementById('cfg-api-key-wrap');
    const keyInput = document.getElementById('cfg-api-key');
    if (keyField) {
        keyWrap.classList.remove('hidden');
        keyInput.classList.add('cfg-key-masked');
        const maskedVal = configApiKeys[keyField] || '';
        keyInput.value = maskedVal;
        keyInput.dataset.field = keyField;
        keyInput.dataset.masked = maskedVal ? '1' : '';
        keyInput.dataset.maskedVal = maskedVal;
        const toggleIcon = document.querySelector('#cfg-api-key-toggle i');
        if (toggleIcon) toggleIcon.className = 'fas fa-eye text-xs';

        if (!keyInput._cfgBound) {
            keyInput.addEventListener('focus', function() {
                if (this.dataset.masked === '1') {
                    this.value = '';
                    this.dataset.masked = '';
                    this.classList.remove('cfg-key-masked');
                }
            });
            keyInput.addEventListener('blur', function() {
                if (!this.value.trim() && this.dataset.maskedVal) {
                    this.value = this.dataset.maskedVal;
                    this.dataset.masked = '1';
                    this.classList.add('cfg-key-masked');
                }
            });
            keyInput.addEventListener('input', function() {
                this.dataset.masked = '';
            });
            keyInput._cfgBound = true;
        }
    } else {
        keyWrap.classList.add('hidden');
        keyInput.value = '';
        keyInput.dataset.field = '';
    }

    // API Base
    const apiBaseInput = document.getElementById('cfg-api-base');
    if (p.api_base_key) {
        document.getElementById('cfg-api-base-wrap').classList.remove('hidden');
        apiBaseInput.value = configApiBases[p.api_base_key] || p.api_base_default || '';
        // Hint the version-path tail (e.g. /v1) so users are reminded to
        // include it themselves. We don't auto-rewrite anything server-side.
        apiBaseInput.placeholder = p.api_base_placeholder || 'https://...';
    } else {
        document.getElementById('cfg-api-base-wrap').classList.add('hidden');
        apiBaseInput.value = '';
        apiBaseInput.placeholder = 'https://...';
    }

    onModelSelectChange(modelOpts[0] ? modelOpts[0].value : '');
}

function onModelSelectChange(val) {
    cfgModelValue = val || getDropdownValue(document.getElementById('cfg-model-select'));
    const customWrap = document.getElementById('cfg-model-custom-wrap');
    if (cfgModelValue === '__custom__') {
        customWrap.classList.remove('hidden');
        document.getElementById('cfg-model-custom').focus();
    } else {
        customWrap.classList.add('hidden');
        document.getElementById('cfg-model-custom').value = '';
    }
}

function syncModelSelection(model) {
    const p = configProviders[cfgProviderValue];
    if (!p) return;

    const modelEl = document.getElementById('cfg-model-select');
    if (p.models && p.models.includes(model)) {
        const modelOpts = (p.models || []).map(m => ({ value: m, label: m }));
        modelOpts.push({ value: '__custom__', label: t('config_custom_option') });
        initDropdown(modelEl, modelOpts, model, onModelSelectChange);
        cfgModelValue = model;
        document.getElementById('cfg-model-custom-wrap').classList.add('hidden');
    } else {
        cfgModelValue = '__custom__';
        const modelOpts = (p.models || []).map(m => ({ value: m, label: m }));
        modelOpts.push({ value: '__custom__', label: t('config_custom_option') });
        initDropdown(modelEl, modelOpts, '__custom__', onModelSelectChange);
        document.getElementById('cfg-model-custom-wrap').classList.remove('hidden');
        document.getElementById('cfg-model-custom').value = model;
    }
}

function getSelectedModel() {
    if (cfgModelValue === '__custom__') {
        return document.getElementById('cfg-model-custom').value.trim();
    }
    return cfgModelValue;
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('cfg-api-key');
    const icon = document.querySelector('#cfg-api-key-toggle i');
    if (input.classList.contains('cfg-key-masked')) {
        input.classList.remove('cfg-key-masked');
        icon.className = 'fas fa-eye-slash text-xs';
    } else {
        input.classList.add('cfg-key-masked');
        icon.className = 'fas fa-eye text-xs';
    }
}

function showStatus(elId, msgKey, isError) {
    const el = document.getElementById(elId);
    el.textContent = t(msgKey);
    el.classList.toggle('text-red-500', !!isError);
    el.classList.toggle('text-primary-500', !isError);
    el.classList.remove('opacity-0');
    setTimeout(() => el.classList.add('opacity-0'), 2500);
}

function saveModelConfig() {
    const model = getSelectedModel();
    if (!model) return;

    const updates = { model: model };
    const p = configProviders[cfgProviderValue];
    updates.use_linkai = (cfgProviderValue === 'linkai');
    if (cfgProviderValue === 'linkai') {
        updates.bot_type = '';
    } else {
        updates.bot_type = cfgProviderValue;
    }
    if (p && p.api_base_key) {
        const base = document.getElementById('cfg-api-base').value.trim();
        if (base) updates[p.api_base_key] = base;
    }
    if (p && p.api_key_field) {
        const keyInput = document.getElementById('cfg-api-key');
        const rawVal = keyInput.value.trim();
        if (rawVal && keyInput.dataset.masked !== '1') {
            updates[p.api_key_field] = rawVal;
        }
    }

    const btn = document.getElementById('cfg-model-save');
    btn.disabled = true;
    fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            configCurrentModel = model;
            if (data.applied) {
                const keyInput = document.getElementById('cfg-api-key');
                Object.entries(data.applied).forEach(([k, v]) => {
                    if (k === 'model') return;
                    if (k.includes('api_key')) {
                        const masked = v.length > 8
                            ? v.substring(0, 4) + '*'.repeat(v.length - 8) + v.substring(v.length - 4)
                            : v;
                        configApiKeys[k] = masked;
                        if (keyInput.dataset.field === k) {
                            keyInput.value = masked;
                            keyInput.dataset.masked = '1';
                            keyInput.dataset.maskedVal = masked;
                            keyInput.classList.add('cfg-key-masked');
                            const toggleIcon = document.querySelector('#cfg-api-key-toggle i');
                            if (toggleIcon) toggleIcon.className = 'fas fa-eye text-xs';
                        }
                    } else {
                        configApiBases[k] = v;
                    }
                });
            }
            showStatus('cfg-model-status', 'config_saved', false);
        } else {
            showStatus('cfg-model-status', 'config_save_error', true);
        }
    })
    .catch(() => showStatus('cfg-model-status', 'config_save_error', true))
    .finally(() => { btn.disabled = false; });
}

function saveAgentConfig() {
    const updates = {
        agent_max_context_tokens: parseInt(document.getElementById('cfg-max-tokens').value) || 50000,
        agent_max_context_turns: parseInt(document.getElementById('cfg-max-turns').value) || 20,
        agent_max_steps: parseInt(document.getElementById('cfg-max-steps').value) || 20,
        enable_thinking: document.getElementById('cfg-enable-thinking').checked,
    };

    const btn = document.getElementById('cfg-agent-save');
    btn.disabled = true;
    fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            showStatus('cfg-agent-status', 'config_saved', false);
        } else {
            showStatus('cfg-agent-status', 'config_save_error', true);
        }
    })
    .catch(() => showStatus('cfg-agent-status', 'config_save_error', true))
    .finally(() => { btn.disabled = false; });
}

function savePasswordConfig() {
    const input = document.getElementById('cfg-password');
    if (input.dataset.masked === '1') {
        showStatus('cfg-password-status', 'config_saved', false);
        return;
    }
    const newPwd = input.value.trim();
    const btn = document.getElementById('cfg-password-save');
    btn.disabled = true;
    fetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: { web_password: newPwd } })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            if (newPwd) {
                showStatus('cfg-password-status', 'config_password_changed', false);
                setTimeout(() => { window.location.reload(); }, 1500);
            } else {
                input.dataset.masked = '';
                input.dataset.maskedVal = '';
                input.classList.remove('cfg-key-masked');
                showStatus('cfg-password-status', 'config_password_cleared', false);
            }
        } else {
            showStatus('cfg-password-status', 'config_save_error', true);
        }
    })
    .catch(() => showStatus('cfg-password-status', 'config_save_error', true))
    .finally(() => { btn.disabled = false; });
}

function loadConfigView() {
    fetch('/config').then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        appConfig = data;
        initConfigView(data);
    }).catch(() => {});
}

// =====================================================================
// Skills View
// =====================================================================
let toolsLoaded = false;

const TOOL_ICONS = {
    bash: 'fa-terminal',
    edit: 'fa-pen-to-square',
    read: 'fa-file-lines',
    write: 'fa-file-pen',
    ls: 'fa-folder-open',
    send: 'fa-paper-plane',
    web_search: 'fa-magnifying-glass',
    browser: 'fa-globe',
    env_config: 'fa-key',
    scheduler: 'fa-clock',
    memory_get: 'fa-brain',
    memory_search: 'fa-brain',
};

function getToolIcon(name) {
    return TOOL_ICONS[name] || 'fa-wrench';
}

function loadSkillsView() {
    loadToolsSection();
    loadSkillsSection();
}

function loadToolsSection() {
    if (toolsLoaded) return;
    const emptyEl = document.getElementById('tools-empty');
    const listEl = document.getElementById('tools-list');
    const badge = document.getElementById('tools-count-badge');

    fetch('/api/tools').then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        const tools = data.tools || [];
        emptyEl.classList.add('hidden');
        if (tools.length === 0) {
            emptyEl.classList.remove('hidden');
            emptyEl.innerHTML = `<span class="text-sm text-slate-400 dark:text-slate-500">${currentLang === 'zh' ? '暂无内置工具' : 'No built-in tools'}</span>`;
            return;
        }
        badge.textContent = tools.length;
        badge.classList.remove('hidden');
        listEl.innerHTML = '';
        tools.forEach(tool => {
            const card = document.createElement('div');
            card.className = 'bg-white dark:bg-[#1A1A1A] rounded-xl border border-slate-200 dark:border-white/10 p-4 flex items-start gap-3';
            card.innerHTML = `
                <div class="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center flex-shrink-0">
                    <i class="fas ${getToolIcon(tool.name)} text-blue-500 dark:text-blue-400 text-sm"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="font-medium text-sm text-slate-700 dark:text-slate-200 font-mono">${escapeHtml(tool.name)}</span>
                    </div>
                    <p class="text-xs text-slate-400 dark:text-slate-500 mt-1 line-clamp-2">${escapeHtml(tool.description || '--')}</p>
                </div>`;
            listEl.appendChild(card);
        });
        listEl.classList.remove('hidden');
        toolsLoaded = true;
    }).catch(() => {
        emptyEl.classList.remove('hidden');
        emptyEl.innerHTML = `<span class="text-sm text-slate-400 dark:text-slate-500">${currentLang === 'zh' ? '加载失败' : 'Failed to load'}</span>`;
    });
}

function loadSkillsSection() {
    const emptyEl = document.getElementById('skills-empty');
    const listEl = document.getElementById('skills-list');
    const badge = document.getElementById('skills-count-badge');

    fetch('/api/skills').then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        const skills = data.skills || [];
        if (skills.length === 0) {
            const p = emptyEl.querySelector('p');
            if (p) p.textContent = currentLang === 'zh' ? '暂无技能' : 'No skills found';
            return;
        }
        badge.textContent = skills.length;
        badge.classList.remove('hidden');
        emptyEl.classList.add('hidden');
        listEl.innerHTML = '';

        skills.forEach(sk => {
            const card = document.createElement('div');
            card.className = 'bg-white dark:bg-[#1A1A1A] rounded-xl border border-slate-200 dark:border-white/10 p-4 flex items-start gap-3 transition-opacity';
            card.dataset.skillName = sk.name;
            card.dataset.skillDesc = sk.description || '';
            card.dataset.enabled = sk.enabled ? '1' : '0';
            renderSkillCard(card, sk);
            listEl.appendChild(card);
        });
    }).catch(() => {});
}

function renderSkillCard(card, sk) {
    const enabled = sk.enabled;
    const iconColor = enabled ? 'text-primary-400' : 'text-slate-300 dark:text-slate-600';
    const trackClass = enabled
        ? 'bg-primary-400'
        : 'bg-slate-200 dark:bg-slate-700';
    const thumbTranslate = enabled ? 'translate-x-3' : 'translate-x-0.5';
    card.innerHTML = `
        <div class="w-9 h-9 rounded-lg bg-amber-50 dark:bg-amber-900/20 flex items-center justify-center flex-shrink-0">
            <i class="fas fa-bolt ${iconColor} text-sm"></i>
        </div>
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
                <span class="font-medium text-sm text-slate-700 dark:text-slate-200 truncate flex-1">${escapeHtml(sk.display_name || sk.name)}</span>
                <button
                    role="switch"
                    aria-checked="${enabled}"
                    onclick="toggleSkill('${escapeHtml(sk.name)}', ${enabled})"
                    class="relative inline-flex h-4 w-7 flex-shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none ${trackClass}"
                    title="${enabled ? (currentLang === 'zh' ? '点击禁用' : 'Click to disable') : (currentLang === 'zh' ? '点击启用' : 'Click to enable')}"
                >
                    <span class="inline-block h-3 w-3 mt-0.5 rounded-full bg-white shadow transform transition-transform duration-200 ease-in-out ${thumbTranslate}"></span>
                </button>
            </div>
            <p class="text-xs text-slate-400 dark:text-slate-500 line-clamp-2">${escapeHtml(sk.description || '--')}</p>
        </div>`;
}

function toggleSkill(name, currentlyEnabled) {
    const action = currentlyEnabled ? 'close' : 'open';
    const card = document.querySelector(`[data-skill-name="${CSS.escape(name)}"]`);
    if (card) card.style.opacity = '0.5';

    fetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, name })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            if (card) {
                const desc = card.dataset.skillDesc || '';
                card.dataset.enabled = currentlyEnabled ? '0' : '1';
                card.style.opacity = '1';
                renderSkillCard(card, { name, description: desc, enabled: !currentlyEnabled });
            }
        } else {
            if (card) card.style.opacity = '1';
            alert(currentLang === 'zh' ? '操作失败，请稍后再试' : 'Operation failed, please try again');
        }
    })
    .catch(() => {
        if (card) card.style.opacity = '1';
        alert(currentLang === 'zh' ? '操作失败，请稍后再试' : 'Operation failed, please try again');
    });
}

// =====================================================================
// Memory View
// =====================================================================
let memoryPage = 1;
let memoryCategory = 'memory';   // 'memory' | 'dream'
const memoryPageSize = 10;

function switchMemoryTab(tab) {
    document.querySelectorAll('.memory-tab').forEach(el => el.classList.remove('active'));
    document.getElementById('memory-tab-' + tab).classList.add('active');
    memoryCategory = tab === 'dreams' ? 'dream' : 'memory';
    loadMemoryView(1);
}

function loadMemoryView(page) {
    page = page || 1;
    memoryPage = page;
    fetch(`/api/memory?page=${page}&page_size=${memoryPageSize}&category=${memoryCategory}`).then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        const emptyEl = document.getElementById('memory-empty');
        const listEl = document.getElementById('memory-list');
        const files = data.list || [];
        const total = data.total || 0;

        if (total === 0) {
            const emptyIcon = emptyEl.querySelector('i');
            const emptyTitle = emptyEl.querySelector('p');
            if (memoryCategory === 'dream') {
                emptyIcon.className = 'fas fa-moon text-purple-400 text-xl';
                emptyTitle.textContent = currentLang === 'zh' ? '暂无梦境日记' : 'No dream diaries yet';
            } else {
                emptyIcon.className = 'fas fa-brain text-purple-400 text-xl';
                emptyTitle.textContent = currentLang === 'zh' ? '暂无记忆文件' : 'No memory files';
            }
            emptyEl.classList.remove('hidden');
            listEl.classList.add('hidden');
            return;
        }
        emptyEl.classList.add('hidden');
        listEl.classList.remove('hidden');

        const tbody = document.getElementById('memory-table-body');
        tbody.innerHTML = '';
        files.forEach(f => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-slate-100 dark:border-white/5 hover:bg-slate-50 dark:hover:bg-white/5 cursor-pointer transition-colors';
            tr.onclick = () => openMemoryFile(f.filename, memoryCategory);
            let typeLabel;
            if (f.type === 'global') {
                typeLabel = '<span class="px-2 py-0.5 rounded-full text-xs bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400">Global</span>';
            } else if (f.type === 'dream') {
                typeLabel = '<span class="px-2 py-0.5 rounded-full text-xs bg-violet-50 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400">Dream</span>';
            } else {
                typeLabel = '<span class="px-2 py-0.5 rounded-full text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">Daily</span>';
            }
            const sizeStr = f.size < 1024 ? f.size + ' B' : (f.size / 1024).toFixed(1) + ' KB';
            tr.innerHTML = `
                <td class="px-4 py-3 text-sm font-mono text-slate-700 dark:text-slate-200">${escapeHtml(f.filename)}</td>
                <td class="px-4 py-3 text-sm">${typeLabel}</td>
                <td class="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">${sizeStr}</td>
                <td class="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">${escapeHtml(f.updated_at)}</td>`;
            tbody.appendChild(tr);
        });

        // Pagination
        const totalPages = Math.ceil(total / memoryPageSize);
        const pagEl = document.getElementById('memory-pagination');
        if (totalPages <= 1) { pagEl.innerHTML = ''; return; }
        let pagHtml = `<span>${page} / ${totalPages}</span><div class="flex gap-2">`;
        if (page > 1) pagHtml += `<button onclick="loadMemoryView(${page - 1})" class="px-3 py-1 rounded-lg border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/10 text-xs">Prev</button>`;
        if (page < totalPages) pagHtml += `<button onclick="loadMemoryView(${page + 1})" class="px-3 py-1 rounded-lg border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/10 text-xs">Next</button>`;
        pagHtml += '</div>';
        pagEl.innerHTML = pagHtml;
    }).catch(() => {});
}

function openMemoryFile(filename, category) {
    category = category || 'memory';
    fetch(`/api/memory/content?filename=${encodeURIComponent(filename)}&category=${category}`).then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        document.getElementById('memory-panel-list').classList.add('hidden');
        const panel = document.getElementById('memory-panel-viewer');
        document.getElementById('memory-viewer-title').textContent = filename;
        document.getElementById('memory-viewer-content').innerHTML = renderMarkdown(data.content || '');
        panel.classList.remove('hidden');
        applyHighlighting(panel);
    }).catch(() => {});
}

function closeMemoryViewer() {
    document.getElementById('memory-panel-viewer').classList.add('hidden');
    document.getElementById('memory-panel-list').classList.remove('hidden');
}

// =====================================================================
// Custom Confirm Dialog
// =====================================================================
function showConfirmDialog({ title, message, okText, cancelText, onConfirm }) {
    const overlay = document.getElementById('confirm-dialog-overlay');
    document.getElementById('confirm-dialog-title').textContent = title || '';
    document.getElementById('confirm-dialog-message').textContent = message || '';
    document.getElementById('confirm-dialog-ok').textContent = okText || 'OK';
    document.getElementById('confirm-dialog-cancel').textContent = cancelText || t('channels_cancel');

    function cleanup() {
        overlay.classList.add('hidden');
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        overlay.removeEventListener('click', onOverlayClick);
    }
    function onOk() { cleanup(); if (onConfirm) onConfirm(); }
    function onCancel() { cleanup(); }
    function onOverlayClick(e) { if (e.target === overlay) cleanup(); }

    const okBtn = document.getElementById('confirm-dialog-ok');
    const cancelBtn = document.getElementById('confirm-dialog-cancel');
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    overlay.addEventListener('click', onOverlayClick);
    overlay.classList.remove('hidden');
}

// =====================================================================
// Channels View
// =====================================================================
let channelsData = [];

function loadChannelsView() {
    const container = document.getElementById('channels-content');
    container.innerHTML = `<div class="flex items-center gap-2 py-8 justify-center text-slate-400 dark:text-slate-500 text-sm">
        <i class="fas fa-spinner fa-spin text-xs"></i><span>Loading...</span></div>`;

    fetch('/api/channels').then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        channelsData = data.channels || [];
        renderActiveChannels();
    }).catch(() => {
        container.innerHTML = '<p class="text-sm text-red-400 py-8 text-center">Failed to load channels</p>';
    });
}

function renderActiveChannels() {
    stopWeixinQrPoll();
    stopWeixinStatusPoll();
    const container = document.getElementById('channels-content');
    container.innerHTML = '';
    closeAddChannelPanel();

    const activeChannels = channelsData.filter(ch => ch.active);

    if (activeChannels.length === 0) {
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center py-20">
                <div class="w-16 h-16 rounded-2xl bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mb-4">
                    <i class="fas fa-tower-broadcast text-blue-400 text-xl"></i>
                </div>
                <p class="text-slate-500 dark:text-slate-400 font-medium">${t('channels_empty')}</p>
                <p class="text-sm text-slate-400 dark:text-slate-500 mt-1">${t('channels_empty_desc')}</p>
            </div>`;
        return;
    }

    activeChannels.forEach(ch => {
        const label = (typeof ch.label === 'object') ? (ch.label[currentLang] || ch.label.en) : ch.label;
        const card = document.createElement('div');
        card.className = 'bg-white dark:bg-[#1A1A1A] rounded-xl border border-slate-200 dark:border-white/10 p-6';
        card.id = `channel-card-${ch.name}`;

        const fieldsHtml = buildChannelFieldsHtml(ch.name, ch.fields || []);
        const hasFields = (ch.fields || []).length > 0;

        const weixinWaiting = ch.name === 'weixin' && ch.login_status && ch.login_status !== 'logged_in';
        const wecomNeedsCreds = ch.name === 'wecom_bot' && !_wecomBotHasCreds(ch);
        // 飞书 active 卡片渲染带 Tab 的 panel：手动填写 + 扫码重建（覆盖现有配置）
        const isFeishu = ch.name === 'feishu';
        let statusDot, statusText;
        if (weixinWaiting) {
            statusDot = 'bg-amber-400 animate-pulse';
            statusText = ch.login_status === 'scanned'
                ? `<span class="text-xs text-primary-500">${t('weixin_scan_scanned')}</span>`
                : `<span class="text-xs text-amber-500">${t('weixin_scan_waiting')}</span>`;
        } else if (wecomNeedsCreds) {
            statusDot = 'bg-amber-400 animate-pulse';
            statusText = `<span class="text-xs text-amber-500">${t('channels_connecting')}</span>`;
        } else {
            statusDot = 'bg-primary-400';
            statusText = `<span class="text-xs text-primary-500">${t('channels_connected')}</span>`;
        }

        card.innerHTML = `
            <div class="flex items-center gap-4${hasFields || weixinWaiting || wecomNeedsCreds || isFeishu ? ' mb-5' : ''}">
                <div class="w-10 h-10 rounded-xl bg-${ch.color}-50 dark:bg-${ch.color}-900/20 flex items-center justify-center flex-shrink-0">
                    <i class="fas ${ch.icon} text-${ch.color}-500 text-base"></i>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="font-semibold text-slate-800 dark:text-slate-100">${escapeHtml(label)}</span>
                        <span class="w-2 h-2 rounded-full ${statusDot}"></span>
                        ${statusText}
                    </div>
                    <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-mono">${escapeHtml(ch.name)}</p>
                </div>
                <button onclick="disconnectChannel('${ch.name}')"
                    class="px-3 py-1.5 rounded-lg text-xs font-medium
                           bg-red-50 dark:bg-red-900/20 text-red-500 dark:text-red-400
                           hover:bg-red-100 dark:hover:bg-red-900/40
                           cursor-pointer transition-colors flex-shrink-0">
                    ${t('channels_disconnect')}
                </button>
            </div>
            ${weixinWaiting ? `<div id="weixin-active-qr" class="flex flex-col items-center py-2">
                <button onclick="showWeixinActiveQr()"
                    class="px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium
                           cursor-pointer transition-colors duration-150">
                    ${t('weixin_scan_title')}
                </button>
            </div>` : ''}
            ${wecomNeedsCreds ? `<div id="wecom-active-auth" class="flex flex-col items-center py-2">
                <p class="text-sm text-slate-500 dark:text-slate-400 mb-3">${t('wecom_scan_desc')}</p>
                <button onclick="startWecomBotAuthInCard()"
                    class="px-5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium
                           cursor-pointer transition-colors duration-150">
                    <i class="fas fa-qrcode mr-2"></i>${t('wecom_scan_btn')}
                </button>
                <div id="wecom-card-scan-status" class="mt-3"></div>
            </div>` : ''}
            ${isFeishu ? buildFeishuPanel(ch, true) : (hasFields ? `<div class="space-y-4">
                ${fieldsHtml}
                <div class="flex items-center justify-end gap-3 pt-1">
                    <span id="ch-status-${ch.name}" class="text-xs text-primary-500 opacity-0 transition-opacity duration-300"></span>
                    <button onclick="saveChannelConfig('${ch.name}')"
                        class="px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium
                               cursor-pointer transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                        id="ch-save-${ch.name}">${t('channels_save')}</button>
                </div>
            </div>` : '')}`;

        container.appendChild(card);
        bindSecretFieldEvents(card);

        if (weixinWaiting) {
            startWeixinActiveStatusPoll();
        }
    });
}

function buildChannelFieldsHtml(chName, fields) {
    let html = '';
    fields.forEach(f => {
        const inputId = `ch-${chName}-${f.key}`;
        let inputHtml = '';
        if (f.type === 'bool') {
            inputHtml = investmentSwitch('', inputId, Boolean(f.value), {
                attrs: `data-field="${escapeHtml(f.key)}" data-ch="${escapeHtml(chName)}"`,
            });
        } else if (f.type === 'secret') {
            inputHtml = `<input id="${inputId}" type="text" value="${escapeHtml(String(f.value || ''))}"
                data-field="${f.key}" data-ch="${chName}" data-masked="${f.value ? '1' : ''}"
                class="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600
                       bg-slate-50 dark:bg-white/5 text-sm text-slate-800 dark:text-slate-100
                       focus:outline-none focus:border-primary-500 font-mono transition-colors
                       ${f.value ? 'cfg-key-masked' : ''}"
                placeholder="${escapeHtml(f.label)}">`;
        } else {
            const inputType = f.type === 'number' ? 'number' : 'text';
            inputHtml = `<input id="${inputId}" type="${inputType}" value="${escapeHtml(String(f.value ?? f.default ?? ''))}"
                data-field="${f.key}" data-ch="${chName}"
                class="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600
                       bg-slate-50 dark:bg-white/5 text-sm text-slate-800 dark:text-slate-100
                       focus:outline-none focus:border-primary-500 font-mono transition-colors"
                placeholder="${escapeHtml(f.label)}">`;
        }
        html += `<div>
            <label class="block text-sm font-medium text-slate-600 dark:text-slate-400 mb-1.5">${escapeHtml(f.label)}</label>
            ${inputHtml}
        </div>`;
    });
    return html;
}

function bindSecretFieldEvents(container) {
    container.querySelectorAll('input[data-masked="1"]').forEach(inp => {
        inp.addEventListener('focus', function() {
            if (this.dataset.masked === '1') {
                this.value = '';
                this.dataset.masked = '';
                this.classList.remove('cfg-key-masked');
            }
        });
    });
}

function showChannelStatus(chName, msgKey, isError) {
    const el = document.getElementById(`ch-status-${chName}`);
    if (!el) return;
    el.textContent = t(msgKey);
    el.classList.toggle('text-red-500', !!isError);
    el.classList.toggle('text-primary-500', !isError);
    el.classList.remove('opacity-0');
    setTimeout(() => el.classList.add('opacity-0'), 2500);
}

function saveChannelConfig(chName) {
    const card = document.getElementById(`channel-card-${chName}`);
    if (!card) return;

    const updates = {};
    card.querySelectorAll('input[data-ch="' + chName + '"]').forEach(inp => {
        const key = inp.dataset.field;
        if (inp.type === 'checkbox') {
            updates[key] = inp.checked;
        } else {
            if (inp.dataset.masked === '1') return;
            updates[key] = inp.value;
        }
    });

    const btn = document.getElementById(`ch-save-${chName}`);
    if (btn) btn.disabled = true;

    fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', channel: chName, config: updates })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            showChannelStatus(chName, data.restarted ? 'channels_restarted' : 'channels_saved', false);
        } else {
            showChannelStatus(chName, 'channels_save_error', true);
        }
    })
    .catch(() => showChannelStatus(chName, 'channels_save_error', true))
    .finally(() => { if (btn) btn.disabled = false; });
}

function disconnectChannel(chName) {
    const ch = channelsData.find(c => c.name === chName);
    const label = ch ? ((typeof ch.label === 'object') ? (ch.label[currentLang] || ch.label.en) : ch.label) : chName;

    showConfirmDialog({
        title: t('channels_disconnect'),
        message: t('channels_disconnect_confirm'),
        okText: t('channels_disconnect'),
        cancelText: t('channels_cancel'),
        onConfirm: () => {
            fetch('/api/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'disconnect', channel: chName })
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    if (ch) ch.active = false;
                    renderActiveChannels();
                }
            })
            .catch(() => {});
        }
    });
}

// --- Add channel panel ---
function openAddChannelPanel() {
    const panel = document.getElementById('channels-add-panel');
    const activeNames = new Set(channelsData.filter(c => c.active).map(c => c.name));
    const available = channelsData.filter(c => !activeNames.has(c.name));

    const content = document.getElementById('channels-content');
    if (activeNames.size === 0 && content) content.classList.add('hidden');

    if (available.length === 0) {
        panel.innerHTML = `<div class="bg-white dark:bg-[#1A1A1A] rounded-xl border border-slate-200 dark:border-white/10 p-6 text-center">
            <p class="text-sm text-slate-500 dark:text-slate-400">${currentLang === 'zh' ? '所有通道均已接入' : 'All channels are already connected'}</p>
            <button onclick="closeAddChannelPanel()" class="mt-3 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 cursor-pointer">${t('channels_cancel')}</button>
        </div>`;
        panel.classList.remove('hidden');
        return;
    }

    const ddOptions = [
        { value: '', label: t('channels_select_placeholder') },
        ...available.map(ch => {
            const label = (typeof ch.label === 'object') ? (ch.label[currentLang] || ch.label.en) : ch.label;
            return { value: ch.name, label: `${label} (${ch.name})` };
        })
    ];

    panel.innerHTML = `
        <div class="bg-white dark:bg-[#1A1A1A] rounded-xl border border-primary-200 dark:border-primary-800 p-6">
            <div class="flex items-center gap-3 mb-5">
                <div class="w-9 h-9 rounded-lg bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center">
                    <i class="fas fa-plus text-primary-500 text-sm"></i>
                </div>
                <h3 class="font-semibold text-slate-800 dark:text-slate-100">${t('channels_add')}</h3>
            </div>
            <div class="mb-4">
                <div id="add-channel-select" class="cfg-dropdown" tabindex="0">
                    <div class="cfg-dropdown-selected">
                        <span class="cfg-dropdown-text">--</span>
                        <i class="fas fa-chevron-down cfg-dropdown-arrow"></i>
                    </div>
                    <div class="cfg-dropdown-menu"></div>
                </div>
            </div>
            <div id="add-channel-fields" class="space-y-4"></div>
            <div id="add-channel-actions" class="hidden flex items-center justify-end gap-3 pt-4">
                <button onclick="closeAddChannelPanel()"
                    class="px-4 py-2 rounded-lg border border-slate-200 dark:border-white/10
                           text-slate-600 dark:text-slate-300 text-sm font-medium
                           hover:bg-slate-50 dark:hover:bg-white/5
                           cursor-pointer transition-colors duration-150">${t('channels_cancel')}</button>
                <button id="add-channel-submit" onclick="submitAddChannel()"
                    class="px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium
                           cursor-pointer transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed">${t('channels_connect_btn')}</button>
            </div>
        </div>`;
    panel.classList.remove('hidden');
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    const ddEl = document.getElementById('add-channel-select');
    initDropdown(ddEl, ddOptions, '', onAddChannelSelect);
}

function closeAddChannelPanel() {
    stopWeixinQrPoll();
    stopFeishuRegisterPoll();
    const panel = document.getElementById('channels-add-panel');
    if (panel) {
        panel.classList.add('hidden');
        panel.innerHTML = '';
    }
    const content = document.getElementById('channels-content');
    if (content) content.classList.remove('hidden');
}

function onAddChannelSelect(chName) {
    stopWeixinQrPoll();
    stopFeishuRegisterPoll();
    const fieldsContainer = document.getElementById('add-channel-fields');
    const actions = document.getElementById('add-channel-actions');

    if (!chName) {
        fieldsContainer.innerHTML = '';
        actions.classList.add('hidden');
        return;
    }

    if (chName === 'weixin') {
        actions.classList.add('hidden');
        fieldsContainer.innerHTML = `
            <div id="weixin-qr-panel" class="flex flex-col items-center py-4">
                <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">${t('weixin_scan_loading')}</p>
            </div>`;
        startWeixinQrLogin();
        return;
    }

    if (chName === 'wecom_bot') {
        actions.classList.add('hidden');
        const ch = channelsData.find(c => c.name === chName);
        fieldsContainer.innerHTML = buildWecomBotPanel(ch);
        return;
    }

    if (chName === 'feishu') {
        actions.classList.add('hidden');
        const ch = channelsData.find(c => c.name === chName);
        fieldsContainer.innerHTML = buildFeishuPanel(ch);
        return;
    }

    const ch = channelsData.find(c => c.name === chName);
    if (!ch) return;

    fieldsContainer.innerHTML = buildChannelFieldsHtml(chName, ch.fields || []);
    bindSecretFieldEvents(fieldsContainer);
    actions.classList.remove('hidden');
}

function submitAddChannel() {
    const ddEl = document.getElementById('add-channel-select');
    const chName = getDropdownValue(ddEl);
    if (!chName) return;

    const fieldsContainer = document.getElementById('add-channel-fields');
    const updates = {};
    fieldsContainer.querySelectorAll('input[data-ch="' + chName + '"]').forEach(inp => {
        const key = inp.dataset.field;
        if (inp.type === 'checkbox') {
            updates[key] = inp.checked;
        } else {
            if (inp.dataset.masked === '1') return;
            updates[key] = inp.value;
        }
    });

    const btn = document.getElementById('add-channel-submit');
    if (btn) { btn.disabled = true; btn.textContent = t('channels_connecting'); }

    fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'connect', channel: chName, config: updates })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            const ch = channelsData.find(c => c.name === chName);
            if (ch) {
                ch.active = true;
                (ch.fields || []).forEach(f => {
                    if (updates[f.key] !== undefined) {
                        f.value = f.type === 'secret' ? ChannelsHandler_maskSecret(updates[f.key]) : updates[f.key];
                    }
                });
            }
            renderActiveChannels();
        } else {
            if (btn) { btn.disabled = false; btn.textContent = t('channels_connect_btn'); }
        }
    })
    .catch(() => {
        if (btn) { btn.disabled = false; btn.textContent = t('channels_connect_btn'); }
    });
}

// =====================================================================
// WeChat QR Login
// =====================================================================
let _weixinQrPollTimer = null;
let _weixinStatusPollTimer = null;

function stopWeixinStatusPoll() {
    if (_weixinStatusPollTimer) {
        clearTimeout(_weixinStatusPollTimer);
        _weixinStatusPollTimer = null;
    }
}

function startWeixinActiveStatusPoll() {
    stopWeixinStatusPoll();
    _weixinStatusPollTimer = setTimeout(() => {
        fetch('/api/channels').then(r => r.json()).then(data => {
            if (data.status !== 'success') return;
            const wx = (data.channels || []).find(c => c.name === 'weixin');
            if (!wx || !wx.active) return;
            if (wx.login_status === 'logged_in') {
                channelsData = data.channels;
                renderActiveChannels();
            } else {
                const ch = channelsData.find(c => c.name === 'weixin');
                if (ch) ch.login_status = wx.login_status;
                startWeixinActiveStatusPoll();
            }
        }).catch(() => { startWeixinActiveStatusPoll(); });
    }, 3000);
}

function showWeixinActiveQr() {
    const container = document.getElementById('weixin-active-qr');
    if (!container) return;
    container.innerHTML = `
        <div id="weixin-qr-panel" class="flex flex-col items-center py-2">
            <p class="text-sm text-slate-500 dark:text-slate-400 mb-4">${t('weixin_scan_loading')}</p>
        </div>`;
    stopWeixinStatusPoll();
    startWeixinQrLogin();
}

function stopWeixinQrPoll() {
    if (_weixinQrPollTimer) {
        clearTimeout(_weixinQrPollTimer);
        _weixinQrPollTimer = null;
    }
}

function startWeixinQrLogin() {
    stopWeixinQrPoll();
    fetch('/api/weixin/qrlogin')
        .then(r => r.json())
        .then(data => {
            const panel = document.getElementById('weixin-qr-panel');
            if (!panel) return;
            if (data.status !== 'success') {
                panel.innerHTML = `<p class="text-sm text-red-500">${t('weixin_scan_fail')}: ${data.message || ''}</p>`;
                return;
            }
            renderWeixinQr(data.qr_image || data.qrcode_url, 'waiting');
            if (data.source === 'channel') {
                startWeixinActiveStatusPoll();
            } else {
                pollWeixinQrStatus();
            }
        })
        .catch(() => {
            const panel = document.getElementById('weixin-qr-panel');
            if (panel) panel.innerHTML = `<p class="text-sm text-red-500">${t('weixin_scan_fail')}</p>`;
        });
}

function renderWeixinQr(qrcodeUrl, status) {
    const panel = document.getElementById('weixin-qr-panel');
    if (!panel) return;

    let statusText = t('weixin_scan_waiting');
    let statusColor = 'text-slate-500 dark:text-slate-400';
    if (status === 'scanned') {
        statusText = t('weixin_scan_scanned');
        statusColor = 'text-primary-500';
    } else if (status === 'expired') {
        statusText = t('weixin_scan_expired');
        statusColor = 'text-amber-500';
    } else if (status === 'confirmed') {
        statusText = t('weixin_scan_success');
        statusColor = 'text-primary-500';
    }

    panel.innerHTML = `
        <div class="flex flex-col items-center">
            <p class="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">${t('weixin_scan_title')}</p>
            <p class="text-xs text-slate-400 dark:text-slate-500 mb-4">${t('weixin_scan_desc')}</p>
            <div class="bg-white p-3 rounded-xl shadow-sm border border-slate-100 dark:border-slate-700 mb-3">
                <img src="${escapeHtml(qrcodeUrl)}" alt="QR Code" class="w-52 h-52" style="image-rendering: pixelated;"/>
            </div>
            <p class="text-xs ${statusColor} mb-1">${statusText}</p>
            <p class="text-xs text-slate-400 dark:text-slate-500">${t('weixin_qr_tip')}</p>
        </div>`;
}

function pollWeixinQrStatus() {
    _weixinQrPollTimer = setTimeout(() => {
        fetch('/api/weixin/qrlogin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'poll' })
        })
        .then(r => r.json())
        .then(data => {
            const panel = document.getElementById('weixin-qr-panel');
            if (!panel) { stopWeixinQrPoll(); return; }

            if (data.status !== 'success') {
                pollWeixinQrStatus();
                return;
            }

            const qrStatus = data.qr_status;
            if (qrStatus === 'confirmed') {
                renderWeixinQr('', 'confirmed');
                panel.innerHTML = `
                    <div class="flex flex-col items-center py-4">
                        <div class="w-12 h-12 rounded-full bg-primary-50 dark:bg-primary-900/30 flex items-center justify-center mb-3">
                            <i class="fas fa-check text-primary-500 text-lg"></i>
                        </div>
                        <p class="text-sm font-medium text-primary-600 dark:text-primary-400">${t('weixin_scan_success')}</p>
                    </div>`;
                connectWeixinAfterQr();
            } else if (qrStatus === 'expired' && (data.qr_image || data.qrcode_url)) {
                renderWeixinQr(data.qr_image || data.qrcode_url, 'waiting');
                pollWeixinQrStatus();
            } else if (qrStatus === 'scaned') {
                const img = panel.querySelector('img');
                const currentSrc = img ? img.src : '';
                renderWeixinQr(currentSrc, 'scanned');
                pollWeixinQrStatus();
            } else {
                pollWeixinQrStatus();
            }
        })
        .catch(() => {
            pollWeixinQrStatus();
        });
    }, 2000);
}

function connectWeixinAfterQr() {
    fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'connect', channel: 'weixin', config: {} })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            const ch = channelsData.find(c => c.name === 'weixin');
            if (ch) ch.active = true;
            setTimeout(() => renderActiveChannels(), 1500);
        }
    })
    .catch(() => {});
}

// =====================================================================
// WeCom Bot QR Auth
// =====================================================================
// NOTE: This is the only remaining external script in the Web Console.
// Tencent's WeCom Bot SDK must be loaded from their official CDN — it
// performs runtime origin/signature checks and will not work if
// self-hosted. The SDK is fetched lazily, only when the user opens the
// "WeCom Bot" channel QR-login flow, so the rest of the console works
// fully offline.
const WECOM_BOT_SDK_URL = 'https://wwcdn.weixin.qq.com/node/wework/js/wecom-aibot-sdk@0.1.0.min.js';
const WECOM_BOT_SOURCE = 'cowagent';
let _wecomSdkLoaded = false;

function ensureWecomSdkLoaded() {
    return new Promise((resolve, reject) => {
        if (_wecomSdkLoaded && window.WecomAIBotSDK) { resolve(); return; }
        if (document.querySelector(`script[src="${WECOM_BOT_SDK_URL}"]`)) {
            _wecomSdkLoaded = true; resolve(); return;
        }
        const s = document.createElement('script');
        s.src = WECOM_BOT_SDK_URL;
        s.onload = () => { _wecomSdkLoaded = true; resolve(); };
        s.onerror = () => reject(new Error('Failed to load WecomAIBotSDK'));
        document.head.appendChild(s);
    });
}

function _wecomBotHasCreds(ch) {
    if (!ch || !ch.fields) return false;
    const idField = ch.fields.find(f => f.key === 'wecom_bot_id');
    const secretField = ch.fields.find(f => f.key === 'wecom_bot_secret');
    return !!(idField && idField.value && secretField && secretField.value);
}

function buildWecomBotPanel(ch) {
    const scanLabel = t('wecom_mode_scan');
    const manualLabel = t('wecom_mode_manual');
    const hasCreds = _wecomBotHasCreds(ch);
    const defaultMode = hasCreds ? 'manual' : 'scan';
    return `
        <div id="wecom-bot-panel" data-default-mode="${defaultMode}">
            <div class="flex items-center justify-center gap-1 mb-5 bg-slate-100 dark:bg-white/5 rounded-lg p-1">
                <button id="wecom-tab-scan" onclick="switchWecomBotMode('scan')"
                    class="flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                           bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm">
                    ${scanLabel}
                </button>
                <button id="wecom-tab-manual" onclick="switchWecomBotMode('manual')"
                    class="flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                           text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">
                    ${manualLabel}
                </button>
            </div>
            <div id="wecom-mode-content"></div>
        </div>`;
}

function switchWecomBotMode(mode) {
    const scanTab = document.getElementById('wecom-tab-scan');
    const manualTab = document.getElementById('wecom-tab-manual');
    const content = document.getElementById('wecom-mode-content');
    const actions = document.getElementById('add-channel-actions');
    if (!scanTab || !manualTab || !content) return;

    const activeClasses = 'bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm';
    const inactiveClasses = 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200';

    if (mode === 'scan') {
        scanTab.className = scanTab.className.replace(/text-slate-500[^\s]*/g, '').replace(/hover:\S+/g, '');
        scanTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${activeClasses}`;
        manualTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${inactiveClasses}`;
        actions.classList.add('hidden');
        content.innerHTML = `
            <div class="flex flex-col items-center py-4">
                <p class="text-sm text-slate-600 dark:text-slate-300 mb-2">${t('wecom_scan_desc')}</p>
                <button onclick="startWecomBotAuth()"
                    class="mt-3 px-6 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium
                           cursor-pointer transition-colors duration-150">
                    <i class="fas fa-qrcode mr-2"></i>${t('wecom_scan_btn')}
                </button>
                <div id="wecom-scan-status" class="mt-3"></div>
            </div>`;
    } else {
        manualTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${activeClasses}`;
        scanTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${inactiveClasses}`;
        const ch = channelsData.find(c => c.name === 'wecom_bot');
        content.innerHTML = `<div class="space-y-4">${buildChannelFieldsHtml('wecom_bot', ch ? ch.fields || [] : [])}</div>`;
        bindSecretFieldEvents(content);
        actions.classList.remove('hidden');
    }
}

function startWecomBotAuth() {
    const statusEl = document.getElementById('wecom-scan-status');
    ensureWecomSdkLoaded().then(() => {
        WecomAIBotSDK.openBotInfoAuthWindow({
            source: WECOM_BOT_SOURCE,
            onCreated: function(bot) {
                if (statusEl) {
                    statusEl.innerHTML = `
                        <div class="flex flex-col items-center py-2">
                            <div class="w-10 h-10 rounded-full bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center mb-2">
                                <i class="fas fa-check text-emerald-500 text-lg"></i>
                            </div>
                            <p class="text-sm font-medium text-emerald-600 dark:text-emerald-400">${t('wecom_scan_success')}</p>
                        </div>`;
                }
                connectWecomBotAfterAuth(bot.botid, bot.secret);
            },
            onError: function(err) {
                if (statusEl) {
                    statusEl.innerHTML = `<p class="text-sm text-red-500">${t('wecom_scan_fail')}: ${err.message || err.code || ''}</p>`;
                }
            }
        });
    }).catch(err => {
        if (statusEl) {
            statusEl.innerHTML = `<p class="text-sm text-red-500">SDK load failed: ${err.message}</p>`;
        }
    });
}

function connectWecomBotAfterAuth(botId, secret) {
    fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'connect',
            channel: 'wecom_bot',
            config: { wecom_bot_id: botId, wecom_bot_secret: secret }
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            const ch = channelsData.find(c => c.name === 'wecom_bot');
            if (ch) {
                ch.active = true;
                (ch.fields || []).forEach(f => {
                    if (f.key === 'wecom_bot_id') f.value = botId;
                    if (f.key === 'wecom_bot_secret') f.value = ChannelsHandler_maskSecret(secret);
                });
            }
            setTimeout(() => renderActiveChannels(), 1500);
        }
    })
    .catch(() => {});
}

function startWecomBotAuthInCard() {
    const statusEl = document.getElementById('wecom-card-scan-status');
    ensureWecomSdkLoaded().then(() => {
        WecomAIBotSDK.openBotInfoAuthWindow({
            source: WECOM_BOT_SOURCE,
            onCreated: function(bot) {
                if (statusEl) {
                    statusEl.innerHTML = `
                        <div class="flex flex-col items-center py-2">
                            <div class="w-10 h-10 rounded-full bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center mb-2">
                                <i class="fas fa-check text-emerald-500 text-lg"></i>
                            </div>
                            <p class="text-sm font-medium text-emerald-600 dark:text-emerald-400">${t('wecom_scan_success')}</p>
                        </div>`;
                }
                connectWecomBotAfterAuth(bot.botid, bot.secret);
            },
            onError: function(err) {
                if (statusEl) {
                    statusEl.innerHTML = `<p class="text-sm text-red-500">${t('wecom_scan_fail')}: ${err.message || err.code || ''}</p>`;
                }
            }
        });
    }).catch(err => {
        if (statusEl) {
            statusEl.innerHTML = `<p class="text-sm text-red-500">SDK load failed: ${err.message}</p>`;
        }
    });
}

// Initialize wecom bot panel with correct default mode when inserted into DOM
document.addEventListener('DOMContentLoaded', function() {
    const observer = new MutationObserver(function() {
        const wecomPanel = document.getElementById('wecom-bot-panel');
        if (wecomPanel && !wecomPanel.dataset.initialized) {
            wecomPanel.dataset.initialized = '1';
            switchWecomBotMode(wecomPanel.dataset.defaultMode || 'scan');
        }
        const feishuPanel = document.getElementById('feishu-panel');
        if (feishuPanel && !feishuPanel.dataset.initialized) {
            feishuPanel.dataset.initialized = '1';
            switchFeishuMode(feishuPanel.dataset.defaultMode || 'scan');
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
});

// =====================================================================
// Feishu One-click App Registration (lark-oapi register_app)
// =====================================================================
let _feishuRegisterPollTimer = null;

function _feishuHasCreds(ch) {
    if (!ch || !ch.fields) return false;
    const idField = ch.fields.find(f => f.key === 'feishu_app_id');
    const secretField = ch.fields.find(f => f.key === 'feishu_app_secret');
    return !!(idField && idField.value && secretField && secretField.value);
}

function buildFeishuPanel(ch, isActive) {
    const scanLabel = t('feishu_mode_scan');
    const manualLabel = t('feishu_mode_manual');
    // 已有凭据时默认进入手动 Tab，方便修改；否则推荐扫码
    const defaultMode = _feishuHasCreds(ch) ? 'manual' : 'scan';
    const activeAttr = isActive ? 'data-active="1"' : '';
    return `
        <div id="feishu-panel" data-default-mode="${defaultMode}" ${activeAttr}>
            <div class="flex items-center justify-center gap-1 mb-5 bg-slate-100 dark:bg-white/5 rounded-lg p-1">
                <button id="feishu-tab-scan" onclick="switchFeishuMode('scan')"
                    class="flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                           bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm">
                    ${scanLabel}
                </button>
                <button id="feishu-tab-manual" onclick="switchFeishuMode('manual')"
                    class="flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                           text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">
                    ${manualLabel}
                </button>
            </div>
            <div id="feishu-mode-content"></div>
        </div>`;
}

function switchFeishuMode(mode) {
    const panel = document.getElementById('feishu-panel');
    const scanTab = document.getElementById('feishu-tab-scan');
    const manualTab = document.getElementById('feishu-tab-manual');
    const content = document.getElementById('feishu-mode-content');
    if (!scanTab || !manualTab || !content) return;

    // 已激活通道卡片中嵌入此 panel 时，没有 add-channel-actions（保存按钮就近渲染）
    const isActive = panel && panel.dataset.active === '1';
    const actions = isActive ? null : document.getElementById('add-channel-actions');

    const activeClasses = 'bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 shadow-sm';
    const inactiveClasses = 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200';

    stopFeishuRegisterPoll();

    if (mode === 'scan') {
        scanTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${activeClasses}`;
        manualTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${inactiveClasses}`;
        if (actions) actions.classList.add('hidden');
        // active 卡片下扫码替换的提示文案，强调"创建新机器人会覆盖现有配置"
        const desc = isActive
            ? t('feishu_scan_replace_desc')
            : t('feishu_scan_desc');
        content.innerHTML = `
            <div id="feishu-scan-panel" class="flex flex-col items-center py-4">
                <p class="text-sm text-slate-600 dark:text-slate-300 mb-3 text-center">${desc}</p>
                <button onclick="startFeishuRegister()"
                    class="mt-2 px-6 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium
                           cursor-pointer transition-colors duration-150">
                    <i class="fas fa-qrcode mr-2"></i>${t('feishu_scan_btn')}
                </button>
                <div id="feishu-scan-status" class="mt-4 w-full"></div>
            </div>`;
    } else {
        manualTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${activeClasses}`;
        scanTab.className = `flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${inactiveClasses}`;
        const ch = channelsData.find(c => c.name === 'feishu');
        const fieldsHtml = buildChannelFieldsHtml('feishu', ch ? ch.fields || [] : []);
        if (isActive) {
            // 已接入卡片：内置保存按钮，复用 saveChannelConfig 走 update 流程
            content.innerHTML = `
                <div class="space-y-4">
                    ${fieldsHtml}
                    <div class="flex items-center justify-end gap-3 pt-1">
                        <span id="ch-status-feishu" class="text-xs text-primary-500 opacity-0 transition-opacity duration-300"></span>
                        <button onclick="saveChannelConfig('feishu')"
                            class="px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white text-sm font-medium
                                   cursor-pointer transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                            id="ch-save-feishu">${t('channels_save')}</button>
                    </div>
                </div>`;
        } else {
            content.innerHTML = `<div class="space-y-4">${fieldsHtml}</div>`;
            if (actions) actions.classList.remove('hidden');
        }
        bindSecretFieldEvents(content);
    }
}

function stopFeishuRegisterPoll() {
    if (_feishuRegisterPollTimer) {
        clearTimeout(_feishuRegisterPollTimer);
        _feishuRegisterPollTimer = null;
    }
}

function startFeishuRegister(targetStatusId) {
    const statusId = targetStatusId || 'feishu-scan-status';
    const statusEl = document.getElementById(statusId);
    if (statusEl) {
        statusEl.innerHTML = `<p class="text-sm text-slate-500 dark:text-slate-400 text-center">${t('feishu_scan_loading')}</p>`;
    }
    stopFeishuRegisterPoll();
    fetch('/api/feishu/register')
        .then(r => r.json())
        .then(data => {
            if (data.status !== 'success') {
                renderFeishuRegisterError(statusId, data.message || t('feishu_scan_fail'));
                return;
            }
            renderFeishuQr(statusId, data.qr_image, data.qrcode_url);
            pollFeishuRegisterStatus(statusId);
        })
        .catch(err => {
            renderFeishuRegisterError(statusId, err.message || t('feishu_scan_fail'));
        });
}

function renderFeishuQr(statusId, qrImage, qrUrl) {
    const statusEl = document.getElementById(statusId);
    if (!statusEl) return;
    const imgHtml = qrImage
        ? `<img src="${qrImage}" alt="QR" class="w-44 h-44 rounded-lg border border-slate-200 dark:border-white/10 bg-white p-2"/>`
        : `<div class="w-44 h-44 rounded-lg border border-dashed border-slate-300 flex items-center justify-center text-xs text-slate-400">QR</div>`;
    statusEl.innerHTML = `
        <div class="flex flex-col items-center gap-3">
            ${imgHtml}
            <p class="text-xs text-amber-500">${t('feishu_scan_waiting')}</p>
            <p class="text-xs text-slate-400 dark:text-slate-500">${t('feishu_scan_tip')}</p>
            ${qrUrl ? `<a href="${qrUrl}" target="_blank" rel="noopener"
                class="text-xs text-blue-500 hover:text-blue-600 underline">${t('feishu_scan_open_link')}</a>` : ''}
        </div>`;
}

function renderFeishuRegisterError(statusId, message) {
    const statusEl = document.getElementById(statusId);
    if (!statusEl) return;
    statusEl.innerHTML = `
        <div class="flex flex-col items-center gap-2 py-2">
            <p class="text-sm text-red-500 text-center">${message}</p>
            <button onclick="startFeishuRegister('${statusId}')"
                class="mt-1 px-4 py-1.5 rounded-md text-xs font-medium
                       bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-slate-200
                       hover:bg-slate-200 dark:hover:bg-white/20 cursor-pointer">
                <i class="fas fa-rotate-right mr-1"></i>${t('feishu_scan_retry')}
            </button>
        </div>`;
}

function pollFeishuRegisterStatus(statusId) {
    stopFeishuRegisterPoll();
    _feishuRegisterPollTimer = setTimeout(() => {
        fetch('/api/feishu/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'poll' })
        })
        .then(r => r.json())
        .then(data => {
            if (data.status !== 'success') {
                renderFeishuRegisterError(statusId, data.message || t('feishu_scan_fail'));
                return;
            }
            const rs = data.register_status;
            if (rs === 'done') {
                const statusEl = document.getElementById(statusId);
                if (statusEl) {
                    statusEl.innerHTML = `
                        <div class="flex flex-col items-center py-2">
                            <div class="w-10 h-10 rounded-full bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center mb-2">
                                <i class="fas fa-check text-emerald-500 text-lg"></i>
                            </div>
                            <p class="text-sm font-medium text-emerald-600 dark:text-emerald-400">${t('feishu_scan_success')}</p>
                        </div>`;
                }
                connectFeishuAfterRegister(data.app_id, data.app_secret);
            } else if (rs === 'expired') {
                renderFeishuRegisterError(statusId, t('feishu_scan_expired'));
            } else if (rs === 'denied') {
                renderFeishuRegisterError(statusId, t('feishu_scan_denied'));
            } else if (rs === 'error') {
                renderFeishuRegisterError(statusId, data.message || t('feishu_scan_fail'));
            } else {
                pollFeishuRegisterStatus(statusId);
            }
        })
        .catch(() => {
            pollFeishuRegisterStatus(statusId);
        });
    }, 2000);
}

function connectFeishuAfterRegister(appId, appSecret) {
    fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'connect',
            channel: 'feishu',
            config: { feishu_app_id: appId, feishu_app_secret: appSecret }
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            const ch = channelsData.find(c => c.name === 'feishu');
            if (ch) {
                ch.active = true;
                (ch.fields || []).forEach(f => {
                    if (f.key === 'feishu_app_id') f.value = appId;
                    if (f.key === 'feishu_app_secret') f.value = ChannelsHandler_maskSecret(appSecret);
                });
            }
            setTimeout(() => renderActiveChannels(), 1500);
        }
    })
    .catch(() => {});
}

// =====================================================================
// Scheduler View
// =====================================================================
let tasksLoaded = false;
function loadTasksView() {
    if (tasksLoaded) return;
    fetch('/api/scheduler').then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        const emptyEl = document.getElementById('tasks-empty');
        const listEl = document.getElementById('tasks-list');
        const allTasks = data.tasks || [];
        // Only show active (enabled) tasks
        const tasks = allTasks.filter(t => t.enabled !== false);
        if (tasks.length === 0) {
            emptyEl.querySelector('p').textContent = currentLang === 'zh' ? '暂无定时任务' : 'No scheduled tasks';
            return;
        }
        emptyEl.classList.add('hidden');
        listEl.classList.remove('hidden');
        listEl.innerHTML = '';

        tasks.forEach(task => {
            const card = document.createElement('div');
            card.className = 'bg-white dark:bg-[#1A1A1A] rounded-xl border border-slate-200 dark:border-white/10 p-4';
            const typeLabel = task.type === 'cron'
                ? `<span class="text-xs font-mono text-slate-400">${escapeHtml(task.cron || '')}</span>`
                : `<span class="text-xs text-slate-400">${escapeHtml(task.type || 'once')}</span>`;
            let nextRun = '--';
            if (task.next_run_at) {
                // next_run_at is an ISO string, not a Unix timestamp
                const d = new Date(task.next_run_at);
                if (!isNaN(d.getTime())) nextRun = d.toLocaleString();
            }
            card.innerHTML = `
                <div class="flex items-center gap-2 mb-2">
                    <span class="w-2 h-2 rounded-full bg-primary-400"></span>
                    <span class="font-medium text-sm text-slate-700 dark:text-slate-200">${escapeHtml(task.name || task.id || '--')}</span>
                    <div class="flex-1"></div>
                    ${typeLabel}
                </div>
                <p class="text-xs text-slate-500 dark:text-slate-400 mb-2 line-clamp-2">${escapeHtml(task.prompt || task.description || '')}</p>
                <div class="flex items-center gap-4 text-xs text-slate-400 dark:text-slate-500">
                    <span><i class="fas fa-clock mr-1"></i>${currentLang === 'zh' ? '下次执行' : 'Next run'}: ${nextRun}</span>
                </div>`;
            listEl.appendChild(card);
        });
        tasksLoaded = true;
    }).catch(() => {});
}

// =====================================================================
// Logs View
// =====================================================================
let logEventSource = null;

function logLevelClass(line) {
    if (/\[CRITICAL\]/.test(line)) return 'log-line-critical';
    if (/\[ERROR\]/.test(line))    return 'log-line-error';
    if (/\[WARNING\]/.test(line))  return 'log-line-warning';
    if (/\[INFO\]/.test(line))     return 'log-line-info';
    if (/\[DEBUG\]/.test(line))    return 'log-line-debug';
    return '';
}

function getHiddenLevels() {
    const hidden = new Set();
    document.querySelectorAll('.log-filter-cb').forEach(function(cb) {
        if (!cb.checked) hidden.add('log-line-' + cb.dataset.level);
    });
    return hidden;
}

function applyLogFilter() {
    const hidden = getHiddenLevels();
    document.querySelectorAll('#log-output .log-line').forEach(function(span) {
        const level = span.classList[1] || '';
        span.style.display = hidden.has(level) ? 'none' : '';
    });
}

function appendLogLines(output, text) {
    const hidden = getHiddenLevels();
    let lastLevelClass = '';
    const lines = text.split('\n');
    lines.forEach(function(line, i) {
        if (i === lines.length - 1 && line === '') return;
        const span = document.createElement('span');
        const levelClass = logLevelClass(line) || lastLevelClass;
        if (logLevelClass(line)) lastLevelClass = levelClass;
        span.className = 'log-line ' + levelClass;
        span.textContent = line + '\n';
        if (hidden.has(levelClass)) span.style.display = 'none';
        output.appendChild(span);
    });
}

document.addEventListener('change', function(e) {
    if (e.target.classList.contains('log-filter-cb')) applyLogFilter();
});

function startLogStream() {
    if (logEventSource) return;
    const output = document.getElementById('log-output');
    output.innerHTML = '';

    logEventSource = new EventSource('/api/logs');
    logEventSource.onmessage = function(e) {
        let item;
        try { item = JSON.parse(e.data); } catch (_) { return; }

        if (item.type === 'init') {
            output.innerHTML = '';
            appendLogLines(output, item.content || '');
            output.scrollTop = output.scrollHeight;
        } else if (item.type === 'line') {
            appendLogLines(output, item.content);
            output.scrollTop = output.scrollHeight;
        } else if (item.type === 'error') {
            output.textContent = item.message || 'Error loading logs';
        }
    };
    logEventSource.onerror = function() {
        logEventSource.close();
        logEventSource = null;
    };
}

function stopLogStream() {
    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }
}

// =====================================================================
// View Navigation Hook
// =====================================================================
const _origNavigateTo = navigateTo;
navigateTo = function(viewId) {
    // Stop log stream when leaving logs view
    if (currentView === 'logs' && viewId !== 'logs') stopLogStream();

    _origNavigateTo(viewId);

    // Lazy-load view data
    if (viewId === 'config') loadConfigView();
    else if (viewId === 'skills') loadSkillsView();
    else if (viewId === 'channels') loadChannelsView();
    else if (viewId === 'logs') startLogStream();
};

// =====================================================================
// Knowledge View
// =====================================================================
let _knowledgeTreeData = [];
let _knowledgeRootFiles = [];
let _knowledgeCurrentFile = null;
let _knowledgeGraphLoaded = false;

function loadKnowledgeView() {
    // Reset to docs tab
    switchKnowledgeTab('docs');
    _knowledgeGraphLoaded = false;
    _knowledgeCurrentFile = null;

    fetch('/api/knowledge/list').then(r => r.json()).then(data => {
        if (data.status !== 'success') return;

        const emptyEl = document.getElementById('knowledge-empty');
        const docsPanel = document.getElementById('knowledge-panel-docs');
        const statsEl = document.getElementById('knowledge-stats');

        const tree = data.tree || [];
        const rootFiles = data.root_files || [];
        _knowledgeTreeData = tree;
        _knowledgeRootFiles = rootFiles;
        const stats = data.stats || {};
        const totalPages = stats.pages || 0;
        const sizeStr = stats.size < 1024 ? stats.size + ' B' : (stats.size / 1024).toFixed(1) + ' KB';

        statsEl.textContent = totalPages + ' pages · ' + sizeStr;

        if (totalPages === 0) {
            emptyEl.querySelector('p').textContent = t('knowledge_empty_hint');
            const guideEl = document.getElementById('knowledge-empty-guide');
            if (guideEl) guideEl.classList.remove('hidden');
            emptyEl.classList.remove('hidden');
            docsPanel.classList.add('hidden');
            return;
        }
        emptyEl.classList.add('hidden');
        docsPanel.classList.remove('hidden');

        renderKnowledgeTree(tree, rootFiles);

        // Auto-select the first file (desktop only)
        if (window.innerWidth >= 768) {
            const firstFile = rootFiles.length > 0 ? rootFiles[0] : null;
            const firstGroup = !firstFile ? tree.find(g => g.files && g.files.length > 0) : null;
            if (firstFile) {
                openKnowledgeFile(firstFile.name, firstFile.title);
            } else if (firstGroup) {
                const gf = firstGroup.files[0];
                openKnowledgeFile(firstGroup.dir + '/' + gf.name, gf.title);
            }
        } else {
            document.getElementById('knowledge-content-placeholder').classList.add('hidden');
            document.getElementById('knowledge-content-viewer').classList.add('hidden');
        }
    }).catch(() => {});
}

function renderKnowledgeTree(tree, rootFilesOrFilter, filter) {
    const container = document.getElementById('knowledge-tree');
    container.innerHTML = '';
    let rootFiles, lowerFilter;
    if (typeof rootFilesOrFilter === 'string') {
        rootFiles = _knowledgeRootFiles;
        lowerFilter = (rootFilesOrFilter || '').toLowerCase();
    } else {
        rootFiles = rootFilesOrFilter || _knowledgeRootFiles;
        lowerFilter = (filter || '').toLowerCase();
    }
    (rootFiles || []).forEach(f => {
        if (lowerFilter && !f.title.toLowerCase().includes(lowerFilter) && !f.name.toLowerCase().includes(lowerFilter)) return;
        const fbtn = document.createElement('button');
        fbtn.className = 'knowledge-tree-file' + (_knowledgeCurrentFile === f.name ? ' active' : '');
        fbtn.dataset.path = f.name;
        fbtn.innerHTML = `<i class="fas fa-file-lines text-[10px] text-slate-400"></i><span class="truncate">${escapeHtml(f.title)}</span>`;
        fbtn.onclick = () => openKnowledgeFile(f.name, f.title);
        container.appendChild(fbtn);
    });
    _renderKnowledgeGroups(container, tree, '', lowerFilter, 0);
}

function _renderKnowledgeGroups(container, groups, parentPath, lowerFilter, depth) {
    const indent = depth * 12;
    groups.forEach(group => {
        const groupPath = parentPath ? parentPath + '/' + group.dir : group.dir;
        const files = (group.files || []).filter(f =>
            !lowerFilter || f.title.toLowerCase().includes(lowerFilter) || f.name.toLowerCase().includes(lowerFilter)
        );
        const children = group.children || [];
        const hasMatchingChildren = lowerFilter ? _hasFilterMatch(children, lowerFilter) : children.length > 0;
        if (files.length === 0 && !hasMatchingChildren && lowerFilter) return;

        const div = document.createElement('div');
        div.className = 'knowledge-tree-group open';

        const fileCount = _countFiles(group);
        const btn = document.createElement('button');
        btn.className = 'knowledge-tree-group-btn';
        btn.style.paddingLeft = (8 + indent) + 'px';
        btn.innerHTML = `<i class="fas fa-chevron-right chevron"></i><i class="fas fa-folder text-amber-400 text-[11px]"></i><span>${escapeHtml(group.dir)}</span><span class="ml-auto text-[10px] text-slate-400">${fileCount}</span>`;
        btn.onclick = () => div.classList.toggle('open');
        div.appendChild(btn);

        const items = document.createElement('div');
        items.className = 'knowledge-tree-group-items';
        files.forEach(f => {
            const fbtn = document.createElement('button');
            const fpath = groupPath + '/' + f.name;
            fbtn.className = 'knowledge-tree-file' + (_knowledgeCurrentFile === fpath ? ' active' : '');
            fbtn.dataset.path = fpath;
            fbtn.style.paddingLeft = (24 + indent) + 'px';
            fbtn.innerHTML = `<i class="fas fa-file-lines text-[10px] text-slate-400"></i><span class="truncate">${escapeHtml(f.title)}</span>`;
            fbtn.onclick = () => openKnowledgeFile(fpath, f.title);
            items.appendChild(fbtn);
        });
        if (children.length > 0) {
            _renderKnowledgeGroups(items, children, groupPath, lowerFilter, depth + 1);
        }
        div.appendChild(items);
        container.appendChild(div);
    });
}

function _hasFilterMatch(groups, lowerFilter) {
    for (const g of groups) {
        for (const f of (g.files || [])) {
            if (f.title.toLowerCase().includes(lowerFilter) || f.name.toLowerCase().includes(lowerFilter)) return true;
        }
        if (_hasFilterMatch(g.children || [], lowerFilter)) return true;
    }
    return false;
}

function _countFiles(group) {
    let count = (group.files || []).length;
    for (const child of (group.children || [])) {
        count += _countFiles(child);
    }
    return count;
}

function filterKnowledgeTree(query) {
    renderKnowledgeTree(_knowledgeTreeData, _knowledgeRootFiles, query);
}

function resolveKnowledgePath(currentFilePath, relativeHref) {
    // currentFilePath: e.g. "concepts/mcp-protocol.md"
    // relativeHref: e.g. "../entities/openai.md"
    const parts = currentFilePath.split('/');
    parts.pop(); // remove filename, keep directory
    const segments = [...parts, ...relativeHref.split('/')];
    const resolved = [];
    for (const seg of segments) {
        if (seg === '..') resolved.pop();
        else if (seg !== '.' && seg !== '') resolved.push(seg);
    }
    return resolved.join('/');
}

function bindKnowledgeLinks(container, currentFilePath) {
    container.querySelectorAll('a').forEach(a => {
        const href = a.getAttribute('href');
        if (!href || !href.endsWith('.md')) return;
        // Skip absolute URLs
        if (/^https?:\/\//.test(href)) return;

        a.addEventListener('click', (e) => {
            e.preventDefault();
            const resolved = resolveKnowledgePath(currentFilePath, href);
            const linkTitle = a.textContent.trim() || resolved.replace(/\.md$/, '').split('/').pop();
            openKnowledgeFile(resolved, linkTitle);
        });
        a.style.cursor = 'pointer';
        a.classList.add('text-primary-500', 'hover:underline');
    });
}

function bindChatKnowledgeLinks(container) {
    return;
}

function _findKnowledgeFileByName(filename) {
    for (const f of _knowledgeRootFiles) {
        if (f.name === filename) return { path: f.name, title: f.title };
    }
    return _searchFileInGroups(_knowledgeTreeData, '', filename);
}

function _searchFileInGroups(groups, parentPath, filename) {
    for (const group of groups) {
        const groupPath = parentPath ? parentPath + '/' + group.dir : group.dir;
        for (const f of (group.files || [])) {
            if (f.name === filename) {
                return { path: groupPath + '/' + f.name, title: f.title };
            }
        }
        const found = _searchFileInGroups(group.children || [], groupPath, filename);
        if (found) return found;
    }
    return null;
}

function openKnowledgeFile(path, title) {
    _knowledgeCurrentFile = path;
    // Update active state in tree via data-path
    document.querySelectorAll('.knowledge-tree-file').forEach(el => {
        el.classList.toggle('active', el.dataset.path === path);
    });

    // Immediately hide placeholder
    document.getElementById('knowledge-content-placeholder').classList.add('hidden');

    fetch(`/api/knowledge/read?path=${encodeURIComponent(path)}`).then(r => r.json()).then(data => {
        if (data.status !== 'success') return;
        const viewer = document.getElementById('knowledge-content-viewer');
        document.getElementById('knowledge-viewer-title').textContent = title;
        document.getElementById('knowledge-viewer-path').textContent = path;
        const bodyEl = document.getElementById('knowledge-viewer-body');
        bodyEl.innerHTML = renderMarkdown(data.content || '');
        viewer.classList.remove('hidden');
        applyHighlighting(viewer);
        bindKnowledgeLinks(bodyEl, path);

        // Mobile: hide sidebar, show content
        if (window.innerWidth < 768) {
            document.getElementById('knowledge-sidebar').classList.add('hidden');
        }
    }).catch(() => {});
}

function knowledgeMobileBack() {
    document.getElementById('knowledge-sidebar').classList.remove('hidden');
    document.getElementById('knowledge-content-viewer').classList.add('hidden');
}

function switchKnowledgeTab(tab) {
    document.querySelectorAll('.knowledge-tab').forEach(el => el.classList.remove('active'));
    document.getElementById('knowledge-tab-' + tab).classList.add('active');

    const docsPanel = document.getElementById('knowledge-panel-docs');
    const graphPanel = document.getElementById('knowledge-panel-graph');

    if (tab === 'docs') {
        docsPanel.classList.remove('hidden');
        graphPanel.classList.add('hidden');
    } else {
        docsPanel.classList.add('hidden');
        graphPanel.classList.remove('hidden');
        if (!_knowledgeGraphLoaded) {
            loadKnowledgeGraph();
        }
    }
}

let _d3LoadPromise = null;

function ensureD3Loaded() {
    if (window.d3) return Promise.resolve(window.d3);
    if (_d3LoadPromise) return _d3LoadPromise;
    _d3LoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'assets/vendor/d3/d3.min.js';
        script.async = true;
        script.onload = () => resolve(window.d3);
        script.onerror = () => reject(new Error('Failed to load d3'));
        document.head.appendChild(script);
    });
    return _d3LoadPromise;
}

function loadKnowledgeGraph() {
    _knowledgeGraphLoaded = true;
    const container = document.getElementById('knowledge-graph-container');
    container.innerHTML = '<div class="flex items-center justify-center h-full text-slate-400 text-sm"><i class="fas fa-spinner fa-spin mr-2"></i>Loading graph...</div>';

    Promise.all([
        ensureD3Loaded(),
        fetch('/api/knowledge/graph').then(r => r.json()),
    ]).then(([, data]) => {
        const nodes = data.nodes || [];
        const links = data.links || [];
        if (nodes.length === 0) {
            container.innerHTML = `<div class="flex flex-col items-center justify-center h-full text-slate-400"><i class="fas fa-diagram-project text-3xl mb-3 opacity-40"></i><p class="text-sm">${t('knowledge_empty_hint')}</p></div>`;
            return;
        }
        container.innerHTML = '';
        renderKnowledgeGraph(container, nodes, links);
    }).catch(() => {
        container.innerHTML = '<div class="flex items-center justify-center h-full text-slate-400 text-sm">Failed to load graph</div>';
    });
}

function renderKnowledgeGraph(container, nodes, links) {
    const width = container.clientWidth;
    const height = container.clientHeight || 600;

    const categories = [...new Set(nodes.map(n => n.category))];
    const colorScale = d3.scaleOrdinal(d3.schemeTableau10).domain(categories);

    // Connection count for sizing
    const connCount = {};
    nodes.forEach(n => connCount[n.id] = 0);
    links.forEach(l => {
        connCount[l.source] = (connCount[l.source] || 0) + 1;
        connCount[l.target] = (connCount[l.target] || 0) + 1;
    });

    const svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height);

    const g = svg.append('g');

    // Zoom with adaptive label visibility
    let currentZoomScale = 1;
    const zoom = d3.zoom()
        .scaleExtent([0.2, 5])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
            currentZoomScale = event.transform.k;
            updateLabelVisibility();
        });
    svg.call(zoom);

    function updateLabelVisibility() {
        if (!label) return;
        if (currentZoomScale < 0.8) {
            label.attr('opacity', 0);
        } else {
            const baseFontSize = Math.min(12, 10 / Math.max(currentZoomScale * 0.7, 0.5));
            label.attr('opacity', 1).attr('font-size', baseFontSize);
        }
    }

    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(90))
        .force('charge', d3.forceManyBody().strength(-180))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('x', d3.forceX(width / 2).strength(0.06))
        .force('y', d3.forceY(height / 2).strength(0.06))
        .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 30));

    function getNodeRadius(d) {
        return Math.max(5, Math.min(16, 5 + (connCount[d.id] || 0) * 2));
    }

    const link = g.append('g')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('stroke', '#94a3b8')
        .attr('stroke-opacity', 0.3)
        .attr('stroke-width', 1);

    const node = g.append('g')
        .selectAll('circle')
        .data(nodes)
        .join('circle')
        .attr('r', d => getNodeRadius(d))
        .attr('fill', d => colorScale(d.category))
        .attr('stroke', '#fff')
        .attr('stroke-width', 1.5)
        .style('cursor', 'pointer')
        .call(d3.drag()
            .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
            .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
            .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
        );

    const label = g.append('g')
        .selectAll('text')
        .data(nodes)
        .join('text')
        .text(d => d.label.length > 15 ? d.label.slice(0, 14) + '…' : d.label)
        .attr('font-size', 9)
        .attr('dx', d => getNodeRadius(d) + 4)
        .attr('dy', 3)
        .attr('fill', '#64748b')
        .style('pointer-events', 'none');

    // Tooltip
    const tooltip = document.createElement('div');
    tooltip.className = 'knowledge-graph-tooltip';
    container.style.position = 'relative';
    container.appendChild(tooltip);

    node.on('mouseover', (event, d) => {
        tooltip.textContent = d.label + ' (' + d.category + ')';
        tooltip.style.opacity = '1';
        tooltip.style.left = (event.offsetX + 12) + 'px';
        tooltip.style.top = (event.offsetY - 8) + 'px';
        // Highlight connections
        link.attr('stroke-opacity', l => (l.source.id === d.id || l.target.id === d.id) ? 0.8 : 0.1);
        node.attr('opacity', n => n.id === d.id || links.some(l => (l.source.id === d.id && l.target.id === n.id) || (l.target.id === d.id && l.source.id === n.id)) ? 1 : 0.2);
        label.attr('opacity', n => n.id === d.id || links.some(l => (l.source.id === d.id && l.target.id === n.id) || (l.target.id === d.id && l.source.id === n.id)) ? 1 : 0.1);
    }).on('mousemove', (event) => {
        tooltip.style.left = (event.offsetX + 12) + 'px';
        tooltip.style.top = (event.offsetY - 8) + 'px';
    }).on('mouseout', () => {
        tooltip.style.opacity = '0';
        link.attr('stroke-opacity', 0.3);
        node.attr('opacity', 1);
        label.attr('opacity', 1);
    }).on('click', (event, d) => {
        // Switch to docs tab and open the file
        switchKnowledgeTab('docs');
        openKnowledgeFile(d.id, d.label);
    });

    simulation.on('tick', () => {
        link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
        node.attr('cx', d => d.x).attr('cy', d => d.y);
        label.attr('x', d => d.x).attr('y', d => d.y);
    });

    // Auto fit-to-view when simulation settles
    simulation.on('end', () => {
        const pad = 16;
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        nodes.forEach(n => {
            if (n.x < x0) x0 = n.x;
            if (n.y < y0) y0 = n.y;
            if (n.x > x1) x1 = n.x;
            if (n.y > y1) y1 = n.y;
        });
        const bw = x1 - x0 + pad * 2;
        const bh = y1 - y0 + pad * 2;
        if (bw > 0 && bh > 0) {
            const scale = Math.min(width / bw, height / bh, 4);
            const tx = width / 2 - (x0 + x1) / 2 * scale;
            const ty = height / 2 - (y0 + y1) / 2 * scale;
            svg.transition().duration(500).call(
                zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale)
            );
        }
    });

    // Legend
    const legendDiv = document.createElement('div');
    legendDiv.className = 'knowledge-graph-legend';
    categories.forEach(cat => {
        const item = document.createElement('span');
        item.className = 'knowledge-graph-legend-item';
        item.innerHTML = `<span class="knowledge-graph-legend-dot" style="background:${colorScale(cat)}"></span>${escapeHtml(cat)}`;
        legendDiv.appendChild(item);
    });
    container.appendChild(legendDiv);
}

// =====================================================================
// Authentication
// =====================================================================
function toggleLoginPassword() {
    const input = document.getElementById('login-password');
    const icon = document.querySelector('#login-toggle-pwd i');
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('fa-eye', 'fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.replace('fa-eye-slash', 'fa-eye');
    }
}
window.toggleLoginPassword = toggleLoginPassword;

function redirectToLogin(nextPath = `${window.location.pathname}${window.location.search}`) {
    if (!nextPath || nextPath === '/login' || nextPath.startsWith('/login?')) {
        nextPath = '/chat';
    }
    window.location.href = `/login?next=${encodeURIComponent(nextPath)}`;
}

function showLoginScreen() {
    const overlay = document.getElementById('login-overlay');
    if (!overlay) return;
    overlay.classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');

    const subtitle = document.getElementById('login-subtitle');
    const loginBtn = document.getElementById('login-btn');
    if (currentLang === 'en') {
        subtitle.textContent = 'Enter password to access the console';
        loginBtn.textContent = 'Login';
    } else {
        subtitle.textContent = '请输入密码以访问控制台';
        loginBtn.textContent = '登录';
    }

    const form = document.getElementById('login-form');
    const usernameInput = document.getElementById('login-username');
    const pwdInput = document.getElementById('login-password');
    (usernameInput || pwdInput).focus();

    form.onsubmit = function(e) {
        e.preventDefault();
        const pwd = pwdInput.value;
        if (!pwd) return;
        const btn = document.getElementById('login-btn');
        const errEl = document.getElementById('login-error');
        btn.disabled = true;
        errEl.classList.add('hidden');

        fetch('/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: usernameInput?.value || '', password: pwd})
        }).then(r => r.json()).then(data => {
            if (data.status === 'success') {
                currentConsoleAuthenticated = true;
                currentInvestmentAdmin = data.investment_admin || currentInvestmentAdmin;
                updateAuthUserSummary(currentInvestmentAdmin);
                overlay.classList.add('hidden');
                document.getElementById('app').classList.remove('hidden');
                initApp();
            } else {
                errEl.textContent = currentLang === 'zh' ? '密码错误' : 'Wrong password';
                errEl.classList.remove('hidden');
                pwdInput.value = '';
                (usernameInput || pwdInput).focus();
            }
            btn.disabled = false;
        }).catch(() => {
            errEl.textContent = currentLang === 'zh' ? '网络错误，请重试' : 'Network error, please retry';
            errEl.classList.remove('hidden');
            btn.disabled = false;
        });
        return false;
    };
}

function investmentAdminRoleLabel(role) {
    const key = `role_${role || ''}`;
    return t(key) === key ? (role || t('auth_logged_in')) : t(key);
}

function updateAuthUserSummary(admin) {
    const summary = document.getElementById('auth-user-summary');
    const nameEl = document.getElementById('auth-user-name');
    const roleEl = document.getElementById('auth-user-role');
    const logoutBtn = document.getElementById('auth-logout-btn');
    const showAuthControls = currentConsoleAuthenticated || Boolean(admin);
    if (logoutBtn) {
        logoutBtn.setAttribute('data-tooltip', t('auth_logout'));
        logoutBtn.setAttribute('title', t('auth_logout'));
        logoutBtn.classList.toggle('hidden', !showAuthControls);
    }
    if (!summary || !nameEl || !roleEl) return;
    if (!showAuthControls) {
        summary.classList.add('hidden');
        summary.classList.remove('sm:flex');
        nameEl.textContent = '';
        roleEl.textContent = '';
        return;
    }
    summary.classList.remove('hidden');
    summary.classList.add('sm:flex');
    nameEl.textContent = admin?.username || '智能投研辅助系统';
    roleEl.textContent = admin ? investmentAdminRoleLabel(admin.role) : t('auth_logged_in');
}

async function logoutConsole() {
    const btn = document.getElementById('auth-logout-btn');
    if (btn) btn.disabled = true;
    try {
        await fetch('/auth/logout', { method: 'POST' });
    } finally {
        currentConsoleAuthenticated = false;
        currentInvestmentAdmin = null;
        updateAuthUserSummary(null);
        redirectToLogin('/chat');
    }
}
window.logoutConsole = logoutConsole;

// Intercept 401 responses globally to show login screen on session expiry
const _originalFetch = window.fetch;
window.fetch = function(...args) {
    return _originalFetch.apply(this, args).then(response => {
        if (response.status === 401) {
            const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
            if (!url.startsWith('/auth/')) {
                redirectToLogin();
            }
        }
        return response;
    });
};

function initApp() {
    applyI18n();
    _applyInputTooltips();
    _restoreSessionPanel();
    loadInvestmentAdminSession().catch(() => {});

    fetch('/api/version').then(r => r.json()).then(data => {
        APP_VERSION = `v${data.version}`;
    }).catch(() => {
        APP_VERSION = '';
    });
    chatInput.focus();
}

// =====================================================================
// Initialization
// =====================================================================
applyTheme();
applyI18n();

fetch('/auth/check').then(r => r.json()).then(data => {
    if (data.auth_required && !data.authenticated) {
        redirectToLogin();
    } else {
        currentConsoleAuthenticated = Boolean(data.auth_required && data.authenticated);
        currentInvestmentAdmin = data.investment_admin || currentInvestmentAdmin;
        initApp();
    }
}).catch(() => {
    initApp();
});

requestAnimationFrame(() => {
    document.body.classList.add('transition-colors', 'duration-200');
});
