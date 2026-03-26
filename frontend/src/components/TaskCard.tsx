import { useState, useEffect } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Task, TASK_TYPES, GitStrategy } from '../types';
import * as api from '../api';

interface TaskCardProps {
  task: Task;
  onRefresh: () => void;
  onOpenDetail: (task: Task) => void;
  onArchive: (task: Task) => void;
}

export default function TaskCard({ task, onRefresh, onOpenDetail, onArchive }: TaskCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : undefined,
  };

  const [editingTitle, setEditingTitle] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [gitStrategy, setGitStrategy] = useState<GitStrategy | null>(null);

  // Sync when task prop changes (after API refresh)
  useEffect(() => {
    setTitle(task.title);
  }, [task.title]);

  // Load git strategy for the task's project
  useEffect(() => {
    if (task.project_name) {
      api.fetchProjectSettings(task.project_name).then((s) => {
        setGitStrategy(s.git_strategy);
      }).catch(() => setGitStrategy(null));
    } else {
      setGitStrategy(null);
    }
  }, [task.project_name]);

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

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    await api.deleteTask(task.id);
    onRefresh();
  }

  const createdDate = new Date(task.created_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`task-card ${isDragging ? 'dragging' : ''}`}
      onClick={() => onOpenDetail(task)}
    >
      <div className="task-card-header">
        <span
          className="drag-handle"
          {...listeners}
          {...attributes}
          onClick={(e) => e.stopPropagation()}
        >
          ⋮⋮
        </span>

        {editingTitle ? (
          <input
            className="task-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={saveTitle}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveTitle();
              if (e.key === 'Escape') {
                setTitle(task.title);
                setEditingTitle(false);
              }
            }}
            autoFocus
          />
        ) : (
          <span
            className="task-title"
            onClick={(e) => {
              e.stopPropagation();
              setEditingTitle(true);
            }}
          >
            {task.title}
          </span>
        )}

        <button
          className="archive-btn"
          onClick={(e) => { e.stopPropagation(); onArchive(task); }}
          title="Archive task"
        >
          📦
        </button>
        <button className="delete-btn" onClick={handleDelete} title="Delete task">
          ×
        </button>
      </div>

      {task.description && (
        <div className="task-description">
          <span className="task-description-text">{task.description}</span>
        </div>
      )}

      <div className="task-meta">
        {task.task_type && task.task_type !== 'coding' && (() => {
          const tt = TASK_TYPES.find(t => t.id === task.task_type);
          return tt ? (
            <span className="task-type-badge" style={{ borderColor: tt.color, color: tt.color }}>
              {tt.emoji} {tt.label}
            </span>
          ) : null;
        })()}
        {task.project_name && (
          <span className="task-project-tag">📁 {task.project_name}</span>
        )}
        {task.project_name && gitStrategy && (
          <span
            style={{
              padding: '1px 6px',
              borderRadius: '8px',
              fontSize: '10px',
              fontWeight: 600,
              border: '1px solid',
              borderColor: gitStrategy === 'pull_request' ? '#8b5cf6' : '#22c55e',
              color: gitStrategy === 'pull_request' ? '#8b5cf6' : '#22c55e',
            }}
          >
            {gitStrategy === 'pull_request' ? 'PR' : 'main'}
          </span>
        )}
        <span>{createdDate}</span>
      </div>
    </div>
  );
}
