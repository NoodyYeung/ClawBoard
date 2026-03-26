import { useState, useEffect, useCallback, useRef } from 'react';
import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  closestCenter,
  CollisionDetection,
} from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { COLUMNS, Task, Status, TASK_TYPES, TaskType } from './types';
import * as api from './api';
import Column from './components/Column';
import ArchiveSection from './components/ArchiveSection';
import TaskDetailModal from './components/TaskDetailModal';
import CalendarView from './components/CalendarView';
import ProjectExplorer from './components/ProjectExplorer';
import MonitorView from './components/MonitorView';
import SettingsView from './components/SettingsView';

// Custom collision detection:
// 1. Prioritise archive drop zone when pointer is inside it.
// 2. Use pointerWithin as the primary strategy (physically checks if pointer is inside a droppable).
//    This fixes tall columns where closestCenter would pick the wrong column because the pointer
//    is nearer to an adjacent column's center when hovering near the top of a long column.
// 3. Fall back to closestCenter only when the pointer is between droppables.
const archiveAwareCollision: CollisionDetection = (args) => {
  const pointerCollisions = pointerWithin(args);
  const archiveHit = pointerCollisions.find((c) => c.id === 'archive');
  if (archiveHit) return [archiveHit];
  if (pointerCollisions.length > 0) return pointerCollisions;
  return closestCenter(args);
};

