import { useState, useEffect, useCallback } from 'react';
import { ListTodo, Terminal, MessageCircle, Wrench, Users, Crown, Eye, Brain, Swords, FileText } from 'lucide-react';
import {
  getProgress,
  getCommandHistory,
  getAgentMessages,
  getToolExecutions,
  getAgentStatuses,
} from '../api/monitor';
import { useI18n } from '../i18n';
import type {
  ProgressItem,
  CommandHistoryItem,
  AgentMessageItem,
  ToolExecutionItem,
  AgentStatusItem,
} from '../api/monitor';

interface Props {
  sessionId: string | null;
  style?: React.CSSProperties;
}

const TAB_KEYS = ['progress', 'history', 'tools', 'conversations', 'team'] as const;
type TabKey = (typeof TAB_KEYS)[number];

export default function RightPanel({ sessionId, style }: Props) {
  const [tab, setTab] = useState<TabKey>('progress');
  const { t } = useI18n();

  return (
    <div className="right-panel" style={style}>
      <div className="panel-tabs">
        <button
          className={`panel-tab ${tab === 'progress' ? 'active' : ''}`}
          onClick={() => setTab('progress')}
        >
          <ListTodo size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          {t('panel.progress')}
        </button>
        <button
          className={`panel-tab ${tab === 'history' ? 'active' : ''}`}
          onClick={() => setTab('history')}
        >
          <Terminal size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          {t('panel.history')}
        </button>
        <button
          className={`panel-tab ${tab === 'tools' ? 'active' : ''}`}
          onClick={() => setTab('tools')}
        >
          <Wrench size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          {t('panel.tools')}
        </button>
        <button
          className={`panel-tab ${tab === 'conversations' ? 'active' : ''}`}
          onClick={() => setTab('conversations')}
        >
          <MessageCircle size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          {t('panel.conversations')}
        </button>
        <button
          className={`panel-tab ${tab === 'team' ? 'active' : ''}`}
          onClick={() => setTab('team')}
        >
          <Users size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          {t('panel.team')}
        </button>
      </div>

      <div className="panel-content">
        <div style={{ display: tab === 'progress' ? 'block' : 'none' }}>
          <ProgressTab sessionId={sessionId} />
        </div>
        <div style={{ display: tab === 'history' ? 'block' : 'none' }}>
          <CommandTab sessionId={sessionId} />
        </div>
        <div style={{ display: tab === 'tools' ? 'block' : 'none' }}>
          <ToolExecutionTab sessionId={sessionId} />
        </div>
        <div style={{ display: tab === 'conversations' ? 'block' : 'none' }}>
          <ConversationTab sessionId={sessionId} />
        </div>
        <div style={{ display: tab === 'team' ? 'block' : 'none' }}>
          <TeamTab sessionId={sessionId} />
        </div>
      </div>
    </div>
  );
}

