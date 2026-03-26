import { useState, useEffect, useCallback } from 'react';
import { Task, TaskMessage, COLUMNS, DispatchRecord, ProjectSummary, TASK_TYPES, TaskType, GitStrategy, ProjectSettingsData } from '../types';
import * as api from '../api';
import ProjectSettingsModal from './ProjectSettingsModal';

interface Props {
  task: Task;
  onClose: () => void;
  onRefresh: () => void;
}

const EVENT_ICONS: Record<string, string> = {
  created: '🆕',
  status_change: '🔄',
  archive: '📦',
  comment: '💬',
  dispatch: '🚀',
};

const AUTHOR_COLORS: Record<string, string> = {
  system: '#6b7280',
  user: '#3b82f6',
  'claude-teams': '#8b5cf6',
  'claude-code': '#a855f7',
  'dev-task': '#22c55e',
  openclaw: '#f59e0b',
};

const DISPATCH_STATUS_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  queued: { icon: '⏳', color: '#f59e0b', label: 'Queued' },
  running: { icon: '🔄', color: '#3b82f6', label: 'Running' },
  completed: { icon: '✅', color: '#22c55e', label: 'Completed' },
  failed: { icon: '❌', color: '#ef4444', label: 'Failed' },
  stopped: { icon: '⏸️', color: '#f97316', label: 'Stopped' },
};

interface ParsedResult {
  result: string | null;
  totalTokens: number;
  costUsd: number;
  numTurns: number;
  durationMs: number;
}

function extractDispatchResult(output: string | null): ParsedResult {
  const empty: ParsedResult = { result: null, totalTokens: 0, costUsd: 0, numTurns: 0, durationMs: 0 };
  if (!output) return empty;
  for (const line of output.split('\n')) {
    try {
      const ev = JSON.parse(line.trim());
      if (ev.type === 'result') {
        const usage = ev.usage || {};
        const tokens =
          (usage.input_tokens || 0) +
          (usage.output_tokens || 0) +
          (usage.cache_read_input_tokens || 0) +
          (usage.cache_creation_input_tokens || 0);
        return {
          result: ev.result || null,
          totalTokens: tokens,
          costUsd: ev.total_cost_usd || 0,
          numTurns: ev.num_turns || 0,
          durationMs: ev.duration_ms || 0,
        };
      }
    } catch {}
  }
  return empty;
}

