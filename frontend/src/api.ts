import { Task, TaskMessage, TaskType, CalendarEvent, CalendarEventItem, EventTag, ProjectSummary, PrPolicy, ProjectSettingsData, FileNode, FileContent, ScaffoldRequest, ScaffoldResponse, DispatchRecord, DispatchCreate, GitBranchInfo, MonitorOverview, SessionStatus, SystemSettings } from './types';

const API = '/api/tasks';
const CAL_API = '/api/calendar';
const PROJ_API = '/api/projects';
const DISPATCH_API = '/api/dispatch';
const MONITOR_API = '/api/monitor';
const PROJECT_SETTINGS_API = '/api/project-settings';

interface TaskCreate {
  title: string;
  description?: string;
  status?: string;
  project_name?: string;
  task_type?: TaskType;
  task_meta?: Record<string, any>;
}

export async function fetchTasks(archived = false): Promise<Task[]> {
  const res = await fetch(`${API}/?archived=${archived}`);
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`);
  return res.json();
}

export async function createTask(data: TaskCreate): Promise<Task> {
  const res = await fetch(`${API}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to create task: ${res.status}`);
  return res.json();
}

export async function updateTask(id: number, data: Partial<Task>): Promise<Task> {
  const res = await fetch(`${API}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update task: ${res.status}`);
  return res.json();
}

export async function moveTask(id: number, status: string, position: number): Promise<Task> {
  const res = await fetch(`${API}/${id}/move`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, position }),
  });
  if (!res.ok) throw new Error(`Failed to move task: ${res.status}`);
  return res.json();
}

export async function archiveTask(id: number): Promise<Task> {
  const res = await fetch(`${API}/${id}/archive`, {
    method: 'PUT',
  });
  if (!res.ok) throw new Error(`Failed to archive task: ${res.status}`);
  return res.json();
}

export async function reorderTasks(taskIds: number[]): Promise<Task[]> {
  const res = await fetch(`${API}/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_ids: taskIds }),
  });
  if (!res.ok) throw new Error(`Failed to reorder tasks: ${res.status}`);
  return res.json();
}

export async function deleteTask(id: number): Promise<void> {
  const res = await fetch(`${API}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete task: ${res.status}`);
}

// ---- Task Messages (append-only activity log) ----

export async function fetchMessages(taskId: number): Promise<TaskMessage[]> {
  const res = await fetch(`${API}/${taskId}/messages`);
  if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`);
  return res.json();
}

export async function addMessage(
  taskId: number,
  message: string,
  author = 'user',
  eventType = 'comment',
): Promise<TaskMessage> {
  const res = await fetch(`${API}/${taskId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, author, event_type: eventType }),
  });
  if (!res.ok) throw new Error(`Failed to add message: ${res.status}`);
  return res.json();
}

// ---- Calendar ----

export async function fetchCalendarEvents(
  start?: string,
  end?: string,
  includeCron = true,
  tagId?: number,
): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  params.set('include_cron', String(includeCron));
  if (tagId) params.set('tag_id', String(tagId));
  const res = await fetch(`${CAL_API}/events?${params}`);
  if (!res.ok) throw new Error(`Failed to fetch calendar events: ${res.status}`);
  return res.json();
}

// ---- Event Tags ----

export async function fetchTags(): Promise<EventTag[]> {
  const res = await fetch(`${CAL_API}/tags`);
  if (!res.ok) throw new Error(`Failed to fetch tags: ${res.status}`);
  return res.json();
}

export async function createTag(name: string, color: string): Promise<EventTag> {
  const res = await fetch(`${CAL_API}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  });
  if (!res.ok) throw new Error(`Failed to create tag: ${res.status}`);
  return res.json();
}

export async function deleteTag(id: number): Promise<void> {
  const res = await fetch(`${CAL_API}/tags/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete tag: ${res.status}`);
}

// ---- Calendar Event Items CRUD ----

export async function createCalendarEvent(data: {
  title: string;
  prompt: string;
  tag_id?: number | null;
  scheduled_at: string;
  scheduled_end?: string;
}): Promise<CalendarEventItem> {
  const res = await fetch(`${CAL_API}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to create calendar event: ${res.status}`);
  return res.json();
}

export async function updateCalendarEvent(
  id: number,
  data: Partial<CalendarEventItem>,
): Promise<CalendarEventItem> {
  const res = await fetch(`${CAL_API}/items/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to update calendar event: ${res.status}`);
  return res.json();
}

export async function deleteCalendarEvent(id: number): Promise<void> {
  const res = await fetch(`${CAL_API}/items/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete calendar event: ${res.status}`);
}

export async function fetchCalendarEvent(id: number): Promise<CalendarEventItem> {
  const res = await fetch(`${CAL_API}/items/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch calendar event: ${res.status}`);
  return res.json();
}

// ---- Project Explorer ----

export async function fetchProjectNames(): Promise<string[]> {
  const res = await fetch(`${PROJ_API}/names`);
  if (!res.ok) throw new Error(`Failed to fetch project names: ${res.status}`);
  return res.json();
}

export async function fetchProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${PROJ_API}/`);
  if (!res.ok) throw new Error(`Failed to fetch projects: ${res.status}`);
  return res.json();
}

export async function fetchProjectTree(projectName: string): Promise<FileNode[]> {
  const res = await fetch(`${PROJ_API}/${encodeURIComponent(projectName)}/tree`);
  if (!res.ok) throw new Error(`Failed to fetch project tree: ${res.status}`);
  return res.json();
}

