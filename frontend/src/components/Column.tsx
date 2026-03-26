import { useState } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ColumnDef, Task } from '../types';
import * as api from '../api';
import TaskCard from './TaskCard';

interface ColumnProps {
  column: ColumnDef;
  tasks: Task[];
  onRefresh: () => void;
  onOpenDetail: (task: Task) => void;
  isActiveTarget?: boolean;
  onArchive: (task: Task) => void;
}

export default function Column({ column, tasks, onRefresh, onOpenDetail, isActiveTarget = false, onArchive }: ColumnProps) {
  const { isOver, setNodeRef } = useDroppable({ id: column.id });
  const [isAdding, setIsAdding] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  async function handleAddTask() {
    const trimmed = newTitle.trim();
    if (!trimmed) {
      setIsAdding(false);
      setNewTitle('');
      return;
    }
    try {
      await api.createTask({ title: trimmed, status: column.id });
      setNewTitle('');
      setIsAdding(false);
      onRefresh();
    } catch (err) {
      console.error('Failed to create task:', err);
    }
  }

  return (
    <div
      ref={setNodeRef}
      className={`column ${isOver || isActiveTarget ? 'drag-over' : ''}`}
    >
      <div className="column-header" style={{ borderBottomColor: column.color }}>
        <span className="column-title">
          {column.emoji} {column.title}
        </span>
        <span className="column-count">{tasks.length}</span>
      </div>

      <div className="tasks-list">
        <SortableContext items={tasks.map(t => t.id)} strategy={verticalListSortingStrategy}>
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} onRefresh={onRefresh} onOpenDetail={onOpenDetail} onArchive={onArchive} />
          ))}
        </SortableContext>
      </div>

      {isAdding ? (
        <div className="new-task-form">
          <input
            className="new-task-input"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onBlur={handleAddTask}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAddTask();
              if (e.key === 'Escape') {
                setIsAdding(false);
                setNewTitle('');
              }
            }}
            placeholder="Task title… (Enter to save, Esc to cancel)"
            autoFocus
          />
        </div>
      ) : (
        <button className="add-task-btn" onClick={() => setIsAdding(true)}>
          + New Task
        </button>
      )}
    </div>
  );
}
