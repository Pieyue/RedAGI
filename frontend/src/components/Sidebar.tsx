import { Plus, MessageSquare, Trash2, Sword, LogOut, User, Globe } from 'lucide-react';
import { useState } from 'react';
import { deleteSession } from '../api/sessions';
import { useI18n } from '../i18n';
import type { Session } from '../api/sessions';

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  onCreateClick: () => void;
}

export default function Sidebar({ sessions, activeId, onSelect, onRefresh, onCreateClick }: Props) {
  const userData = JSON.parse(localStorage.getItem('user') || '{}');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const { lang, t, toggleLang } = useI18n();

  function handleLogout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }

  function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    setDeleteTarget(id);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteSession(deleteTarget);
      setDeleteTarget(null);
      onRefresh();
      if (activeId === deleteTarget) {
        onSelect('');
      }
    } catch (err) {
      console.error('删除会话失败', err);
    } finally {
      setDeleting(false);
    }
  }

  function cancelDelete() {
    setDeleteTarget(null);
  }

  function formatTime(ts: string) {
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60_000) return t('sidebar.just_now');
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}${t('sidebar.min_ago')}`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}${t('sidebar.hour_ago')}`;
    return d.toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US');
  }

  function statusLabel(s: string) {
    if (s === 'running') return t('sidebar.running');
    if (s === 'stopped') return t('sidebar.stopped');
    return t('sidebar.idle');
  }

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Sword className="logo-icon" style={{ transform: 'rotate(-45deg)' }} />
          <span>RedAGI</span>
        </div>
        <button className="lang-toggle-btn sidebar-lang-btn" onClick={toggleLang} title={lang === 'zh' ? 'English' : '中文'}>
          <Globe size={14} />
          <span>{lang === 'zh' ? 'EN' : '中'}</span>
        </button>
      </div>

      <button className="sidebar-create-btn" onClick={onCreateClick}>
        <Plus size={18} />
        {t('sidebar.new_task')}
      </button>

      <div className="sidebar-list">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`session-item ${activeId === s.id ? 'active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <MessageSquare className="session-icon" />
            <div className="session-info">
              <div className="session-title">{s.title}</div>
              <div className="session-meta">
                {statusLabel(s.status)} &middot; {formatTime(s.updated_at)}
              </div>
            </div>
            <span className={`session-status ${s.status}`} />
            <button
              className="btn-icon"
              onClick={(e) => handleDelete(e, s.id)}
              title={t('sidebar.delete_title')}
              style={{ width: 28, height: 28, opacity: 0.5 }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="empty-state">{t('sidebar.no_sessions')}</div>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <User size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
          {userData.username || 'admin'}
        </div>
        <button className="logout-btn" onClick={handleLogout}>
          <LogOut size={14} />
          {t('sidebar.logout')}
        </button>
      </div>

      {deleteTarget && (
        <div className="modal-overlay" onClick={cancelDelete}>
          <div className="modal-confirm" onClick={(e) => e.stopPropagation()}>
            <div className="modal-confirm-title">{t('sidebar.delete_title')}</div>
            <div className="modal-confirm-body">
              {t('sidebar.delete_confirm')}
            </div>
            <div className="modal-confirm-actions">
              <button className="btn-cancel" onClick={cancelDelete} disabled={deleting}>{t('sidebar.cancel')}</button>
              <button className="btn-danger" onClick={confirmDelete} disabled={deleting}>
                {deleting ? t('sidebar.deleting') : t('sidebar.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