/* ── 进度标签 ── */
function ProgressTab({ sessionId }: { sessionId: string | null }) {
  const [items, setItems] = useState<ProgressItem[]>([]);
  const { t } = useI18n();

  const fetchData = useCallback(async () => {
    if (!sessionId) { setItems([]); return; }
    try {
      setItems(await getProgress(sessionId));
    } catch { /* ignore */ }
  }, [sessionId]);

  useEffect(() => {
    // sessionId 改变时立即清空旧数据
    setItems([]);
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, [fetchData]);

  if (!sessionId) return <div className="empty-state">{t('panel.select_session')}</div>;
  if (!items.length) return <div className="empty-state">{t('panel.no_progress')}</div>;
  return (
    <>
      {items.map((p) => (
        <div key={p.num} className="progress-item">
          <div className="progress-header">
            <span className="progress-num">#{p.num} {p.title}</span>
            <span className={`progress-status ${p.status}`}>{p.status}</span>
          </div>
          {p.description && <div className="progress-desc">{p.description}</div>}
        </div>
      ))}
    </>
  );
}

/* ── 命令历史标签 ── */
function CommandTab({ sessionId }: { sessionId: string | null }) {
  const [items, setItems] = useState<CommandHistoryItem[]>([]);
  const { t } = useI18n();

  const fetchData = useCallback(async () => {
    if (!sessionId) { setItems([]); return; }
    try {
      setItems(await getCommandHistory(sessionId));
    } catch { /* ignore */ }
  }, [sessionId]);

  useEffect(() => {
    // sessionId 改变时立即清空旧数据
    setItems([]);
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, [fetchData]);

  if (!sessionId) return <div className="empty-state">{t('panel.select_session')}</div>;
  if (!items.length) return <div className="empty-state">{t('panel.no_commands')}</div>;
  return (
    <>
      {[...items].reverse().map((c) => (
        <div key={c.id} className="cmd-item">
          <div className="cmd-agent">{c.agent_name}</div>
          <div className="cmd-command">$ {c.command}</div>
          {c.result && <div className="cmd-result">{c.result}</div>}
          <div className="cmd-time">{new Date(c.timestamp).toLocaleString('zh-CN')}</div>
        </div>
      ))}
    </>
  );
}

/* ── Agent 对话标签 ── */
function ConversationTab({ sessionId }: { sessionId: string | null }) {
  const [items, setItems] = useState<AgentMessageItem[]>([]);
  const { t } = useI18n();

  const fetchData = useCallback(async () => {
    if (!sessionId) { setItems([]); return; }
    try {
      setItems(await getAgentMessages(sessionId));
    } catch { /* ignore */ }
  }, [sessionId]);

  useEffect(() => {
    // sessionId 改变时立即清空旧数据
    setItems([]);
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, [fetchData]);

  if (!sessionId) return <div className="empty-state">{t('panel.select_session')}</div>;
  if (!items.length) return <div className="empty-state">{t('panel.no_conversations')}</div>;
  return (
    <>
      {[...items].reverse().map((m) => (
        <div key={m.id} className="agent-msg-item">
          <div className="agent-msg-header">
            <span className="agent-msg-from">{m.from_agent}</span>
            <span className="agent-msg-arrow">&rarr;</span>
            <span className="agent-msg-to">{m.to_agent}</span>
            <span className="agent-msg-type">{m.msg_type}</span>
          </div>
          <div className="agent-msg-content">{m.content}</div>
          <div className="agent-msg-time">{new Date(m.created_at).toLocaleString('zh-CN')}</div>
        </div>
      ))}
    </>
  );
}

/* ── 工具执行记录标签 ── */
function ToolExecutionTab({ sessionId }: { sessionId: string | null }) {
  const [items, setItems] = useState<ToolExecutionItem[]>([]);
  const { t } = useI18n();

  const fetchData = useCallback(async () => {
    if (!sessionId) { setItems([]); return; }
    try {
      setItems(await getToolExecutions(sessionId));
    } catch { /* ignore */ }
  }, [sessionId]);

  useEffect(() => {
    // sessionId 改变时立即清空旧数据
    setItems([]);
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, [fetchData]);

  if (!sessionId) return <div className="empty-state">{t('panel.select_session')}</div>;
  if (!items.length) return <div className="empty-state">{t('panel.no_tools')}</div>;
  return (
    <>
      {[...items].reverse().map((tool) => (
        <div key={tool.id} className="cmd-item">
          <div className="cmd-agent">{tool.agent_name}</div>
          <div className="cmd-command" style={{ color: 'var(--accent)' }}>
            {tool.action}
          </div>
          {tool.summary && (
            <div className="cmd-result" style={{ marginTop: 4 }}>
              {tool.summary}
            </div>
          )}
          {tool.detail && (
            <div className="cmd-result" style={{ marginTop: 4, fontSize: 11 }}>
              {tool.detail}
            </div>
          )}
          <div className="cmd-time">{new Date(tool.created_at).toLocaleString('zh-CN')}</div>
        </div>
      ))}
    </>
  );
}

/* ── 团队状态标签 ── */
const AGENT_ORDER: Record<string, number> = { leader: 0, recon: 1, analysis: 2, attack: 3, report: 4 };
const AGENT_ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  leader: Crown,
  recon: Eye,
  analysis: Brain,
  attack: Swords,
  report: FileText,
};

function TeamTab({ sessionId }: { sessionId: string | null }) {
  const [agents, setAgents] = useState<AgentStatusItem[]>([]);
  const { t } = useI18n();

  const fetchData = useCallback(async () => {
    if (!sessionId) { setAgents([]); return; }
    try {
      const data = await getAgentStatuses(sessionId);
      data.sort((a, b) => (AGENT_ORDER[a.name] ?? 99) - (AGENT_ORDER[b.name] ?? 99));
      setAgents(data);
    } catch { /* ignore */ }
  }, [sessionId]);

  useEffect(() => {
    setAgents([]);
    fetchData();
    const id = setInterval(fetchData, 3000);
    return () => clearInterval(id);
  }, [fetchData]);

  if (!sessionId) return <div className="empty-state">{t('panel.select_session')}</div>;
  if (!agents.length) return <div className="empty-state">{t('panel.no_team')}</div>;
  return (
    <div className="team-list">
      {agents.map((a) => {
        const Icon = AGENT_ICONS[a.name];
        return (
          <div key={a.name} className={`team-item ${a.status} ${a.name === 'leader' ? 'team-leader' : ''}`}>
            {Icon && <Icon size={14} className="team-icon" />}
            <span className="team-name">{a.name}</span>
            <div className="team-status-bar">
              <div className="team-status-fill" />
            </div>
            <span className="team-status">{a.status === 'busy' ? t('panel.status_busy') : t('panel.status_idle')}</span>
          </div>
        );
      })}
    </div>
  );
}
