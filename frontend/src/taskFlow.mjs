export const workStates = ['Pending', 'In Progress'];
export const dateKey = (date = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
export const isWorking = (task) => workStates.includes(task.status);
export const needsAvailabilityResponse = task => task.maintenanceOnCall?.state === 'Awaiting response';
export const isLate = (task, now = Date.now()) => isWorking(task) && !task.maintenanceOnCall && !!task.dueDate && new Date(`${task.dueDate}T${task.dueTime || '23:59:59'}+08:00`).getTime() < now;
export function canStartTask(task, now = Date.now()) {
  if (task.maintenanceOnCall) return task.maintenanceOnCall.state === 'Accepted' && !!task.maintenanceOnCall.scheduleApproved;
  if (!task.dueDate || !task.dueTime) return false;
  const time = String(task.dueTime);
  const scheduledAt = new Date(`${task.dueDate}T${time.length === 5 ? `${time}:00` : time}+08:00`).getTime();
  return Number.isFinite(scheduledAt) && dateKey(new Date(now)) === task.dueDate && now <= scheduledAt;
}
export const checklistCount = (task) => ({ done: (task.checklist || []).filter(item => item.done).length, total: (task.checklist || []).length });
export const readyForReview = (task) => task.status === 'In Progress' && checklistCount(task).total > 0 && checklistCount(task).done === checklistCount(task).total;
export function orderTasks(tasks, now = Date.now()) {
  const rank = task => isLate(task, now) ? 0 : task.status === 'In Progress' ? 1 : task.status === 'Pending' ? 2 : task.status === 'Pending Review' ? 3 : 4;
  return [...tasks].sort((a,b) => rank(a) - rank(b) || `${a.dueDate || '9999'} ${a.dueTime || '23:59'}`.localeCompare(`${b.dueDate || '9999'} ${b.dueTime || '23:59'}`) || ({High:0,Medium:1,Low:2}[a.priority] ?? 3) - ({High:0,Medium:1,Low:2}[b.priority] ?? 3));
}
export function dateLabel(value, options = {}) {
  return value ? new Date(`${value}T00:00:00`).toLocaleDateString('en-PH', { month:'short', day:'numeric', ...options }) : 'Unscheduled';
}
export function timeLabel(value) {
  if (!value) return 'Flexible time';
  return new Date(`2000-01-01T${value}`).toLocaleTimeString('en-PH', { hour:'numeric', minute:'2-digit' });
}

export function returnedFeedback(task) {
  if (task.status !== 'In Progress') return '';
  const latest = (task.statusHistory || []).at(-1);
  return latest?.note?.startsWith('Returned for correction:') ? latest.note.slice('Returned for correction:'.length).trim() : '';
}

export function matchesFocus(task, focus, now = Date.now()) {
  switch (focus) {
    case 'To do': return task.status === 'Pending';
    case 'In progress': return task.status === 'In Progress';
    case 'Due today': return task.dueDate === dateKey(new Date(now));
    case 'Overdue': return isLate(task, now);
    case 'Needs correction': return !!returnedFeedback(task);
    case 'Unscheduled': return !task.dueDate;
    default: return true;
  }
}
export function filterTaskQueue(tasks, {view = 'My work', focus = 'All work', search = '', priority = ''} = {}, now = Date.now()) {
  const query = search.trim().toLowerCase();
  return orderTasks(tasks.filter(task => {
    const inView = view === 'Schedule' ? task.status !== 'Cancelled'
      : view === 'My work' ? isWorking(task) && !needsAvailabilityResponse(task) && !isLate(task, now)
      : view === 'In review' ? task.status === 'Pending Review'
      : ['Completed', 'Cancelled'].includes(task.status) || isLate(task, now);
    return inView && (view !== 'My work' || matchesFocus(task,focus,now)) && (!priority || task.priority === priority)
      && `${task.title || ''} ${task.villaName || ''} ${task.bookingCode || ''} ${task.description || ''}`.toLowerCase().includes(query);
  }),now);
}
