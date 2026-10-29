export const MAINTENANCE_SOURCE = 'manual-maintenance-request';
export const NEXT_MAINTENANCE_STATUSES = {
  Pending: ['Pending', 'In Progress', 'Cancelled'],
  'In Progress': ['In Progress', 'Pending Review', 'Cancelled'],
  'Pending Review': ['Pending Review', 'In Progress', 'Completed', 'Cancelled'],
  Completed: ['Completed'],
  Cancelled: ['Cancelled'],
};
export const isClosed = row => ['Completed', 'Cancelled'].includes(row.status);
export const onCallState = row => row?.maintenance?.onCall?.state || '';
export const needsAttention = row => !isClosed(row) && !!row.maintenance?.onCall?.attentionNeeded;
export function arrivalInput(value) {
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time + 8 * 3600000).toISOString().slice(0, 16) : '';
}
function clockValue(value, fallback) {
  const text = String(value || fallback).trim();
  const twentyFourHour = text.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (twentyFourHour) return `${String(Number(twentyFourHour[1])).padStart(2, '0')}:${twentyFourHour[2]}`;
  const twelveHour = text.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!twelveHour) return '';
  let hour = Number(twelveHour[1]) % 12;
  if (twelveHour[3].toUpperCase() === 'PM') hour += 12;
  return `${String(hour).padStart(2, '0')}:${twelveHour[2]}`;
}
export function conflictsWithBooking(arrival, period) {
  if (!arrival || !period?.checkInDate || !period?.checkOutDate) return false;
  const arrivalValue = arrival.length === 16 ? `${arrival}:00` : arrival;
  const checkInTime = clockValue(period.checkInTime, '3:00 PM');
  const checkOutTime = clockValue(period.checkOutTime, '00:00');
  if (!checkInTime || !checkOutTime) return false;
  const start = `${period.checkInDate}T${checkInTime}:00`;
  const end = period.checkOutTime
    ? `${period.checkOutDate}T${checkOutTime}:00`
    : `${period.checkOutDate}T23:59:59`;
  return arrivalValue >= start && arrivalValue < end;
}
export const arrivalTimestamp = value => value ? `${value}:00+08:00` : null;
export const phoneHref = phone => {
  const value = String(phone || '').replace(/[^+\d]/g, '');
  return value.replace(/\D/g, '').length >= 7 ? `tel:${value}` : '';
};
export function maintenanceForm(row, technicianId = '', defaults = {}) {
  const meta = row?.maintenance || {};
  return {
    title: row?.title || '', description: row?.description || '',
    kind: meta.kind || defaults.kind || 'Repair', blocksBooking: row ? !!meta.blocksBooking : !!defaults.blocksBooking,
    assignedStaffId: row?.assignedStaffId || technicianId, villaId: meta.villaId || defaults.villaId || '',
    location: meta.location || '', equipment: meta.equipment || '', reportedBy: meta.reportedBy || '',
    priority: row?.priority || 'Medium', dueDate: row?.dueDate || '',
    contactMethod: meta.contactMethod || 'Not contacted', contactNotes: meta.contactNotes || '',
    messengerUrl: meta.messengerUrl || '', repairNotes: meta.repairNotes || row?.notes || '',
    verificationNote: meta.verificationNote || '', waitingForParts: meta.waitingForParts || false,
    partsNotes: meta.partsNotes || '', repairCost: meta.repairCost || '0.00',
    photos: row?.attachments || [], status: row?.status || 'Pending',
    responseWindowMinutes: meta.onCall?.responseWindowMinutes || '', responseAction: '',
    expectedArrival: arrivalInput(meta.onCall?.expectedArrival), responseNotes: '',
  };
}
export function maintenancePayload(form, row) {
  const payload = { ...form, assignedStaffId: form.assignedStaffId || null, dueDate: form.dueDate || null,
    repairCost: String(form.repairCost || '0'), responseWindowMinutes: form.responseWindowMinutes ? Number(form.responseWindowMinutes) : null,
    expectedArrival: arrivalTimestamp(form.expectedArrival) };
  if (row) payload.expectedUpdatedAt = row.updatedAt || null;
  else {
    for (const key of ['status', 'responseAction', 'expectedArrival', 'responseNotes']) delete payload[key];
  }
  return payload;
}
