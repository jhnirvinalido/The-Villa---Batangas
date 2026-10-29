import test from 'node:test';
import assert from 'node:assert/strict';
import { arrivalInput, conflictsWithBooking, maintenanceForm, maintenancePayload, NEXT_MAINTENANCE_STATUSES, phoneHref } from '../src/maintenanceModel.mjs';

test('editing retains persisted contact, parts, cost and photo information', () => {
  const row = { id: 'request-1', title: 'Pump', assignedStaffId: 'staff-1', status: 'In Progress', updatedAt: '2026-10-27T00:00:00Z', notes: 'Repair notes', attachments: [{ name: 'Before', phase: 'Before', url: 'data:image/jpeg;base64,abc' }], maintenance: { location: 'Pool', equipment: 'Pump', contactMethod: 'Phone call', contactNotes: 'Arriving today', waitingForParts: true, partsNotes: 'Capacitor', repairCost: '100.50' } };
  const payload = maintenancePayload(maintenanceForm(row), row);
  assert.equal(payload.expectedUpdatedAt, row.updatedAt);
  assert.equal(payload.contactNotes, 'Arriving today');
  assert.equal(payload.waitingForParts, true);
  assert.equal(payload.repairNotes, 'Repair notes');
  assert.deepEqual(payload.photos, row.attachments);
  assert.equal(payload.repairCost, '100.50');
});
test('new request payload omits status and version and can use a common area', () => {
  const form = maintenanceForm(null, 'staff-1');
  form.location = 'Pool';
  const payload = maintenancePayload(form, null);
  assert.equal(payload.assignedStaffId, 'staff-1');
  assert.equal(payload.location, 'Pool');
  assert.equal(payload.dueDate, null);
  assert.equal(Object.hasOwn(payload, 'status'), false);
  assert.equal(Object.hasOwn(payload, 'expectedUpdatedAt'), false);
});
test('review cannot be skipped and closed requests offer no editing transition', () => {
  assert.equal(NEXT_MAINTENANCE_STATUSES.Pending.includes('Completed'), false);
  assert.equal(NEXT_MAINTENANCE_STATUSES['In Progress'].includes('Completed'), false);
  assert.equal(NEXT_MAINTENANCE_STATUSES['Pending Review'].includes('Completed'), true);
  assert.deepEqual(NEXT_MAINTENANCE_STATUSES.Completed, ['Completed']);
});
test('phone contact uses only a usable phone number', () => {
  assert.equal(phoneHref('+63 (917) 123-4567'), 'tel:+639171234567');
  assert.equal(phoneHref('javascript:alert(1)'), '');
  assert.equal(phoneHref(''), '');
});
test('villa work defaults bind the villa, inspection type and booking impact', () => {
  const payload = maintenancePayload(maintenanceForm(null, '', { villaId: 'villa-2', kind: 'Inspection', blocksBooking: true }));
  assert.equal(payload.villaId, 'villa-2');
  assert.equal(payload.kind, 'Inspection');
  assert.equal(payload.blocksBooking, true);
  assert.equal(payload.assignedStaffId, null);
  assert.equal(Object.hasOwn(payload, 'responseAction'), false);
});
test('arrival input and response payload use Philippine time', () => {
  assert.equal(arrivalInput('2026-10-27T02:30:00Z'), '2026-10-27T10:30');
  const row = { id: 'request-1', updatedAt: 'revision-1', maintenance: { onCall: { expectedArrival: '2026-10-27T02:30:00Z' } } };
  const form = maintenanceForm(row); form.responseAction = 'Accepted';
  assert.equal(maintenancePayload(form, row).expectedArrival, '2026-10-27T10:30:00+08:00');
  assert.equal(maintenancePayload(form, row).responseAction, 'Accepted');
});
test('booking availability compares the arrival time with guest stay boundaries', () => {
  const period = { checkInDate: '2026-10-29', checkOutDate: '2026-10-30', checkInTime: '3:00 PM', checkOutTime: '11:00 AM' };
  assert.equal(conflictsWithBooking('2026-10-29T14:59', period), false);
  assert.equal(conflictsWithBooking('2026-10-29T15:00', period), true);
  assert.equal(conflictsWithBooking('2026-10-30T10:59', period), true);
  assert.equal(conflictsWithBooking('2026-10-30T11:00', period), false);
  assert.equal(conflictsWithBooking('2026-10-30T12:00', { ...period, checkOutTime: '' }), true);
});
