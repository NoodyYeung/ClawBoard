import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { CalendarEvent, CalendarViewMode, EventTag } from '../types';
import * as api from '../api';

// ---- date helpers ----

function startOfWeek(d: Date): Date {
  const day = d.getDay(); // 0=Sun
  const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Mon start
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatMonth(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

function formatHour(d: Date): string {
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

/** Local date key (YYYY-MM-DD) — avoids UTC shift that causes off-by-one day bugs. */
function localDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// ---- time grid constants ----
const SLOT_HEIGHT = 48; // px per 30-min slot
const TOTAL_SLOTS = 48; // 24h × 2

function getSlotTop(hours: number, minutes: number): number {
  return ((hours * 60 + minutes) / 30) * SLOT_HEIGHT;
}

// ---- component ----

export default function CalendarView() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [tags, setTags] = useState<EventTag[]>([]);
  const [selectedTagId, setSelectedTagId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<CalendarViewMode>('month');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(false);

  // Modal state
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [newEventTitle, setNewEventTitle] = useState('');
  const [newEventPrompt, setNewEventPrompt] = useState('');
  const [newEventTime, setNewEventTime] = useState('09:00');
  const [newEventEndTime, setNewEventEndTime] = useState('10:00');
  const [newEventTagId, setNewEventTagId] = useState<number | null>(null);
  const [editingEventId, setEditingEventId] = useState<number | null>(null);

  const weekScrollRef = useRef<HTMLDivElement>(null);

  // Compute date range for the view
  const dateRange = useMemo(() => {
    if (viewMode === 'week') {
      const weekStart = startOfWeek(currentDate);
      return {
        start: weekStart,
        end: addDays(weekStart, 7),
      };
    }
    // Month view: pad to full weeks
    const first = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
    const last = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);
    const monthStart = startOfWeek(first);
    const adjustedStart = monthStart > first ? addDays(monthStart, -7) : monthStart;
    const weeksNeeded = Math.ceil(
      (last.getTime() - adjustedStart.getTime()) / (7 * 86400000) + 1,
    );
    return {
      start: adjustedStart,
      end: addDays(adjustedStart, weeksNeeded * 7),
    };
  }, [viewMode, currentDate]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [evts, tgs] = await Promise.all([
        api.fetchCalendarEvents(
          dateRange.start.toISOString(),
          dateRange.end.toISOString(),
          true,
          selectedTagId || undefined,
        ),
        api.fetchTags(),
      ]);
      setEvents(evts.filter((e) => !e.is_scanner));
      setTags(tgs);
    } catch (err) {
      console.error('Failed to load calendar data:', err);
    } finally {
      setLoading(false);
    }
  }, [dateRange, selectedTagId]);

  useEffect(() => {
    loadData();
    // Auto-refresh every 60 seconds
    const interval = setInterval(loadData, 60_000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Auto-scroll week view to ~7 AM
  useEffect(() => {
    if (viewMode === 'week' && weekScrollRef.current) {
      weekScrollRef.current.scrollTop = getSlotTop(7, 0);
    }
  }, [viewMode, dateRange]);

  // ---- Navigation ----

  function navigate(dir: -1 | 1) {
    const d = new Date(currentDate);
    if (viewMode === 'month') {
      d.setMonth(d.getMonth() + dir);
    } else {
      d.setDate(d.getDate() + 7 * dir);
    }
    setCurrentDate(d);
  }

  function goToday() {
    setCurrentDate(new Date());
  }

  // ---- Events grouped by date ----

  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {};
    for (const evt of events) {
      const key = localDateKey(new Date(evt.start));
      if (!map[key]) map[key] = [];
      map[key].push(evt);
    }
    return map;
  }, [events]);

  // ---- Helpers for grid ----

  function getMonthDays(): Date[][] {
    const weeks: Date[][] = [];
    let d = new Date(dateRange.start);
    while (d < dateRange.end) {
      const week: Date[] = [];
      for (let i = 0; i < 7; i++) {
        week.push(new Date(d));
        d = addDays(d, 1);
      }
      weeks.push(week);
    }
    return weeks;
  }

  function getWeekDays(): Date[] {
    const days: Date[] = [];
    let d = new Date(dateRange.start);
    for (let i = 0; i < 7; i++) {
      days.push(new Date(d));
      d = addDays(d, 1);
    }
    return days;
  }

  function getDayEvents(d: Date): CalendarEvent[] {
    const key = localDateKey(d);
    return eventsByDate[key] || [];
  }

  // ---- Click Handlers ----

  function handleDayClick(day: Date) {
    setSelectedDate(day);
    setEditingEventId(null);
    setNewEventTitle('');
    setNewEventPrompt('');
    setNewEventTime('09:00');
    setNewEventEndTime('10:00');
    setNewEventTagId(null);
    setShowScheduleModal(true);
  }

  function handleSlotClick(day: Date, hour: number, minute: number) {
    setSelectedDate(day);
    setEditingEventId(null);
    setNewEventTime(`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`);
    // Default end time: +1 hour
    const endH = Math.min(hour + 1, 23);
    setNewEventEndTime(`${String(endH).padStart(2, '0')}:${String(minute).padStart(2, '0')}`);
    setNewEventTitle('');
    setNewEventPrompt('');
    setNewEventTagId(null);
    setShowScheduleModal(true);
  }

  async function handleEventClick(evt: CalendarEvent, e: React.MouseEvent) {
    e.stopPropagation();
    if (evt.source === 'event' && evt.event_id) {
      try {
        const item = await api.fetchCalendarEvent(evt.event_id);
        const d = new Date(item.scheduled_at);
        setSelectedDate(d);
        setEditingEventId(item.id);
        setNewEventTitle(item.title);
        setNewEventPrompt(item.prompt);
        setNewEventTime(
          `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
        );
        if (item.scheduled_end) {
          const ed = new Date(item.scheduled_end);
          setNewEventEndTime(
            `${String(ed.getHours()).padStart(2, '0')}:${String(ed.getMinutes()).padStart(2, '0')}`,
          );
        } else {
          const endH = Math.min(d.getHours() + 1, 23);
          setNewEventEndTime(
            `${String(endH).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
          );
        }
        setNewEventTagId(item.tag_id);
        setShowScheduleModal(true);
      } catch (err) {
        console.error('Failed to fetch event details:', err);
      }
    }
  }

  // ---- Save / Delete Event ----

  async function handleSaveEvent() {
    if (!newEventTitle.trim() || !selectedDate) return;
    const [hours, mins] = newEventTime.split(':').map(Number);
    const [endHours, endMins] = newEventEndTime.split(':').map(Number);

    // Build date in local timezone
    const dt = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate(), hours, mins, 0, 0);
    const endDt = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate(), endHours, endMins, 0, 0);
    // If end is before start (e.g. crosses midnight), push to next day
    if (endDt <= dt) endDt.setDate(endDt.getDate() + 1);

    try {
      if (editingEventId) {
        await api.updateCalendarEvent(editingEventId, {
          title: newEventTitle.trim(),
          prompt: newEventPrompt.trim(),
          tag_id: newEventTagId,
          scheduled_at: dt.toISOString(),
          scheduled_end: endDt.toISOString(),
        });
      } else {
        await api.createCalendarEvent({
          title: newEventTitle.trim(),
          prompt: newEventPrompt.trim(),
          tag_id: newEventTagId,
          scheduled_at: dt.toISOString(),
          scheduled_end: endDt.toISOString(),
        });
      }
      setShowScheduleModal(false);
      await loadData();
    } catch (err) {
      console.error('Failed to save event:', err);
    }
  }

  async function handleDeleteEvent() {
    if (!editingEventId) return;
    if (!confirm('Are you sure you want to delete this event?')) return;
    try {
      await api.deleteCalendarEvent(editingEventId);
      setShowScheduleModal(false);
      await loadData();
    } catch (err) {
      console.error('Failed to delete event:', err);
    }
  }

  // ---- Render ----

  const today = new Date();
  const isCurrentMonth = (d: Date) => d.getMonth() === currentDate.getMonth();

  return (
    <div className="calendar-container">
      {/* Toolbar */}
      <div className="calendar-toolbar">
        <div className="calendar-nav">
          <button className="cal-nav-btn" onClick={() => navigate(-1)}>
            ◀
          </button>
          <button className="cal-today-btn" onClick={goToday}>
            Today
          </button>
          <button className="cal-nav-btn" onClick={() => navigate(1)}>
            ▶
          </button>
          <h2 className="calendar-title">{formatMonth(currentDate)}</h2>
        </div>

        {/* Tag Filter */}
        <div className="calendar-filters">
          <span className="filter-label">Filter:</span>
          <select
            className="filter-select"
            value={selectedTagId || ''}
            onChange={(e) => setSelectedTagId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">All Events</option>
            {tags.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>

        <div className="calendar-view-toggle">
          <button
            className={`cal-view-btn ${viewMode === 'month' ? 'active' : ''}`}
            onClick={() => setViewMode('month')}
          >
            Month
          </button>
          <button
            className={`cal-view-btn ${viewMode === 'week' ? 'active' : ''}`}
            onClick={() => setViewMode('week')}
          >
            Week
          </button>
        </div>
      </div>

      {loading && <div className="calendar-loading">Loading…</div>}

      {/* Month View */}
      {viewMode === 'month' && (
        <div className="calendar-month">
          <div className="calendar-weekday-header">
            {WEEKDAYS.map((d) => (
              <div key={d} className="calendar-weekday">
                {d}
              </div>
            ))}
          </div>
          <div className="calendar-grid">
            {getMonthDays().map((week, wi) => (
              <div key={wi} className="calendar-week">
                {week.map((day) => {
                  const dayEvents = getDayEvents(day);
                  const isToday = isSameDay(day, today);
                  const otherMonth = !isCurrentMonth(day);
                  return (
                    <div
                      key={day.toISOString()}
                      className={`calendar-day ${isToday ? 'today' : ''} ${otherMonth ? 'other-month' : ''}`}
                      onClick={() => handleDayClick(day)}
                    >
                      <span className={`day-number ${isToday ? 'today-badge' : ''}`}>
                        {day.getDate()}
                      </span>
                      <div className="day-events">
                        {dayEvents.slice(0, 3).map((evt) => (
                          <div
                            key={evt.id}
                            className={`day-event ${evt.source}`}
                            style={{
                              borderLeftColor: evt.color || '#6b7280',
                              backgroundColor: `${evt.color || '#6b7280'}15`,
                            }}
                            onClick={(e) => handleEventClick(evt, e)}
                            title={`${evt.title}\n${formatHour(new Date(evt.start))}${evt.end ? ' – ' + formatHour(new Date(evt.end)) : ''}`}
                          >
                            <span className="day-event-time">
                              {formatHour(new Date(evt.start))}
                            </span>
                            <span className="day-event-title">
                              {evt.is_triggered ? '✅ ' : ''}{evt.title}
                            </span>
                          </div>
                        ))}
                        {dayEvents.length > 3 && (
                          <div className="day-event-more">
                            +{dayEvents.length - 3} more
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Week View */}
      {viewMode === 'week' && (
        <div className="calendar-week-view">
          <div className="week-header">
            <div className="week-header-gutter" />
            {getWeekDays().map((day) => {
              const isToday = isSameDay(day, today);
              return (
                <div key={day.toISOString()} className={`week-header-day ${isToday ? 'today' : ''}`}>
                  <span className="week-day-name">{WEEKDAYS[day.getDay() === 0 ? 6 : day.getDay() - 1]}</span>
                  <span className={`week-day-number ${isToday ? 'today-badge' : ''}`}>
                    {day.getDate()}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="week-timegrid-scroll" ref={weekScrollRef}>
            <div className="week-timegrid">
              {/* Time gutter */}
              <div className="week-time-gutter">
                {Array.from({ length: TOTAL_SLOTS }, (_, i) => {
                  const hour = Math.floor(i / 2);
                  const isHour = i % 2 === 0;
                  const period = hour >= 12 ? 'PM' : 'AM';
                  const dh = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
                  return (
                    <div key={i} className={`week-time-label ${isHour ? 'hour' : 'half'}`}>
                      {isHour && <span>{dh} {period}</span>}
                    </div>
                  );
                })}
              </div>

              {/* Day columns */}
              {getWeekDays().map((day) => {
                const dayEvents = getDayEvents(day);
                const isToday = isSameDay(day, today);

                // ---- Overlap layout: assign columns to overlapping events ----
                type LayoutEvt = {
                  evt: CalendarEvent;
                  startMin: number;
                  endMin: number;
                  col: number;
                  totalCols: number;
                };
                const sorted = dayEvents
                  .map((evt) => {
                    const s = new Date(evt.start);
                    const e = evt.end ? new Date(evt.end) : new Date(s.getTime() + 30 * 60000);
                    return {
                      evt,
                      startMin: s.getHours() * 60 + s.getMinutes(),
                      endMin: Math.max(e.getHours() * 60 + e.getMinutes(), s.getHours() * 60 + s.getMinutes() + 30),
                      col: 0,
                      totalCols: 1,
                    } as LayoutEvt;
                  })
                  .sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin);

                // Assign columns using a greedy algorithm
                const groups: LayoutEvt[][] = [];
                for (const item of sorted) {
                  let placed = false;
                  for (const group of groups) {
                    const lastInGroup = group[group.length - 1];
                    if (item.startMin >= lastInGroup.endMin) {
                      // No overlap with this group's last item
                      item.col = group[0].col;
                      group.push(item);
                      placed = true;
                      break;
                    }
                  }
                  if (!placed) {
                    item.col = groups.length;
                    groups.push([item]);
                  }
                }
                // Set totalCols for each cluster of overlapping events
                for (const item of sorted) {
                  // Find all items that overlap with this one
                  const overlapping = sorted.filter(
                    (o) => o.startMin < item.endMin && o.endMin > item.startMin,
                  );
                  const maxCol = Math.max(...overlapping.map((o) => o.col)) + 1;
                  for (const o of overlapping) {
                    o.totalCols = Math.max(o.totalCols, maxCol);
                  }
                }

                return (
                  <div key={day.toISOString()} className={`week-day-col ${isToday ? 'today' : ''}`}>
                    {/* Slot grid lines */}
                    {Array.from({ length: TOTAL_SLOTS }, (_, i) => {
                      const hour = Math.floor(i / 2);
                      const minute = (i % 2) * 30;
                      return (
                        <div
                          key={i}
                          className={`week-slot ${i % 2 === 0 ? 'hour-slot' : 'half-slot'}`}
                          onClick={() => handleSlotClick(day, hour, minute)}
                        />
                      );
                    })}

                    {/* Current time indicator */}
                    {isToday && (
                      <div
                        className="week-now-line"
                        style={{ top: `${getSlotTop(today.getHours(), today.getMinutes())}px` }}
                      />
                    )}

                    {/* Events overlaid with overlap columns */}
                    {sorted.map(({ evt, startMin, endMin, col, totalCols }) => {
                      const s = new Date(evt.start);
                      const dur = endMin - startMin;
                      const topPx = getSlotTop(Math.floor(startMin / 60), startMin % 60);
                      const hPx = (dur / 30) * SLOT_HEIGHT;
                      const widthPct = 100 / totalCols;
                      const leftPct = col * widthPct;
                      return (
                        <div
                          key={evt.id}
                          className={`week-event ${evt.source}`}
                          style={{
                            top: `${topPx}px`,
                            height: `${hPx}px`,
                            left: `calc(${leftPct}% + 2px)`,
                            width: `calc(${widthPct}% - 4px)`,
                            borderLeftColor: evt.color || '#6b7280',
                            backgroundColor: `${evt.color || '#6b7280'}25`,
                          }}
                          onClick={(e) => handleEventClick(evt, e)}
                        >
                          <div className="week-event-time">
                            {formatHour(s)}{evt.end ? ` – ${formatHour(new Date(evt.end))}` : ''}
                          </div>
                          <div className="week-event-title">
                            {evt.is_triggered ? '✅ ' : ''}{evt.title}
                          </div>
                          {evt.tag_name && (
                            <div className="week-event-status" style={{ color: evt.tag_color || '#6b7280' }}>
                              {evt.tag_name}
                            </div>
                          )}
                          {evt.cron_expr && (
                            <div className="week-event-cron">🔄 {evt.cron_expr}</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Schedule Task Modal */}
      {showScheduleModal && selectedDate && (
        <div className="modal-overlay" onClick={() => setShowScheduleModal(false)}>
          <div
            className="modal-content schedule-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>
                {editingEventId ? '✏️ Edit Event' : '📅 Schedule Event'} —{' '}
                {selectedDate.toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric',
                })}
              </h3>
              <button className="modal-close" onClick={() => setShowScheduleModal(false)}>
                ✕
              </button>
            </div>
            <div className="schedule-form">
              <label className="modal-label">Event Title</label>
              <input
                className="schedule-input"
                value={newEventTitle}
                onChange={(e) => setNewEventTitle(e.target.value)}
                placeholder="What needs to be done?"
                autoFocus
              />

              <label className="modal-label">Prompt / Description</label>
              <textarea
                className="schedule-input"
                value={newEventPrompt}
                onChange={(e) => setNewEventPrompt(e.target.value)}
                placeholder="Instructions for OpenClaw..."
                rows={4}
                style={{ resize: 'vertical' }}
              />

              <div className="schedule-row">
                <div className="schedule-field">
                  <label className="modal-label">Start Time</label>
                  <input
                    type="time"
                    className="schedule-input"
                    value={newEventTime}
                    onChange={(e) => {
                      setNewEventTime(e.target.value);
                      // Auto-advance end time +1h
                      const [h, m] = e.target.value.split(':').map(Number);
                      const endH = Math.min(h + 1, 23);
                      setNewEventEndTime(`${String(endH).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
                    }}
                  />
                </div>
                <div className="schedule-field">
                  <label className="modal-label">End Time</label>
                  <input
                    type="time"
                    className="schedule-input"
                    value={newEventEndTime}
                    onChange={(e) => setNewEventEndTime(e.target.value)}
                  />
                </div>
              </div>

              <div className="schedule-row">
                <div className="schedule-field">
                  <label className="modal-label">Tag</label>
                  <select
                    className="schedule-input"
                    value={newEventTagId || ''}
                    onChange={(e) => setNewEventTagId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">No Tag</option>
                    {tags.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="schedule-field" />
              </div>

              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <button
                  className="schedule-submit"
                  style={{ flex: 1 }}
                  onClick={handleSaveEvent}
                  disabled={!newEventTitle.trim()}
                >
                  {editingEventId ? 'Save Changes' : 'Create Event'}
                </button>
                {editingEventId && (
                  <button
                    className="schedule-submit"
                    style={{ background: '#ef4444' }}
                    onClick={handleDeleteEvent}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
