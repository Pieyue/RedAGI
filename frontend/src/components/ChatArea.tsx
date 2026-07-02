import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Send, Square } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { API_BASE } from '../api/client';
import { stopSession } from '../api/sessions';
import { useI18n } from '../i18n';
import type { ChatMessage } from '../api/monitor';

interface Props {
  sessionId: string | null;
  sessionStatus: string;
  initialMessage: string | null;
  onInitialMessageSent: () => void;
  onCreateTask: (title: string, objective: string) => void;
}

export default function ChatArea({ sessionId, sessionStatus, initialMessage, onInitialMessageSent, onCreateTask }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const msgEndRef = useRef<HTMLDivElement>(null);
  const initialSentRef = useRef(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskObjective, setTaskObjective] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [isRunning, setIsRunning] = useState(false);
  const rainCanvasRef = useRef<HTMLCanvasElement>(null);
  const { t } = useI18n();

  // 同步 sessionStatus prop 到本地 isRunning（session 切换时重置）
  useEffect(() => {
    setIsRunning(sessionStatus === 'running');
  }, [sessionId, sessionStatus]);
  const connect = useCallback(() => {
    if (!sessionId) return;
    const token = localStorage.getItem('access_token');
    const wsUrl = API_BASE.replace('http', 'ws') + `/ws/chat/${sessionId}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      setCreating(false); // WebSocket 连接成功，初始化完成
    };
    ws.onclose = () => { setWsConnected(false); setSending(false); setCreating(false); };
    ws.onerror = () => { setWsConnected(false); setSending(false); setCreating(false); };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'response') {
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              session_id: sessionId!,
              role: 'agent',
              agent_name: 'leader',
              content: data.content || '',
              created_at: new Date().toISOString(),
            },
          ]);
          setSending(false);
        } else if (data.type === 'error') {
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              session_id: sessionId!,
              role: 'agent',
              agent_name: 'leader',
              content: `[Error] ${data.content || ''}`,
              created_at: new Date().toISOString(),
            },
          ]);
          setSending(false);
        } else if (data.type === 'status') {
          if (data.status === 'stopped') {
            setSending(false);
            setIsRunning(false);
          } else if (data.status === 'running') {
            setIsRunning(true);
          }
        } else if (data.type === 'agent_message') {
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              session_id: sessionId!,
              role: 'agent',
              agent_name: data.agent || 'agent',
              content: data.content || '',
              created_at: new Date().toISOString(),
            },
          ]);
        }
      } catch (e) {
        console.error('[ChatArea] 消息解析失败:', e);
      }
    };
  }, [sessionId]);

  // 加载历史消息
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    // 新建任务时有 initialMessage，跳过历史加载（全新会话无历史，且异步返回会覆盖初始消息）
    if (!initialMessage) {
      import('../api/monitor').then(({ getMessages }) => {
        getMessages(sessionId).then(setMessages).catch(console.error);
      }).catch(console.error);
    }

    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [sessionId, connect]);

  // 新建任务时自动发送任务目标
  useEffect(() => {
    if (wsConnected && initialMessage && !initialSentRef.current) {
      initialSentRef.current = true;
      // 任务目标作为用户消息显示在聊天区
      setMessages([{
        id: Date.now(),
        session_id: sessionId!,
        role: 'user',
        agent_name: null,
        content: initialMessage,
        created_at: new Date().toISOString(),
      }]);
      setSending(true);
      wsRef.current?.send(JSON.stringify({ content: initialMessage }));
      onInitialMessageSent();
      return () => { initialSentRef.current = false; };
    }
  }, [wsConnected, initialMessage, onInitialMessageSent, sessionId]);

  // 自动滚动
  useEffect(() => {
    msgEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const userMsg: ChatMessage = {
      id: Date.now(),
      session_id: sessionId!,
      role: 'user',
      agent_name: null,
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);

    wsRef.current.send(JSON.stringify({ content: text }));
  }

  async function handleStop() {
    if (!sessionId) return;
    try {
      await stopSession(sessionId);
      setSending(false);
      setIsRunning(false);
    } catch (err) {
      console.error('停止任务失败', err);
    }
  }

  // textarea 自动伸缩高度
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 340) + 'px';
  }, [input]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function formatMessageTime(ts: string) {
    const d = new Date(ts);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  // 二进制代码雨效果（粒子式，随机位置产生）
  useEffect(() => {
    if (sessionId) return;
    const canvas = rainCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();

    const chars = '01';

    // 单个代码雨流
    interface Stream {
      x: number;        // x 坐标（像素）
      y: number;        // 头部 y 坐标（像素）
      speed: number;    // 每帧下落像素数
      fontSize: number; // 字号
      trail: number;    // 字符链长度
      life: number;     // 剩余生命周期（帧数）
      maxLife: number;  // 总生命周期（用于计算渐变）
      chars: string[];  // 预生成的字符序列
    }

    let streams: Stream[] = [];
    let animId: number;
    let frameCount = 0;

    // 在随机位置生成一个新流
    const spawnStream = (): Stream => {
      const fontSize = 8 + Math.floor(Math.random() * 13); // 8~20px，随机尺寸
      const trail = 3 + Math.floor(Math.random() * 6); // 3~8 个字符
      const life = 120 + Math.floor(Math.random() * 180); // 存活 120~300 帧
      // 预生成字符序列，避免每帧随机闪烁
      const charList = Array.from({ length: trail }, () => chars[Math.floor(Math.random() * chars.length)]);
      return {
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height, // 随机 y（界面任意位置）
        speed: 0.3 + Math.random() * 0.4, // 每帧 0.3~0.7px，很慢
        fontSize,
        trail,
        life,
        maxLife: life,
        chars: charList,
      };
    };

    // 初始生成一批流
    const initCount = Math.floor((canvas.width * canvas.height) / 7000); // 按面积密度
    for (let i = 0; i < Math.max(initCount, 8); i++) {
      streams.push(spawnStream());
    }

    const draw = () => {
      frameCount++;
      // 每 4 帧更新一次，进一步降低速度
      if (frameCount % 4 !== 0) {
        animId = requestAnimationFrame(draw);
        return;
      }

      // 每帧完全清屏，不留任何残影
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 根据缺口批量补充新流（保持密度稳定）
      const targetCount = Math.max(initCount, 8);
      const deficit = targetCount - streams.length;
      if (deficit > 0) {
        // 每帧最多补充缺口的 1/3 或至少 1 个，避免瞬间爆发
        const spawnCount = Math.min(Math.ceil(deficit / 3), 5);
        for (let i = 0; i < spawnCount; i++) {
          streams.push(spawnStream());
        }
      }

      for (let s = streams.length - 1; s >= 0; s--) {
        const stream = streams[s];
        stream.y += stream.speed;
        stream.life--;

        // 生命耗尽或超出画布底部 → 移除
        if (stream.life <= 0 || stream.y - stream.trail * stream.fontSize > canvas.height) {
          streams.splice(s, 1);
          continue;
        }

        ctx.font = `${stream.fontSize}px Consolas, monospace`;

        // 淡入淡出渐变透明度
        const fadeInThreshold = 30;  // 前 30 帧淡入
        const fadeOutThreshold = 40; // 最后 40 帧淡出
        const age = stream.maxLife - stream.life;
        const fadeInFactor = age < fadeInThreshold ? age / fadeInThreshold : 1;
        const fadeOutFactor = stream.life < fadeOutThreshold ? stream.life / fadeOutThreshold : 1;
        const fadeFactor = fadeInFactor * fadeOutFactor;

        // 绘制字符链（头部稍亮 → 尾部极暗）
        for (let j = 0; j < stream.trail; j++) {
          const charY = stream.y - j * stream.fontSize;
          if (charY < 0 || charY > canvas.height) continue;

          const ratio = 1 - j / stream.trail; // 1=头部, 0=尾部
          // 颜色整体偏暗，融入背景
          const r = Math.floor(80 + ratio * 100);  // 80~180
          const g = Math.floor(ratio * 12);          // 0~12
          const b = Math.floor(ratio * 12);          // 0~12
          const alpha = (0.1 + ratio * 0.3) * fadeFactor; // 乘以渐变因子
          ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;

          ctx.fillText(stream.chars[j], stream.x, charY);
        }
      }

      animId = requestAnimationFrame(draw);
    };

    // 初始清屏
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    animId = requestAnimationFrame(draw);

    const onResize = () => {
      resize();
      streams = [];
      for (let i = 0; i < Math.max(initCount, 8); i++) {
        streams.push(spawnStream());
      }
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
    };
  }, [sessionId]);

  // 随机欢迎语
  const welcomeText = useMemo(() => {
    const keys = [
      'chat.welcome_1',
      'chat.welcome_2',
      'chat.welcome_3',
      'chat.welcome_4',
      'chat.welcome_5',
      'chat.welcome_6',
      'chat.welcome_7',
    ];
    return t(keys[Math.floor(Math.random() * keys.length)]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className={`chat-area${!sessionId ? ' chat-welcome' : ''}`}>
      {!sessionId && <canvas ref={rainCanvasRef} className="chat-rain-canvas" />}
      <div className="chat-header">
        <div className="chat-header-title">
          {sessionId ? t('chat.title_active') : t('chat.title_idle')}
        </div>
        <div className="chat-header-status">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: wsConnected ? 'var(--success)' : 'var(--text-muted)',
              display: 'inline-block',
            }}
          />
          {wsConnected ? t('chat.connected') : t('chat.disconnected')}
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && !sessionId && (
          <div className="chat-empty" style={{ flexDirection: 'column', gap: 32, justifyContent: 'flex-start', paddingTop: '10vh' }}>
            <p style={{ fontSize: 48, fontWeight: 700, color: '#fff', letterSpacing: 3, marginBottom: 16 }}>
              {welcomeText}
            </p>
            <div style={{ width: 800, maxWidth: '90%' }}>
              <input
                type="text"
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
                placeholder={t('chat.placeholder_title')}
                style={{ width: '100%', marginBottom: 12 }}
              />
              <textarea
                value={taskObjective}
                onChange={(e) => setTaskObjective(e.target.value)}
                placeholder={t('chat.placeholder_obj')}
                rows={10}
                style={{ width: '100%', resize: 'vertical', marginBottom: 12 }}
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn-primary"
                onClick={async () => {
                  const t = taskTitle.trim();
                  const o = taskObjective.trim();
                  if (!t || !o) return;
                  setCreating(true);
                  setTaskTitle('');
                  setTaskObjective('');
                  try {
                    await onCreateTask(t, o);
                  } catch {
                    // onCreateTask 内部已 catch，这里兜底
                  } finally {
                    setCreating(false);
                  }
                }}
                disabled={!taskTitle.trim() || !taskObjective.trim() || creating}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 28px',
                  fontSize: 15,
                  fontWeight: 600,
                  opacity: creating ? 0.7 : 1,
                  cursor: creating ? 'not-allowed' : 'pointer',
                }}
              >
                {creating ? (
                  <>
                    <span className="loading-dots" style={{ marginRight: 4 }}>
                      <span /><span /><span />
                    </span>
                    {t('chat.initializing')}
                  </>
                ) : (
                  <>
                    <Send size={16} />
                    {t('chat.start_task')}
                  </>
                )}
              </button>
              </div>
            </div>
          </div>
        )}
        {messages.length === 0 && sessionId && !wsConnected && (
          <div className="chat-empty">
            <div style={{ textAlign: 'center' }}>
              <span className="loading-dots" style={{ marginBottom: 16 }}>
                <span /><span /><span />
              </span>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 12 }}>
                {t('chat.init_session')}
              </p>
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: m.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            {m.agent_name && (
              <div className="message-role" style={{ marginLeft: 8 }}>
                {m.agent_name}
              </div>
            )}
            <div className={`message-bubble ${m.role}`}>
              {m.role === 'agent' ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              ) : (
                m.content
              )}
            </div>
            <div className="message-time">{formatMessageTime(m.created_at)}</div>
          </div>
        ))}
        {sending && (
          <div className="message-bubble agent" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className="loading-dots">
              <span /><span /><span />
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('chat.thinking')}</span>
          </div>
        )}
        <div ref={msgEndRef} />
      </div>

      {sessionId && (
      <div className="chat-input-area">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={sessionId ? t('chat.placeholder_input') : t('chat.placeholder_disabled')}
          disabled={!sessionId || isRunning}
          rows={1}
        />
        {isRunning ? (
          <button className="stop-btn" onClick={handleStop}>
            <Square size={16} />
            {t('chat.stop')}
          </button>
        ) : (
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!sessionId || !input.trim() || !wsConnected}
          >
            <Send size={16} />
            {t('chat.send')}
          </button>
        )}
      </div>
      )}
    </div>
  );
}
