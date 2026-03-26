import { useDroppable } from '@dnd-kit/core';
import { Task, COLUMNS } from '../types';

interface ArchiveSectionProps {
  tasks: Task[];
  onRestore: (id: number) => void;
  collapsed?: boolean;
  onToggle?: () => void;
}

function getStatusColor(status: string): string {
  const col = COLUMNS.find((c) => c.id === status);
  return col?.color || '#6b7280';
}

function getStatusLabel(status: string): string {
  const col = COLUMNS.find((c) => c.id === status);
  return col?.title || status.replace('_', ' ');
}

export default function ArchiveSection({ tasks, onRestore, collapsed = false, onToggle }: ArchiveSectionProps) {
  const { isOver, setNodeRef } = useDroppable({ id: 'archive' });

  return (
    <div
      ref={setNodeRef}
      className={`archive-section ${isOver ? 'drag-over' : ''} ${collapsed ? 'collapsed' : ''}`}
    >
      {/* Toggle button — always visible */}
      {onToggle && (
        <button
          className={`archive-toggle-bottom ${!collapsed ? 'active' : ''}`}
          onClick={onToggle}
        >
          {collapsed ? '▶' : '▼'} 📦 Archive ({tasks.length})
        </button>
      )}

      {/* Drag hint — visible when dragging over collapsed section */}
      {collapsed && isOver && (
        <div className="archive-drop-hint">Drop here to archive</div>
      )}

      {/* Expanded content */}
      {!collapsed && (
        <>
          <div className="archive-header">
            <h2>📦 Archived Tasks</h2>
            <span className="column-count">{tasks.length}</span>
          </div>

          {tasks.length === 0 ? (
            <p className="archive-empty">
              Drag tasks here to archive them, or they'll appear here when archived
            </p>
          ) : (
            <div className="archive-tasks">
              {tasks.map((task) => (
                <div key={task.id} className="archived-card">
                  <div className="archived-card-header">
                    <span
                      className="task-status-badge"
                      style={{ backgroundColor: getStatusColor(task.status) }}
                    >
                      {getStatusLabel(task.status)}
                    </span>
                  </div>
                  <h4>{task.title}</h4>
                  {task.description && (
                    <p className="task-description-text">{task.description}</p>
                  )}
                  <button
                    className="restore-btn"
                    onClick={() => onRestore(task.id)}
                  >
                    ↩ Restore
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
