import { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from '../components/Sidebar';
import ChatArea from '../components/ChatArea';
import RightPanel from '../components/RightPanel';
import { listSessions, createSession } from '../api/sessions';
import { useI18n } from '../i18n';
import type { Session } from '../api/sessions';

const PANEL_MIN = 240;
const PANEL_MAX = 720;
const PANEL_DEFAULT = 360;

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [initialMessage, setInitialMessage] = useState<string | null>(null);
  const [panelWidth, setPanelWidth] = useState(PANEL_DEFAULT);
  const resizingRef = useRef(false);
  const { t } = useI18n();

  const fetchSessions = useCallback(async () => {
    try {
      setSessions(await listSessions());
    } catch (err) {
      console.error('获取会话列表失败', err);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    const id = setInterval(fetchSessions, 5000);
    return () => clearInterval(id);
  }, [fetchSessions]);

  const handleInitialMessageSent = useCallback(() => {
    setInitialMessage(null);
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setActiveId(id);
    setInitialMessage(null);
  }, []);

  async function handleCreateTask(title: string, objective: string) {
    try {
      const s = await createSession(title);
      setActiveId(s.id);
      setInitialMessage(objective);
      fetchSessions();
    } catch (err: any) {
      console.error('创建任务失败', err);
      const detail = err?.response?.data?.detail || t('dashboard.init_fail');
      alert(`${t('dashboard.create_fail')}：${detail}`);
    }
  }

  // 右侧面板拖拽调整宽度
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current) return;
      const newWidth = window.innerWidth - e.clientX;
      setPanelWidth(Math.min(PANEL_MAX, Math.max(PANEL_MIN, newWidth)));
    };
    const onMouseUp = () => {
      if (resizingRef.current) {
        resizingRef.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const startResize = () => {
    resizingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const activeSession = sessions.find((s) => s.id === activeId) || null;

  return (
    <div className="dashboard">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={handleSelectSession}
        onRefresh={fetchSessions}
        onCreateClick={() => { setActiveId(null); setInitialMessage(null); }}
      />
      <ChatArea
        sessionId={activeId}
        sessionStatus={activeSession?.status || 'idle'}
        initialMessage={initialMessage}
        onInitialMessageSent={handleInitialMessageSent}
        onCreateTask={handleCreateTask}
      />
      {activeId && (
        <>
          <div className="resize-handle" onMouseDown={startResize} />
          <RightPanel sessionId={activeId} style={{ width: panelWidth, minWidth: panelWidth }} />
        </>
      )}
    </div>
  );
}