export async function fetchFileContent(projectName: string, path: string): Promise<FileContent> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${PROJ_API}/${encodeURIComponent(projectName)}/file?${params}`);
  if (!res.ok) throw new Error(`Failed to fetch file: ${res.status}`);
  return res.json();
}

export async function scaffoldProject(data: ScaffoldRequest): Promise<ScaffoldResponse> {
  const res = await fetch(`${PROJ_API}/scaffold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Failed to scaffold project: ${res.status}`);
  }
  return res.json();
}

export async function deleteProject(projectName: string): Promise<void> {
  const res = await fetch(`${PROJ_API}/${encodeURIComponent(projectName)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete project: ${res.status}`);
}

export async function updateProjectSettings(
  projectName: string,
  settings: { pr_policy: PrPolicy },
): Promise<{ pr_policy: PrPolicy; updated_at: string }> {
  const res = await fetch(`${PROJ_API}/${encodeURIComponent(projectName)}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Failed to update settings: ${res.status}`);
  }
  return res.json();
}

// ---- Project Settings (git strategy) ----

export async function fetchProjectSettings(projectKey: string): Promise<ProjectSettingsData> {
  const res = await fetch(`${PROJECT_SETTINGS_API}/${encodeURIComponent(projectKey)}`);
  if (!res.ok) throw new Error(`Failed to fetch project settings: ${res.status}`);
  return res.json();
}

export async function updateProjectGitStrategy(
  projectKey: string,
  data: { git_strategy: string; default_branch: string },
): Promise<ProjectSettingsData> {
  const res = await fetch(`${PROJECT_SETTINGS_API}/${encodeURIComponent(projectKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Failed to update project settings: ${res.status}`);
  }
  return res.json();
}

// ---- Dispatch (ClawBoard ↔ Claude Code) ----

export async function createDispatch(taskId: number, data: DispatchCreate): Promise<DispatchRecord> {
  const res = await fetch(`${DISPATCH_API}/${taskId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Failed to dispatch: ${res.status}`);
  }
  return res.json();
}

export async function fetchActiveDispatches(): Promise<DispatchRecord[]> {
  const res = await fetch(`${DISPATCH_API}/active`);
  if (!res.ok) throw new Error(`Failed to fetch active dispatches: ${res.status}`);
  return res.json();
}

export async function fetchDispatchHistory(taskId?: number): Promise<DispatchRecord[]> {
  const params = new URLSearchParams();
  if (taskId) params.set('task_id', String(taskId));
  const res = await fetch(`${DISPATCH_API}/history?${params}`);
  if (!res.ok) throw new Error(`Failed to fetch dispatch history: ${res.status}`);
  return res.json();
}

export async function fetchDispatch(dispatchId: number): Promise<DispatchRecord> {
  const res = await fetch(`${DISPATCH_API}/${dispatchId}`);
  if (!res.ok) throw new Error(`Failed to fetch dispatch: ${res.status}`);
  return res.json();
}

// ---- Git Branches ----

export async function fetchGitBranches(projectName: string): Promise<GitBranchInfo> {
  const res = await fetch(`${PROJ_API}/${encodeURIComponent(projectName)}/git/branches`);
  if (!res.ok) throw new Error(`Failed to fetch branches: ${res.status}`);
  return res.json();
}

export async function checkoutBranch(projectName: string, branch: string): Promise<{ message: string; branch: string }> {
  const res = await fetch(`${PROJ_API}/${encodeURIComponent(projectName)}/git/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ branch }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Checkout failed: ${res.status}`);
  }
  return res.json();
}

// ---- Monitor (live Claude Code activity) ----

export async function fetchMonitorStatus(maxEvents = 30): Promise<MonitorOverview> {
  const res = await fetch(`${MONITOR_API}/status?max_events=${maxEvents}`);
  if (!res.ok) throw new Error(`Failed to fetch monitor status: ${res.status}`);
  return res.json();
}

export async function fetchSessionDetail(dispatchId: number, maxEvents = 50): Promise<SessionStatus> {
  const res = await fetch(`${MONITOR_API}/session/${dispatchId}?max_events=${maxEvents}`);
  if (!res.ok) throw new Error(`Failed to fetch session detail: ${res.status}`);
  return res.json();
}

// ---- System Settings ----

const SETTINGS_API = '/api/settings';

export async function triggerDispatch(): Promise<{ triggered: boolean }> {
  const res = await fetch(`${DISPATCH_API}/run-now`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to trigger dispatch: ${res.status}`);
  return res.json();
}

export async function fetchSettings(): Promise<SystemSettings> {
  const res = await fetch(`${SETTINGS_API}/`);
  if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`);
  const raw = await res.json();
  return {
    llm_provider: raw.llm_provider ?? 'claude',
    minimax_api_key: raw.minimax_api_key ?? '',
    minimax_base_url: raw.minimax_base_url ?? 'https://api.minimax.io/anthropic',
    minimax_model: raw.minimax_model ?? 'MiniMax-M2.5',
  };
}

export async function updateSettings(settings: Partial<SystemSettings>): Promise<SystemSettings> {
  const res = await fetch(`${SETTINGS_API}/`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Failed to update settings: ${res.status}`);
  }
  const raw = await res.json();
  return {
    llm_provider: raw.llm_provider ?? 'claude',
    minimax_api_key: raw.minimax_api_key ?? '',
    minimax_base_url: raw.minimax_base_url ?? 'https://api.minimax.io/anthropic',
    minimax_model: raw.minimax_model ?? 'MiniMax-M2.5',
  };
}
