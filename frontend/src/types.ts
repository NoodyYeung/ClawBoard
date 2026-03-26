export type TaskType = 'coding' | 'video-editing' | 'research' | 'design';

export const TASK_TYPES: { id: TaskType; label: string; emoji: string; color: string }[] = [
  { id: 'coding', label: 'Coding', emoji: '💻', color: '#3b82f6' },
  { id: 'video-editing', label: 'Video Editing', emoji: '🎬', color: '#f59e0b' },
  { id: 'research', label: 'Research', emoji: '🔬', color: '#8b5cf6' },
  { id: 'design', label: 'Design', emoji: '🎨', color: '#ec4899' },
];

export interface Task {
  id: number;
  title: string;
  description: string;
  status: Status;
  position: number;
  is_archived: boolean;
  project_name: string | null;
  task_type: TaskType;
  task_meta: Record<string, any> | null;
  scheduled_at: string | null;
  scheduled_end: string | null;
  cron_job_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskMessage {
  id: number;
  task_id: number;
  message: string;
  author: string;
  event_type: string;
  status_from: string | null;
  status_to: string | null;
  created_at: string;
}

export type Status = 'planning' | 'planned' | 'in_progress' | 'testing' | 'review' | 'done';

export interface ColumnDef {
  id: Status;
  title: string;
  emoji: string;
  color: string;
}

export const COLUMNS: ColumnDef[] = [
  { id: 'planning', title: 'Planning', emoji: '💭', color: '#9ca3af' },
  { id: 'planned', title: 'Planned', emoji: '📝', color: '#6b7280' },
  { id: 'in_progress', title: 'In Progress', emoji: '⚙️', color: '#3b82f6' },
  { id: 'testing', title: 'Testing', emoji: '🧪', color: '#8b5cf6' },
  { id: 'review', title: 'Review', emoji: '👀', color: '#f59e0b' },
  { id: 'done', title: 'Done', emoji: '✅', color: '#22c55e' },
];

export interface StatusSummary {
  planning: number;
  planned: number;
  in_progress: number;
  testing: number;
  review: number;
  done: number;
  archived: number;
}

// ---- Calendar types ----

export interface EventTag {
  id: number;
  name: string;
  color: string;
  created_at: string;
}

export interface CalendarEventItem {
  id: number;
  title: string;
  prompt: string;
  tag_id: number | null;
  tag_name: string | null;
  tag_color: string | null;
  scheduled_at: string;
  scheduled_end: string | null;
  is_triggered: boolean;
  created_at: string;
  updated_at: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  description: string;
  start: string;
  end: string | null;
  source: 'event' | 'cron';
  tag_name: string | null;
  tag_color: string | null;
  cron_name: string | null;
  cron_expr: string | null;
  color: string | null;
  is_scanner: boolean;
  event_id: number | null;
  is_triggered: boolean;
}

export type CalendarViewMode = 'month' | 'week';

// ---- Project Explorer types ----

export type PrPolicy = 'require_pr' | 'direct_commit';

export interface ProjectSummary {
  name: string;
  path: string;
  description: string;
  has_docker_compose: boolean;
  has_dockerfile: boolean;
  has_readme: boolean;
  has_claude_md: boolean;
  services: string[];
  created_at: string | null;
  updated_at: string | null;
  file_count: number;
  dir_count: number;
  pr_policy: PrPolicy;
}

export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified: string | null;
  children: FileNode[] | null;
}

export interface FileContent {
  path: string;
  name: string;
  content: string;
  size: number;
  modified: string | null;
  language: string;
}

export interface ScaffoldRequest {
  name: string;
  description?: string;
  include_db?: boolean;
  include_redis?: boolean;
  python_deps?: string[];
}

export interface ScaffoldResponse {
  name: string;
  path: string;
  files_created: number;
  message: string;
}

// ---- Project Settings (git strategy) ----

export type GitStrategy = 'direct_commit' | 'pull_request';

export interface ProjectSettingsData {
  project_key: string;
  git_strategy: GitStrategy;
  default_branch: string;
}

// ---- Dispatch types (ClawBoard ↔ Claude Code) ----

export type DispatchStatus = 'queued' | 'running' | 'completed' | 'failed' | 'stopped';

export interface DispatchRecord {
  id: number;
  task_id: number | null;
  status: DispatchStatus;
  prompt: string;
  project_name: string | null;
  workdir: string | null;
  agent_mode: 'dev-task' | 'claude-teams';
  session_id: string | null;
  exit_code: number | null;
  output: string | null;
  error_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DispatchCreate {
  prompt?: string;
  project_name?: string;
  agent_mode?: 'dev-task' | 'claude-teams';
}

// ---- Git types ----

export interface GitBranchInfo {
  current: string;
  branches: string[];
}

// ---- Monitor types (live Claude Code activity) ----

export interface ActivityEntry {
  timestamp: string | null;
  type: 'thinking' | 'tool_use' | 'tool_result' | 'text' | 'error' | 'status';
  summary: string;
  detail: string | null;
}

export interface SessionStatus {
  dispatch_id: number | null;
  task_id: number | null;
  task_title: string | null;
  project_name: string | null;
  dispatch_status: string | null;
  session_id: string | null;
  session_file: string | null;
  started_at: string | null;
  total_messages: number;
  total_tokens: number;
  total_cost_usd: number;
  activity: ActivityEntry[];
}

export interface MonitorOverview {
  has_active: boolean;
  active_dispatches: number;
  sessions: SessionStatus[];
  recent_completed: SessionStatus[];
}

// ---- System Settings ----

export type LLMProvider = 'claude' | 'minimax';

export interface SystemSettings {
  llm_provider: LLMProvider;
  minimax_api_key: string;
  minimax_base_url: string;
  minimax_model: string;
}
