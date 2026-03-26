import { useState, useEffect, useCallback } from 'react';
import { MonitorOverview, SessionStatus, ActivityEntry } from '../types';
import * as api from '../api';

/**
 * MonitorView — Live Claude Code session monitor.
 *
 * Polls the backend every 5 seconds and shows:
 * - Active sessions with real-time activity feed (thinking, tool calls, text)
 * - Recently completed dispatches
 */
export default function MonitorView() {
  const [data, setData] = useState<MonitorOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detailSession, setDetailSession] = useState<SessionStatus | null>(null);
  const [pollInterval, setPollInterval] = useState(5);

  const loadStatus = useCallback(async () => {
    try {
      const overview = await api.fetchMonitorStatus(50);
      setData(overview);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, []);

  // Load detail when expanded
  const loadDetail = useCallback(async (dispatchId: number) => {
    try {
      const detail = await api.fetchSessionDetail(dispatchId, 100);
      setDetailSession(detail);
    } catch {
      // ignore — overview data is still shown
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, pollInterval * 1000);
    return () => clearInterval(interval);
  }, [loadStatus, pollInterval]);

  // Reload detail when overview refreshes
  useEffect(() => {
    if (expandedId !== null) {
      loadDetail(expandedId);
    }
  }, [data, expandedId, loadDetail]);

  const toggleExpand = (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetailSession(null);
    } else {
      setExpandedId(id);
    }
  };

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'thinking': return '🧠';
      case 'tool_use': return '🔧';
      case 'tool_result': return '�';
      case 'text': return '💬';
      case 'error': return '❌';
      case 'status': return '📡';
      default: return '•';
    }
  };

  const getStatusBadge = (status: string | null) => {
    switch (status) {
      case 'running': return <span className="monitor-badge running">● Running</span>;
      case 'queued': return <span className="monitor-badge queued">◷ Queued</span>;
      case 'completed': return <span className="monitor-badge completed">✓ Completed</span>;
      case 'failed': return <span className="monitor-badge failed">✗ Failed</span>;
      case 'stopped': return <span className="monitor-badge stopped">⏸ Stopped</span>;
      default: return <span className="monitor-badge">{status}</span>;
    }
  };

  const formatTime = (isoStr: string | null) => {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getElapsed = (startedAt: string | null) => {
    if (!startedAt) return '';
    const start = new Date(startedAt).getTime();
    const now = Date.now();
    const secs = Math.floor((now - start) / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    const remSecs = secs % 60;
    if (mins < 60) return `${mins}m ${remSecs}s`;
    const hours = Math.floor(mins / 60);
    return `${hours}h ${mins % 60}m`;
  };

  return (
    <div className="monitor-container">
      {/* Controls bar */}
      <div className="monitor-controls">
        <div className="monitor-controls-left">
          <h2 className="monitor-title">📡 Claude Code Monitor</h2>
          {data && (
            <span className="monitor-status-line">
              {data.has_active ? (
                <span className="pulse-dot" />
              ) : (
                <span className="idle-dot" />
              )}
              {data.active_dispatches > 0
                ? `${data.active_dispatches} active session${data.active_dispatches > 1 ? 's' : ''}`
                : 'No active sessions'}
            </span>
          )}
        </div>
        <div className="monitor-controls-right">
          <label className="monitor-poll-label">
            Poll:
            <select
              value={pollInterval}
              onChange={(e) => setPollInterval(Number(e.target.value))}
              className="monitor-select"
            >
              <option value={2}>2s</option>
              <option value={5}>5s</option>
              <option value={10}>10s</option>
              <option value={30}>30s</option>
            </select>
          </label>
          <button className="monitor-refresh-btn" onClick={loadStatus}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {error && <div className="monitor-error">⚠️ {error}</div>}

      {/* Active sessions */}
      {data && data.sessions.length > 0 && (
        <div className="monitor-section">
          <h3 className="monitor-section-title">🔥 Active Sessions</h3>
          {data.sessions.map((session) => (
            <SessionCard
              key={session.dispatch_id}
              session={session}
              isExpanded={expandedId === session.dispatch_id}
              detail={expandedId === session.dispatch_id ? detailSession : null}
              onToggle={() => session.dispatch_id && toggleExpand(session.dispatch_id)}
              getActivityIcon={getActivityIcon}
              getStatusBadge={getStatusBadge}
              formatTime={formatTime}
              getElapsed={getElapsed}
            />
          ))}
        </div>
      )}

      {/* Idle state */}
      {data && data.sessions.length === 0 && (
        <div className="monitor-idle">
          <div className="monitor-idle-icon">🦞</div>
          <p>No active Claude Code sessions</p>
          <p className="monitor-idle-hint">
            Dispatch a task from the Board to start a session
          </p>
        </div>
      )}

      {/* Recently completed */}
      {data && data.recent_completed.length > 0 && (
        <div className="monitor-section">
          <h3 className="monitor-section-title">📜 Recent History</h3>
          {data.recent_completed.map((session) => (
            <SessionCard
              key={session.dispatch_id}
              session={session}
              isExpanded={expandedId === session.dispatch_id}
              detail={expandedId === session.dispatch_id ? detailSession : null}
              onToggle={() => session.dispatch_id && toggleExpand(session.dispatch_id)}
              getActivityIcon={getActivityIcon}
              getStatusBadge={getStatusBadge}
              formatTime={formatTime}
              getElapsed={getElapsed}
            />
          ))}
        </div>
      )}
    </div>
  );
}


// ---- Sub-components ----

interface SessionCardProps {
  session: SessionStatus;
  isExpanded: boolean;
  detail: SessionStatus | null;
  onToggle: () => void;
  getActivityIcon: (type: string) => string;
  getStatusBadge: (status: string | null) => JSX.Element;
  formatTime: (isoStr: string | null) => string;
  getElapsed: (startedAt: string | null) => string;
}

function SessionCard({
  session,
  isExpanded,
  detail,
  onToggle,
  getActivityIcon,
  getStatusBadge,
  formatTime,
  getElapsed,
}: SessionCardProps) {
  const activity = (detail?.activity ?? session.activity);
  const lastActivity = activity.length > 0 ? activity[activity.length - 1] : null;

  return (
    <div className={`monitor-card ${isExpanded ? 'expanded' : ''} ${session.dispatch_status}`}>
      <div className="monitor-card-header" onClick={onToggle}>
        <div className="monitor-card-title">
          {getStatusBadge(session.dispatch_status)}
          <span className="monitor-card-name">
            {session.task_title || session.project_name || `Dispatch #${session.dispatch_id}`}
          </span>
          {session.dispatch_status === 'running' && (
            <span className="monitor-elapsed">{getElapsed(session.started_at)}</span>
          )}
        </div>
        <div className="monitor-card-meta">
          {session.total_tokens > 0 && (
            <span className="monitor-token-count" title="Tokens used">
              🪙 {session.total_tokens.toLocaleString()}
            </span>
          )}
          {session.total_cost_usd > 0 && (
            <span className="monitor-cost" title="Estimated cost">
              ${session.total_cost_usd.toFixed(4)}
            </span>
          )}
          <span className="monitor-msg-count">{session.total_messages} msgs</span>
          <span className="monitor-expand-icon">{isExpanded ? '▼' : '▶'}</span>
        </div>
      </div>

      {/* Preview: last activity (when collapsed) */}
      {!isExpanded && lastActivity && (
        <div className="monitor-preview">
          <span className="monitor-preview-icon">{getActivityIcon(lastActivity.type)}</span>
          <span className="monitor-preview-text">{lastActivity.summary}</span>
        </div>
      )}

      {/* Expanded: full activity feed */}
      {isExpanded && (
        <div className="monitor-activity-panel">
          <div className="monitor-activity-toolbar">
            <span className="monitor-activity-info">
              Session: {session.session_id?.slice(0, 8) || '—'}… • Started: {formatTime(session.started_at)}
            </span>
          </div>
          <div className="monitor-activity-feed">
            {activity.map((entry: ActivityEntry, i: number) => (
              <ActivityRow key={i} entry={entry} getIcon={getActivityIcon} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function ActivityRow({ entry, getIcon }: { entry: ActivityEntry; getIcon: (t: string) => string }) {
  const [showDetail, setShowDetail] = useState(false);

  return (
    <div className={`monitor-activity-row ${entry.type}`}>
      <span className="monitor-activity-icon">{getIcon(entry.type)}</span>
      <div className="monitor-activity-content">
        <span className="monitor-activity-summary">{entry.summary}</span>
        {entry.detail && (
          <>
            <button
              className="monitor-detail-toggle"
              onClick={() => setShowDetail(!showDetail)}
            >
              {showDetail ? '▼ hide' : '▶ detail'}
            </button>
            {showDetail && (
              <pre className="monitor-detail-block">{entry.detail}</pre>
            )}
          </>
        )}
      </div>
    </div>
  );
}