export default function TaskDetailModal({ task, onClose, onRefresh }: Props) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description);
  const [messages, setMessages] = useState<TaskMessage[]>([]);
  const [newMsg, setNewMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);

  // Dispatch state
  const [showDispatch, setShowDispatch] = useState(false);
  const [dispatching, setDispatching] = useState(false);
  const [dispatchError, setDispatchError] = useState('');
  const [dispatchPrompt, setDispatchPrompt] = useState('');
  const [dispatchProject, setDispatchProject] = useState('');
  const [dispatchMode, setDispatchMode] = useState<'dev-task' | 'claude-teams'>('dev-task');
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [dispatches, setDispatches] = useState<DispatchRecord[]>([]);
  const [showOutput, setShowOutput] = useState<number | null>(null);

  // Project selector state
  const [taskProject, setTaskProject] = useState(task.project_name || '');

  // Task type state
  const [taskType, setTaskType] = useState<TaskType>(task.task_type || 'coding');

  // Project settings (git strategy)
  const [gitStrategy, setGitStrategy] = useState<GitStrategy>('direct_commit');
  const [showProjectSettings, setShowProjectSettings] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const projs = await api.fetchProjects();
      setProjects(projs);
    } catch {
      setProjects([]);
    }
  }, []);

  const loadMessages = useCallback(async () => {
    try {
      const msgs = await api.fetchMessages(task.id);
      setMessages(msgs);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  }, [task.id]);

  const loadDispatches = useCallback(async () => {
    try {
      const history = await api.fetchDispatchHistory(task.id);
      setDispatches(history);
    } catch (err) {
      console.error('Failed to load dispatches:', err);
    }
  }, [task.id]);

  useEffect(() => {
    loadMessages();
    loadDispatches();
    loadProjects();
  }, [loadMessages, loadDispatches, loadProjects]);

  useEffect(() => {
    setTitle(task.title);
    setDescription(task.description);
    setTaskProject(task.project_name || '');
    setTaskType(task.task_type || 'coding');
  }, [task.title, task.description, task.project_name, task.task_type]);

  // Load project git strategy settings when project changes
  useEffect(() => {
    if (taskProject) {
      api.fetchProjectSettings(taskProject).then((s) => {
        setGitStrategy(s.git_strategy);
      }).catch(() => setGitStrategy('direct_commit'));
    } else {
      setGitStrategy('direct_commit');
    }
  }, [taskProject]);

  // Poll for dispatch updates when there's an active dispatch
  useEffect(() => {
    const hasActive = dispatches.some((d) => d.status === 'queued' || d.status === 'running');
    if (!hasActive) return;

    const interval = setInterval(async () => {
      await loadDispatches();
      await loadMessages();
      onRefresh();
    }, 5000);

    return () => clearInterval(interval);
  }, [dispatches, loadDispatches, loadMessages, onRefresh]);

  async function handleSendMessage() {
    const trimmed = newMsg.trim();
    if (!trimmed || sending) return;
    setSending(true);
    try {
      await api.addMessage(task.id, trimmed, 'user', 'comment');
      setNewMsg('');
      await loadMessages();
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setSending(false);
    }
  }

  async function saveTitle() {
    setEditingTitle(false);
    const trimmed = title.trim();
    if (trimmed && trimmed !== task.title) {
      await api.updateTask(task.id, { title: trimmed });
      onRefresh();
    } else {
      setTitle(task.title);
    }
  }

  async function saveDescription() {
    setEditingDesc(false);
    if (description !== task.description) {
      await api.updateTask(task.id, { description });
      onRefresh();
    }
  }

  async function handleProjectChange(newProject: string) {
    setTaskProject(newProject);
    const value = newProject || null;
    if (value !== (task.project_name || null)) {
      await api.updateTask(task.id, { project_name: value } as any);
      onRefresh();
    }
  }

  async function handleTaskTypeChange(newType: TaskType) {
    setTaskType(newType);
    if (newType !== (task.task_type || 'coding')) {
      await api.updateTask(task.id, { task_type: newType } as any);
      onRefresh();
    }
  }

  async function openDispatchForm() {
    setShowDispatch(true);
    setDispatchPrompt(task.description || task.title);
    setDispatchError('');
    // Pre-fill dispatch project from task's project
    setDispatchProject(taskProject);
  }

  async function handleDispatch() {
    setDispatching(true);
    setDispatchError('');
    try {
      await api.createDispatch(task.id, {
        prompt: dispatchPrompt || undefined,
        project_name: dispatchProject || undefined,
        agent_mode: dispatchMode,
      });
      setShowDispatch(false);
      await loadDispatches();
      await loadMessages();
      onRefresh();
    } catch (err: any) {
      setDispatchError(err.message || 'Failed to dispatch');
    } finally {
      setDispatching(false);
    }
  }

  const statusCol = COLUMNS.find((c) => c.id === task.status);
  const created = new Date(task.created_at).toLocaleString();
  const updated = new Date(task.updated_at).toLocaleString();

  // Dispatch availability
  const canDispatch = ['planned', 'planning', 'in_progress'].includes(task.status);
  const hasActiveDispatch = dispatches.some((d) => d.status === 'queued' || d.status === 'running');
  const latestDispatch = dispatches[0] || null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content task-detail-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-status-badge" style={{ backgroundColor: statusCol?.color || '#6b7280' }}>
            {statusCol?.emoji} {statusCol?.title || task.status}
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {/* Title */}
        <div className="modal-title-section">
          {editingTitle ? (
            <input
              className="modal-title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={saveTitle}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveTitle();
                if (e.key === 'Escape') { setTitle(task.title); setEditingTitle(false); }
              }}
              autoFocus
            />
          ) : (
            <h2 className="modal-title" onClick={() => setEditingTitle(true)}>
              {task.title}
            </h2>
          )}
        </div>

        {/* Description */}
        <div className="modal-description-section">
          <label className="modal-label">Description</label>
          {editingDesc ? (
            <textarea
              className="modal-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={saveDescription}
              onKeyDown={(e) => {
                if (e.key === 'Escape') { setDescription(task.description); setEditingDesc(false); }
              }}
              placeholder="Add a detailed description…"
              autoFocus
            />
          ) : (
            <div
              className={`modal-description ${task.description ? '' : 'empty'}`}
              onClick={() => setEditingDesc(true)}
            >
              {task.description || 'Click to add a detailed description…'}
            </div>
          )}
        </div>

        {/* Project Selector */}
        <div className="modal-project-section">
          <label className="modal-label">📁 Project</label>
          <select
            className="modal-project-select"
            value={taskProject}
            onChange={(e) => handleProjectChange(e.target.value)}
          >
            <option value="">No project assigned</option>
            {projects.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} {p.has_docker_compose ? '🐳' : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Task Type Selector */}
        <div className="modal-task-type-section">
          <label className="modal-label">Task Type</label>
          <div className="task-type-buttons">
            {TASK_TYPES.map((tt) => (
              <button
                key={tt.id}
                className={`task-type-btn ${taskType === tt.id ? 'active' : ''}`}
                style={taskType === tt.id ? { borderColor: tt.color, color: tt.color } : {}}
                onClick={() => handleTaskTypeChange(tt.id)}
              >
                {tt.emoji} {tt.label}
              </button>
            ))}
          </div>
        </div>

        {/* ====== DISPATCH SECTION ====== */}
        <div className="dispatch-section">
          <div className="dispatch-header">
            <label className="modal-label">🤖 Claude Code</label>
            {canDispatch && !hasActiveDispatch && (
              <button className="dispatch-btn" onClick={openDispatchForm}>
                🚀 Dispatch
              </button>
            )}
            {hasActiveDispatch && (
              <span className="dispatch-active-badge">
                {DISPATCH_STATUS_CONFIG[latestDispatch?.status || 'running'].icon}{' '}
                {DISPATCH_STATUS_CONFIG[latestDispatch?.status || 'running'].label}
              </span>
            )}
          </div>

          {/* Active dispatch status */}
          {latestDispatch && (latestDispatch.status === 'queued' || latestDispatch.status === 'running') && (
            <div className="dispatch-status-card running">
              <div className="dispatch-status-line">
                <span className="dispatch-status-dot pulse" />
                <span>
                  Dispatch #{latestDispatch.id} — {latestDispatch.agent_mode}
                  {latestDispatch.project_name && ` → ${latestDispatch.project_name}`}
                </span>
              </div>
              <div className="dispatch-status-hint">
                {latestDispatch.status === 'queued'
                  ? '⏳ Waiting for host watcher to pick up…'
                  : '🔄 Claude Code is working…'}
              </div>
              <div className="dispatch-status-hint" style={{ fontSize: '11px', marginTop: '4px' }}>
                Run on host: <code>./scripts/dispatch-watcher.sh --once</code>
              </div>
            </div>
          )}

          {/* Dispatch history */}
          {dispatches.length > 0 && (
            <div className="dispatch-history">
              {dispatches.slice(0, 5).map((d) => {
                const cfg = DISPATCH_STATUS_CONFIG[d.status] || DISPATCH_STATUS_CONFIG.queued;
                return (
                  <div key={d.id} className={`dispatch-history-item ${d.status}`}>
                    <div className="dispatch-history-header">
                      <span style={{ color: cfg.color }}>
                        {cfg.icon} #{d.id}
                      </span>
                      <span className="dispatch-history-mode">{d.agent_mode}</span>
                      {d.project_name && (
                        <span className="dispatch-history-project">📁 {d.project_name}</span>
                      )}
                      <span className="dispatch-history-time">
                        {d.completed_at
                          ? new Date(d.completed_at).toLocaleString()
                          : d.started_at
                            ? new Date(d.started_at).toLocaleString()
                            : new Date(d.created_at).toLocaleString()}
                      </span>
                    </div>
                    {d.error_reason && (
                      <div className="dispatch-error-text">⚠️ {d.error_reason}</div>
                    )}
                    {/* Parsed result summary */}
                    {d.status === 'completed' && (() => {
                      const parsed = extractDispatchResult(d.output);
                      const duration = parsed.durationMs
                        ? `${(parsed.durationMs / 1000).toFixed(1)}s`
                        : null;
                      return (
                        <>
                          {(parsed.totalTokens > 0 || parsed.costUsd > 0) && (
                            <div className="dispatch-result-stats">
                              {parsed.numTurns > 0 && <span>🔁 {parsed.numTurns} turns</span>}
                              {duration && <span>⏱ {duration}</span>}
                              {parsed.totalTokens > 0 && <span>🪙 {parsed.totalTokens.toLocaleString()}</span>}
                              {parsed.costUsd > 0 && <span>💵 ${parsed.costUsd.toFixed(4)}</span>}
                            </div>
                          )}
                          {parsed.result && (
                            <div className="dispatch-result-block">
                              <button
                                className="dispatch-output-toggle"
                                onClick={() => setShowOutput(showOutput === d.id ? null : d.id)}
                              >
                                {showOutput === d.id ? '▼ Hide Result' : '▶ Show Result'}
                              </button>
                              {showOutput === d.id && (
                                <pre className="dispatch-result-text">{parsed.result}</pre>
                              )}
                            </div>
                          )}
                        </>
                      );
                    })()}
                    {/* Raw output for non-completed / no result */}
                    {d.status !== 'completed' && d.output && (
                      <>
                        <button
                          className="dispatch-output-toggle"
                          onClick={() => setShowOutput(showOutput === d.id ? null : d.id)}
                        >
                          {showOutput === d.id ? '▼ Hide Output' : '▶ Show Output'}
                        </button>
                        {showOutput === d.id && (
                          <pre className="dispatch-output-block">
                            <code>{d.output.slice(-2000)}</code>
                          </pre>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Meta info */}
        <div className="modal-meta">
          <span>Created: {created}</span>
          <span>Updated: {updated}</span>
          <span>ID: #{task.id}</span>
        </div>

        {/* Activity Timeline */}
        <div className="modal-timeline-section">
          <label className="modal-label">
            Activity ({messages.length})
          </label>
          <div className="modal-timeline">
            {messages.length === 0 ? (
              <div className="timeline-empty">No activity yet</div>
            ) : (
              messages.map((msg) => (
                <div key={msg.id} className={`timeline-item ${msg.event_type}`}>
                  <span className="timeline-icon">
                    {EVENT_ICONS[msg.event_type] || '💬'}
                  </span>
                  <div className="timeline-body">
                    <div className="timeline-header">
                      <span
                        className="timeline-author"
                        style={{ color: AUTHOR_COLORS[msg.author] || '#e4e4e7' }}
                      >
                        {msg.author}
                      </span>
                      <span className="timeline-time">
                        {new Date(msg.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="timeline-message">{msg.message}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* New message input */}
        <div className="modal-message-form">
          <input
            className="modal-message-input"
            value={newMsg}
            onChange={(e) => setNewMsg(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder="Add a comment… (Enter to send)"
            disabled={sending}
          />
          <button
            className="modal-send-btn"
            onClick={handleSendMessage}
            disabled={!newMsg.trim() || sending}
          >
            Send
          </button>
        </div>

        {/* ====== PROJECT SETTINGS MODAL ====== */}
        {showProjectSettings && taskProject && (
          <ProjectSettingsModal
            projectKey={taskProject}
            onClose={() => setShowProjectSettings(false)}
            onSaved={(s) => setGitStrategy(s.git_strategy)}
          />
        )}

        {/* ====== DISPATCH FORM MODAL ====== */}
        {showDispatch && (
          <div className="dispatch-form-overlay" onClick={() => setShowDispatch(false)}>
            <div className="dispatch-form" onClick={(e) => e.stopPropagation()}>
              <div className="dispatch-form-header">
                <h3>🚀 Dispatch to Claude Code</h3>
                <button className="modal-close" onClick={() => setShowDispatch(false)}>✕</button>
              </div>

              <div className="dispatch-form-body">
                <label className="modal-label">Agent Mode</label>
                <div className="dispatch-mode-buttons">
                  <button
                    className={`dispatch-mode-btn ${dispatchMode === 'dev-task' ? 'active' : ''}`}
                    onClick={() => setDispatchMode('dev-task')}
                  >
                    📦 dev-task
                    <small>Single agent — bugs, features, small tasks</small>
                  </button>
                  <button
                    className={`dispatch-mode-btn ${dispatchMode === 'claude-teams' ? 'active' : ''}`}
                    onClick={() => setDispatchMode('claude-teams')}
                  >
                    👥 claude-teams
                    <small>Multi-agent — new projects, large refactors</small>
                  </button>
                </div>

                <label className="modal-label">Target Project <span style={{ color: 'var(--text-dim)', fontWeight: 400, fontSize: '12px' }}>(optional)</span></label>
                <select
                  className="schedule-input"
                  value={dispatchProject}
                  onChange={(e) => setDispatchProject(e.target.value)}
                >
                  <option value="">No specific project</option>
                  {projects.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name} {p.has_docker_compose ? '🐳' : ''}
                    </option>
                  ))}
                </select>

                {dispatchProject && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px' }}>
                    <span
                      className="git-strategy-badge"
                      style={{
                        padding: '3px 10px',
                        borderRadius: '12px',
                        fontSize: '12px',
                        fontWeight: 600,
                        border: '1px solid',
                        borderColor: gitStrategy === 'pull_request' ? '#8b5cf6' : '#22c55e',
                        color: gitStrategy === 'pull_request' ? '#8b5cf6' : '#22c55e',
                        background: gitStrategy === 'pull_request' ? 'rgba(139, 92, 246, 0.08)' : 'rgba(34, 197, 94, 0.08)',
                      }}
                    >
                      {gitStrategy === 'pull_request' ? 'PR' : 'main'}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); setShowProjectSettings(true); }}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: '16px',
                        padding: '2px 4px',
                        color: 'var(--text-dim)',
                      }}
                      title="Project git settings"
                    >
                      &#x2699;&#xFE0F;
                    </button>
                  </div>
                )}

                <label className="modal-label">Prompt</label>
                <textarea
                  className="schedule-input"
                  value={dispatchPrompt}
                  onChange={(e) => setDispatchPrompt(e.target.value)}
                  rows={6}
                  style={{ resize: 'vertical', fontFamily: 'monospace', fontSize: '13px' }}
                  placeholder="What should Claude Code do?"
                />

                {dispatchError && (
                  <div className="scaffold-error">⚠️ {dispatchError}</div>
                )}

                <button
                  className="schedule-submit"
                  onClick={handleDispatch}
                  disabled={dispatching || !dispatchPrompt.trim()}
                  style={{ marginTop: '8px' }}
                >
                  {dispatching ? '⏳ Dispatching…' : '🚀 Dispatch Now'}
                </button>

                <div className="dispatch-form-hint">
                  After dispatching, run the watcher on your host machine:
                  <code style={{ display: 'block', marginTop: '4px', padding: '6px 8px', background: 'var(--bg)', borderRadius: '4px', fontSize: '12px' }}>
                    cd ~/Projects/Moltbot_ClaudeCode && ./scripts/dispatch-watcher.sh --once
                  </code>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
