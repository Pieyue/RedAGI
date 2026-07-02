import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

type Lang = 'zh' | 'en';

interface I18nCtx {
  lang: Lang;
  t: (key: string) => string;
  toggleLang: () => void;
}

const I18nContext = createContext<I18nCtx>({ lang: 'zh', t: (k) => k, toggleLang: () => {} });

export function useI18n() {
  return useContext(I18nContext);
}

/* ── 翻译表 ── */
const translations: Record<string, Record<Lang, string>> = {
  // ── Login ──
  'login.subtitle':        { zh: 'AI 红队作战系统',        en: 'AI Red Team System' },
  'login.username':        { zh: '用户名',              en: 'Username' },
  'login.password':        { zh: '密码',                en: 'Password' },
  'login.submit':          { zh: '登录',                en: 'Sign In' },
  'login.error_required':  { zh: '请输入用户名和密码',   en: 'Please enter username and password' },
  'login.error_fail':      { zh: '登录失败，请重试',     en: 'Login failed, please retry' },

  // ── Sidebar ──
  'sidebar.new_task':      { zh: '新建任务',            en: 'New Task' },
  'sidebar.no_sessions':   { zh: '暂无任务会话',         en: 'No sessions yet' },
  'sidebar.delete_title':  { zh: '删除会话',            en: 'Delete Session' },
  'sidebar.delete_confirm':{ zh: '此操作不可逆，将永久删除该会话及其所有关联数据（对话记录、任务进度、Agent日志等）。确定要继续吗？', en: 'This action is irreversible. It will permanently delete the session and all associated data (chat logs, task progress, agent logs, etc.). Continue?' },
  'sidebar.cancel':        { zh: '取消',                en: 'Cancel' },
  'sidebar.confirm':       { zh: '确定',                en: 'Confirm' },
  'sidebar.deleting':      { zh: '清理中……',            en: 'Cleaning...' },
  'sidebar.logout':        { zh: '退出',                en: 'Logout' },
  'sidebar.running':       { zh: '运行中',              en: 'Running' },
  'sidebar.stopped':       { zh: '已停止',              en: 'Stopped' },
  'sidebar.idle':          { zh: '空闲',                en: 'Idle' },
  'sidebar.just_now':      { zh: '刚刚',                en: 'Just now' },
  'sidebar.min_ago':       { zh: '分钟前',              en: 'm ago' },
  'sidebar.hour_ago':      { zh: '小时前',              en: 'h ago' },

  // ── ChatArea ──
  'chat.title_active':     { zh: 'Leader Agent 对话',   en: 'Leader Agent Chat' },
  'chat.title_idle':       { zh: '选择或创建一个任务会话', en: 'Select or create a task session' },
  'chat.connected':        { zh: '已连接',              en: 'Connected' },
  'chat.disconnected':     { zh: '未连接',              en: 'Disconnected' },
  'chat.placeholder_title':{ zh: '标题',                en: 'Title' },
  'chat.placeholder_obj':  { zh: '目标',                en: 'Objective' },
  'chat.start_task':       { zh: '开始任务',            en: 'Start Task' },
  'chat.initializing':     { zh: '初始化……',            en: 'Initializing...' },
  'chat.init_session':     { zh: '正在初始化会话……',     en: 'Initializing session...' },
  'chat.placeholder_input':{ zh: '输入消息，Enter 发送，Shift+Enter 换行', en: 'Type a message, Enter to send, Shift+Enter for new line' },
  'chat.placeholder_disabled':{ zh: '请先创建会话',      en: 'Please create a session first' },
  'chat.send':             { zh: '发送',                en: 'Send' },
  'chat.stop':             { zh: '停止',                en: 'Stop' },
  'chat.thinking':         { zh: 'Leader 思考中...',     en: 'Leader is thinking...' },

  // ── Welcome messages (Try Harder stays the same) ──
  'chat.welcome_1':        { zh: 'Try Harder',                          en: 'Try Harder' },
  'chat.welcome_2':        { zh: '下达你的进攻指示',                      en: 'Issue your attack orders' },
  'chat.welcome_3':        { zh: '这次的任务是什么？',                     en: 'What is the mission this time?' },
  'chat.welcome_4':        { zh: '自主战术规划并渗透',                     en: 'Autonomous tactical planning & penetration' },
  'chat.welcome_5':        { zh: '欢迎使用RedAGI',                       en: 'Welcome to RedAGI' },
  'chat.welcome_6':        { zh: '遵守法律',                              en: 'Stay within the law' },
  'chat.welcome_7':        { zh: '进攻是为了更好地防守',                   en: 'Attack to defend better' },

  // ── RightPanel ──
  'panel.progress':        { zh: '进度',                en: 'Progress' },
  'panel.history':         { zh: '命令',                en: 'Commands' },
  'panel.tools':           { zh: '工具',                en: 'Tools' },
  'panel.conversations':   { zh: '对话',                en: 'Chat' },
  'panel.team':            { zh: '团队',                en: 'Team' },
  'panel.select_session':  { zh: '请先选择会话',         en: 'Please select a session' },
  'panel.no_progress':     { zh: '暂无进度记录',         en: 'No progress records' },
  'panel.no_commands':     { zh: '暂无命令记录',         en: 'No command records' },
  'panel.no_conversations':{ zh: '暂无 Agent 对话',     en: 'No agent conversations' },
  'panel.no_tools':        { zh: '暂无工具执行记录',     en: 'No tool execution records' },
  'panel.no_team':         { zh: '团队尚未初始化',       en: 'Team not initialized' },
  'panel.status_busy':     { zh: '忙碌',                en: 'Busy' },
  'panel.status_idle':     { zh: '空闲',                en: 'Idle' },

  // ── Dashboard ──
  'dashboard.create_fail': { zh: '创建任务失败',         en: 'Failed to create task' },
  'dashboard.init_fail':   { zh: '会话初始化失败，请重试', en: 'Session init failed, please retry' },
};

/* ── Provider ── */
export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const saved = localStorage.getItem('lang');
    return (saved === 'en' ? 'en' : 'zh');
  });

  const toggleLang = useCallback(() => {
    setLang((prev) => {
      const next = prev === 'zh' ? 'en' : 'zh';
      localStorage.setItem('lang', next);
      return next;
    });
  }, []);

  const t = useCallback(
    (key: string) => translations[key]?.[lang] ?? key,
    [lang],
  );

  return (
    <I18nContext.Provider value={{ lang, t, toggleLang }}>
      {children}
    </I18nContext.Provider>
  );
}
