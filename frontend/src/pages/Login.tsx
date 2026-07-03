import { useState, useRef, useEffect, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api/auth';
import { Sword, LogIn, Globe } from 'lucide-react';
import { useI18n } from '../i18n';

/* ── 二进制雨流（单条水平流） ── */
interface RainStream {
  y: number;
  chars: { char: string; x: number }[];
  speed: number;
  maxLen: number;
  fontSize: number;
  charSpace: number;
}

function spawnStream(canvasW: number, canvasH: number): RainStream {
  const maxLen = 15 + Math.floor(Math.random() * 70);
  const fontSize = 5 + Math.random() * 18; // 5~22，大幅拉开层次
  const charSpace = fontSize * 0.48;
  const stream: RainStream = {
    y: Math.random() * canvasH,
    chars: [],
    speed: 0.8 + Math.random() * 2.5,
    maxLen,
    fontSize,
    charSpace,
  };
  // 预填充字符，初始散布在画布右侧外
  const startX = canvasW + Math.random() * canvasW * 0.4;
  for (let i = 0; i < maxLen; i++) {
    stream.chars.push({
      char: Math.random() > 0.5 ? '0' : '1',
      x: startX + i * stream.charSpace,
    });
  }
  return stream;
}

/* ── 多段渐变映射：粉白→亮红→红色→暗红→黑红 ── */
type ColorStop = [t: number, r: number, g: number, b: number];
const GRADIENT_STOPS: ColorStop[] = [
  [1.0,  255, 195, 195],  // 粉白
  [0.75, 240,  35,  35],  // 亮红
  [0.50, 160,  15,  15],  // 红色
  [0.25,  75,   5,   5],  // 暗红
  [0.0,   18,   0,   0],  // 黑红
];

// 字体字符串缓存，避免每流拼接
const _fontCache = new Map<number, string>();
function getFont(fontSize: number): string {
  const cached = _fontCache.get(fontSize);
  if (cached) return cached;
  const font = `${fontSize}px 'Consolas','Courier New',monospace`;
  _fontCache.set(fontSize, font);
  return font;
}

// 颜色缓存：缓存完整 rgba 字符串，避免每帧拼接
const _colorCache = new Map<number, string>();
const _shadowCache = new Map<number, string>();
function getCachedStyle(t: number): { fill: string; shadow: string | null; blur: number } {
  const key = Math.round(t * 100);
  const cached = _colorCache.get(key);
  if (cached) return { fill: cached, shadow: _shadowCache.get(key) || null, blur: 0 };
  // 计算颜色
  const stops = GRADIENT_STOPS;
  let r = 18, g = 0, b = 0;
  for (let i = 0; i < stops.length - 1; i++) {
    const [t1, r1, g1, b1] = stops[i];
    const [t2, r2, g2, b2] = stops[i + 1];
    if (t <= t1 && t >= t2) {
      const ratio = (t - t2) / (t1 - t2);
      r = Math.floor(r2 + ratio * (r1 - r2));
      g = Math.floor(g2 + ratio * (g1 - g2));
      b = Math.floor(b2 + ratio * (b1 - b2));
      break;
    }
  }
  const alpha = 0.10 + t * 0.90;
  const fill = `rgba(${r},${g},${b},${alpha})`;
  _colorCache.set(key, fill);
  // 光晕颜色（仅 t>0.65 有效，减少无关 shadow 开销）
  let shadow: string | null = null;
  if (t > 0.65) {
    const glowAlpha = Math.min(t * 0.92, 0.92);
    shadow = `rgba(${Math.floor(r + t * 60)},${Math.floor(g + t * 60)},${Math.floor(b + t * 60)},${glowAlpha})`;
    _shadowCache.set(key, shadow);
  }
  return { fill, shadow, blur: 0 };
}

/* ── 绘制：两遍，第一遍无光晕字符，第二遍有光晕字符 ── */
function drawStream(
  ctx: CanvasRenderingContext2D,
  stream: RainStream,
) {
  const { chars, y, fontSize } = stream;
  const len = chars.length;
  const charWidth = fontSize * 0.58;
  if (len === 0) return;
  ctx.font = getFont(fontSize);

  // 第一遍：尾部 + 中部无光晕字符
  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;
  for (let i = 0; i < len; i++) {
    const { char, x } = chars[i];
    if (x < -charWidth || x > ctx.canvas.width + charWidth) continue;
    const t = 1 - i / (len - 1 || 1);
    if (t > 0.65) continue; // 留给第二遍
    if (0.10 + t * 0.90 < 0.03) continue;
    ctx.fillStyle = getCachedStyle(t).fill;
    ctx.fillText(char, x, y);
  }

  // 第二遍：头部发光字符
  for (let i = 0; i < len; i++) {
    const { char, x } = chars[i];
    if (x < -charWidth || x > ctx.canvas.width + charWidth) continue;
    const t = 1 - i / (len - 1 || 1);
    if (t <= 0.65) continue;
    const style = getCachedStyle(t);
    ctx.fillStyle = style.fill;
    if (style.shadow) {
      ctx.shadowColor = style.shadow;
      ctx.shadowBlur = t * fontSize * 2.2;
    }
    ctx.fillText(char, x, y);
  }
  ctx.shadowColor = 'transparent';
  ctx.shadowBlur = 0;
}

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const { lang, t, toggleLang } = useI18n();

  /* ── 鼠标跟随光晕 ── */
  useEffect(() => {
    const el = pageRef.current;
    if (!el) return;
    const onMove = (e: MouseEvent) => {
      el.style.setProperty('--mx', `${e.clientX}px`);
      el.style.setProperty('--my', `${e.clientY}px`);
    };
    window.addEventListener('mousemove', onMove);
    return () => window.removeEventListener('mousemove', onMove);
  }, []);

  /* ── 二进制雨动画 ── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const TARGET_COUNT = 100; // 目标流数量
    let animId = 0;
    let frame = 0;
    let streams: RainStream[] = [];

    function resize() {
      canvas!.width = window.innerWidth;
      canvas!.height = window.innerHeight;
    }

    function init() {
      resize();
      for (let i = 0; i < TARGET_COUNT; i++) {
        streams.push(spawnStream(canvas!.width, canvas!.height));
      }
    }

    function tick() {
      if (!canvas || !ctx) return;
      frame++;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 持续发射：每 N 帧补充新流
      if (frame % 6 === 0 && streams.length < TARGET_COUNT) {
        streams.push(spawnStream(canvas.width, canvas.height));
      }

      for (let i = streams.length - 1; i >= 0; i--) {
        const s = streams[i];
        const cw = s.fontSize * 0.58; // 字符宽度

        // 所有字符左移，同时每位在 0/1 间翻转（帧计数器驱动，无 random）
        for (let j = 0; j < s.chars.length; j++) {
          const c = s.chars[j];
          c.x -= s.speed;
          if (((frame + j) & 15) === 0) c.char = c.char === '0' ? '1' : '0';
        }

        // 移除已完全离开左侧的字符
        while (s.chars.length > 0 && s.chars[0].x < -cw * 3) {
          s.chars.shift();
        }

        // 补足到 maxLen，新字符从右侧进入
        while (s.chars.length < s.maxLen) {
          const lastX = s.chars.length > 0 ? s.chars[s.chars.length - 1].x : canvas.width - s.charSpace;
          const targetX = Math.max(lastX + s.charSpace, canvas.width);
          if (targetX - lastX > 200) {
            let nx = canvas.width;
            while (s.chars.length < s.maxLen) {
              s.chars.push({ char: Math.random() > 0.5 ? '0' : '1', x: nx });
              nx += s.charSpace;
            }
            break;
          }
          s.chars.push({ char: Math.random() > 0.5 ? '0' : '1', x: targetX });
        }

        // 截断超长
        while (s.chars.length > s.maxLen) s.chars.shift();

        // 流全部离开左侧 → 重生到右侧
        if (s.chars.length === 0 || s.chars[s.chars.length - 1].x < -cw) {
          s.y = Math.random() * canvas.height;
          s.speed = 0.8 + Math.random() * 2.5;
          s.fontSize = 5 + Math.random() * 18;
          s.charSpace = s.fontSize * 0.48;
          s.maxLen = 15 + Math.floor(Math.random() * 70);
          s.chars = [];
          const sx = canvas.width + Math.random() * 300;
          for (let j = 0; j < s.maxLen; j++) {
            s.chars.push({
              char: Math.random() > 0.5 ? '0' : '1',
              x: sx + j * s.charSpace,
            });
          }
        }

        drawStream(ctx, s);
      }

      animId = requestAnimationFrame(tick);
    }

    init();
    window.addEventListener('resize', resize);
    animId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password.trim()) {
      setError(t('login.error_required'));
      return;
    }
    setLoading(true);
    try {
      const data = await login({ username, password });
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('user', JSON.stringify({ id: data.user_id, username: data.username }));
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || t('login.error_fail'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page" ref={pageRef}>
      <canvas ref={canvasRef} className="login-canvas" />

      <div className="login-card">
        <button className="lang-toggle-btn" onClick={toggleLang} title={lang === 'zh' ? 'English' : '中文'}>
          <Globe size={16} />
          <span>{lang === 'zh' ? 'EN' : '中'}</span>
        </button>
        <div style={{ textAlign: 'center', marginBottom: 8 }}>
          <Sword size={40} color="#c0392b" style={{ transform: 'rotate(-45deg)' }} />
        </div>
        <h1 className="login-title">RedAGI</h1>
        <p className="login-subtitle">{t('login.subtitle')}</p>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: 'var(--text-secondary)' }}>
              {t('login.username')}
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t('login.username_ph')}
              style={{ width: '100%' }}
              autoFocus
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: 'var(--text-secondary)' }}>
              {t('login.password')}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('login.password_ph')}
              style={{ width: '100%' }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary"
            style={{
              width: '100%',
              padding: '12px',
              fontSize: 15,
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
            }}
          >
            {loading ? (
              <span className="loading-dots">
                <span /><span /><span />
              </span>
            ) : (
              <>
                <LogIn size={18} />
                {t('login.submit')}
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