// ---- Board view (DnD Kanban) ----
function BoardView({
  tasks,
  archivedTasks,
  loadTasks,
  detailTask,
  setDetailTask,
}: {
  tasks: Task[];
  archivedTasks: Task[];
  loadTasks: () => Promise<void>;
  detailTask: Task | null;
  setDetailTask: (t: Task | null) => void;
}) {
  const [showArchive, setShowArchive] = useState(false);
  const [filterType, setFilterType] = useState<TaskType | ''>('');

  const getTasksByStatus = useCallback(
    (status: Status) =>
      tasks
        .filter((t) => t.status === status && !t.is_archived)
        .filter((t) => !filterType || (t.task_type || 'coding') === filterType)
        .sort((a, b) => a.position - b.position),
    [tasks, filterType],
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [activeOverColumnId, setActiveOverColumnId] = useState<string | null>(null);

  // Toast state for archive undo
  const [toast, setToast] = useState<{ key: number; title: string; taskId: number } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function handleArchive(task: Task) {
    await api.archiveTask(task.id);
    await loadTasks();
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ key: Date.now(), title: task.title, taskId: task.id });
    toastTimerRef.current = setTimeout(() => setToast(null), 5000);
  }

  async function handleUndo() {
    if (!toast) return;
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    await api.archiveTask(toast.taskId);
    await loadTasks();
    setToast(null);
  }

  function handleDragStart(event: DragStartEvent) {
    const task = tasks.find((t) => t.id === Number(event.active.id));
    setActiveTask(task || null);
  }

  function handleDragOver(event: DragOverEvent) {
    const { over } = event;
    if (!over) { setActiveOverColumnId(null); return; }
    const overId = String(over.id);
    const col = COLUMNS.find((c) => c.id === overId);
    if (col) { setActiveOverColumnId(col.id); return; }
    const overTask = tasks.find((t) => t.id === Number(overId));
    if (overTask) { setActiveOverColumnId(overTask.status); return; }
    setActiveOverColumnId(null);
  }

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveTask(null);
    setActiveOverColumnId(null);
    if (!over) return;

    const taskId = Number(active.id);
    const targetId = String(over.id);

    if (targetId === 'archive') {
      await api.archiveTask(taskId);
      await loadTasks();
      return;
    }

    const draggedTask = tasks.find((t) => t.id === taskId);
    if (!draggedTask) return;

    const targetColumn = COLUMNS.find((c) => c.id === targetId);
    if (targetColumn) {
      if (draggedTask.status !== targetColumn.id) {
        const targetTasks = getTasksByStatus(targetColumn.id);
        await api.moveTask(taskId, targetColumn.id, targetTasks.length);
        await loadTasks();
      }
      return;
    }

    const overTask = tasks.find((t) => t.id === Number(targetId));
    if (!overTask) return;

    if (draggedTask.status === overTask.status) {
      const columnTasks = getTasksByStatus(draggedTask.status);
      const oldIndex = columnTasks.findIndex((t) => t.id === taskId);
      const newIndex = columnTasks.findIndex((t) => t.id === overTask.id);
      if (oldIndex !== -1 && newIndex !== -1 && oldIndex !== newIndex) {
        const reordered = arrayMove(columnTasks, oldIndex, newIndex);
        const reorderedIds = reordered.map((t) => t.id);
        // Optimistic update via parent — not ideal but avoids prop drilling setTasks
        await api.reorderTasks(reorderedIds);
        await loadTasks();
      }
    } else {
      const targetTasks = getTasksByStatus(overTask.status);
      const insertAt = targetTasks.findIndex((t) => t.id === overTask.id);
      await api.moveTask(taskId, overTask.status, insertAt >= 0 ? insertAt : targetTasks.length);
      await loadTasks();
    }
  }

  return (
    <>
      <div className="board-filter-bar">
        <button
          className={`filter-chip ${filterType === '' ? 'active' : ''}`}
          onClick={() => setFilterType('')}
        >
          All
        </button>
        {TASK_TYPES.map((tt) => (
          <button
            key={tt.id}
            className={`filter-chip ${filterType === tt.id ? 'active' : ''}`}
            style={filterType === tt.id ? { borderColor: tt.color, color: tt.color } : {}}
            onClick={() => setFilterType(filterType === tt.id ? '' : tt.id)}
          >
            {tt.emoji} {tt.label}
          </button>
        ))}
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={archiveAwareCollision}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div className="board">
          {COLUMNS.map((column) => (
            <Column
              key={column.id}
              column={column}
              tasks={getTasksByStatus(column.id)}
              onRefresh={loadTasks}
              onOpenDetail={setDetailTask}
              isActiveTarget={activeOverColumnId === column.id}
              onArchive={handleArchive}
            />
          ))}
        </div>

        <DragOverlay dropAnimation={null}>
          {activeTask ? (
            <div className="task-card overlay">
              <div className="task-card-header">
                <span className="drag-handle">⋮⋮</span>
                <span className="task-title">{activeTask.title}</span>
              </div>
              {activeTask.description && (
                <p className="task-description-text">{activeTask.description}</p>
              )}
            </div>
          ) : null}
        </DragOverlay>

        {/* Archive section — always rendered so droppable zone is active for DnD */}
        <div className="board-archive-section">
          <ArchiveSection
            tasks={archivedTasks}
            onRestore={async (id) => {
              await api.archiveTask(id);
              await loadTasks();
            }}
            collapsed={!showArchive}
            onToggle={() => setShowArchive(!showArchive)}
          />
        </div>
      </DndContext>

      {toast && (
        <div className="archive-toast" key={toast.key}>
          <span>📦 "{toast.title}" archived</span>
          <button className="toast-undo-btn" onClick={handleUndo}>Undo</button>
          <button className="toast-close-btn" onClick={() => { if (toastTimerRef.current) clearTimeout(toastTimerRef.current); setToast(null); }}>×</button>
        </div>
      )}

      {detailTask && (
        <TaskDetailModal
          task={detailTask}
          onClose={() => setDetailTask(null)}
          onRefresh={async () => {
            await loadTasks();
            const allTasks = await api.fetchTasks(false);
            const updated = allTasks.find((t) => t.id === detailTask.id);
            if (updated) setDetailTask(updated);
          }}
        />
      )}
    </>
  );
}

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [archivedTasks, setArchivedTasks] = useState<Task[]>([]);
  const [detailTask, setDetailTask] = useState<Task | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const [dispatchMsg, setDispatchMsg] = useState<{ text: string; ok: boolean } | null>(null);

  async function handleDispatchNow() {
    setDispatching(true);
    setDispatchMsg(null);
    try {
      await api.triggerDispatch();
      setDispatchMsg({ text: '✅ Triggered!', ok: true });
    } catch {
      setDispatchMsg({ text: '❌ Failed', ok: false });
    } finally {
      setDispatching(false);
      setTimeout(() => setDispatchMsg(null), 3000);
    }
  }

  const loadTasks = useCallback(async () => {
    try {
      const [active, archived] = await Promise.all([
        api.fetchTasks(false),
        api.fetchTasks(true),
      ]);
      setTasks(active);
      setArchivedTasks(archived);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    }
  }, []);

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 60_000);
    return () => clearInterval(interval);
  }, [loadTasks]);

  return (
    <div className="app">
      <header className="header">
        <h1 className="header-title">🦞 ClawBoard</h1>
        <span className="header-subtitle">Task Management for OpenClaw</span>
        <nav className="header-tabs">
          <NavLink to="/board" className={({ isActive }) => `tab-btn${isActive ? ' active' : ''}`}>
            📋 Board
          </NavLink>
          <NavLink to="/calendar" className={({ isActive }) => `tab-btn${isActive ? ' active' : ''}`}>
            📅 Calendar
          </NavLink>
          <NavLink to="/projects" className={({ isActive }) => `tab-btn${isActive ? ' active' : ''}`}>
            📂 Projects
          </NavLink>
          <NavLink to="/monitor" className={({ isActive }) => `tab-btn${isActive ? ' active' : ''}`}>
            📡 Monitor
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `tab-btn${isActive ? ' active' : ''}`}>
            ⚙️ Settings
          </NavLink>
        </nav>
        <div className="header-actions">
          {dispatchMsg && (
            <span className={`dispatch-msg ${dispatchMsg.ok ? 'ok' : 'err'}`}>
              {dispatchMsg.text}
            </span>
          )}
          <button
            className="dispatch-now-btn"
            onClick={handleDispatchNow}
            disabled={dispatching}
            title="Trigger dispatch-watcher immediately to pick up queued tasks"
          >
            {dispatching ? '⏳ Running…' : '⚡ Dispatch Now'}
          </button>
        </div>
      </header>

      <Routes>
        <Route
          path="/board"
          element={
            <BoardView
              tasks={tasks}
              archivedTasks={archivedTasks}
              loadTasks={loadTasks}
              detailTask={detailTask}
              setDetailTask={setDetailTask}
            />
          }
        />
        <Route path="/calendar" element={<CalendarView />} />
        <Route path="/projects" element={<ProjectExplorer />} />
        <Route path="/monitor" element={<MonitorView />} />
        <Route path="/settings" element={<SettingsView />} />
        <Route path="*" element={<Navigate to="/board" replace />} />
      </Routes>
    </div>
  );
}

export default App;
