import test from 'node:test';
import assert from 'node:assert/strict';
import { canStartTask, dateKey, isLate, orderTasks, readyForReview } from '../src/taskFlow.mjs';
const now = Date.parse('2026-10-20T12:00:00+08:00');
test('on-call work starts only after acceptance and stays actionable after its arrival time', () => {
  const task = { status: 'Pending', dueDate: '2026-10-19', dueTime: '10:00', maintenanceOnCall: { state: 'Awaiting response' } };
  assert.equal(canStartTask(task, now), false);
  assert.equal(isLate(task, now), false);
  task.maintenanceOnCall.state = 'Accepted';
  assert.equal(canStartTask(task, now), false);
  task.maintenanceOnCall.scheduleApproved = true;
  assert.equal(canStartTask(task, now), true);
  assert.equal(isLate(task, now), false);
});
test('deadline uses Philippine business time and excludes review and approved work',()=>{
  assert.equal(isLate({status:'Pending',dueDate:'2026-10-20',dueTime:'11:00'},now),true);
  assert.equal(isLate({status:'In Progress',dueDate:'2026-10-20',dueTime:'13:00'},now),false);
  for(const status of ['Pending Review','Completed']) assert.equal(isLate({status,dueDate:'2026-10-19'},now),false);
  assert.equal(isLate({status:'Pending',dueDate:'2026-10-20'},now),false);
});
test('calendar today follows Manila even across UTC date boundaries',()=>{
  assert.equal(dateKey(new Date('2026-10-19T18:00:00Z')),'2026-10-20');
});
test('work queue prioritizes overdue then in-progress then pending without mutating input',()=>{
  const tasks=[{id:1,status:'Pending',dueDate:'2026-10-21'},{id:2,status:'In Progress',dueDate:'2026-10-21'},{id:3,status:'Pending',dueDate:'2026-10-19'}];
  assert.deepEqual(orderTasks(tasks,now).map(t=>t.id),[3,2,1]);
  assert.deepEqual(tasks.map(t=>t.id),[1,2,3]);
});
test('review is allowed only after work starts and every assigned step is complete',()=>{
  assert.equal(readyForReview({status:'Pending',checklist:[{done:true}]}),false);
  assert.equal(readyForReview({status:'In Progress',checklist:[]}),false);
  assert.equal(readyForReview({status:'In Progress',checklist:[{done:true},{done:false}]}),false);
  assert.equal(readyForReview({status:'In Progress',checklist:[{done:true}]}),true);
});

test('returned feedback is visible only while corrections are in progress',async()=>{
  const {returnedFeedback}=await import('../src/taskFlow.mjs');
  const task={status:'In Progress',statusHistory:[{note:'Returned for correction: Please recheck the bathroom.'}]};
  assert.equal(returnedFeedback(task),'Please recheck the bathroom.');
  assert.equal(returnedFeedback({...task,status:'Pending Review'}),'');
});

test('staff queue keeps review and history separate from actionable work',async()=>{
  const {filterTaskQueue}=await import('../src/taskFlow.mjs');
  const tasks=['Pending','In Progress','Pending Review','Completed','Cancelled'].map((status,id)=>({id,status}));
  assert.deepEqual(filterTaskQueue(tasks,{},now).map(t=>t.status),['In Progress','Pending']);
  assert.deepEqual(filterTaskQueue(tasks,{view:'In review'},now).map(t=>t.status),['Pending Review']);
  assert.deepEqual(filterTaskQueue(tasks,{view:'History'},now).map(t=>t.status),['Completed','Cancelled']);
});
test('calendar task list includes every assignment for the selected date except cancelled',async()=>{
  const {filterTaskQueue}=await import('../src/taskFlow.mjs');
  const tasks=['Pending','In Progress','Pending Review','Completed','Cancelled'].map((status,id)=>({id,status,dueDate:'2026-10-30'}));
  assert.deepEqual(
    filterTaskQueue(tasks,{view:'Schedule'}).filter(task=>task.dueDate==='2026-10-30').map(task=>task.status),
    ['In Progress','Pending','Pending Review','Completed']
  );
});
test('maintenance awaiting availability stays in requests, not my tasks', async()=>{
  const {filterTaskQueue}=await import('../src/taskFlow.mjs');
  const tasks=[
    {id:'request',status:'Pending',maintenanceOnCall:{state:'Awaiting response'}},
    {id:'scheduled',status:'Pending',maintenanceOnCall:{state:'Accepted',scheduleApproved:false}},
  ];
  assert.deepEqual(filterTaskQueue(tasks,{},now).map(task=>task.id),['scheduled']);
});
test('queue focus combines deadline, priority, and text search without losing assignments',async()=>{
  const {filterTaskQueue}=await import('../src/taskFlow.mjs');
  const tasks=[{id:1,status:'Pending',title:'Inspect Villa 2',priority:'High',dueDate:'2026-10-20',dueTime:'10:00'},{id:2,status:'In Progress',title:'Inspect Villa 3',priority:'Low',dueDate:'2026-10-20',dueTime:'15:00'},{id:3,status:'Pending',title:'Inspect garden',priority:'High'}];
  assert.deepEqual(filterTaskQueue(tasks,{view:'History'},now).map(t=>t.id),[1]);
  assert.deepEqual(filterTaskQueue(tasks,{focus:'Due today',search:'villa 3',priority:'Low'},now).map(t=>t.id),[2]);
  assert.deepEqual(filterTaskQueue(tasks,{focus:'Unscheduled'},now).map(t=>t.id),[3]);
});

test('starts are allowed only on the assigned Manila date before the deadline',async()=>{
  const {canStartTask}=await import('../src/taskFlow.mjs');
  const task={dueDate:'2026-10-22',dueTime:'10:00'};
  assert.equal(canStartTask(task,Date.parse('2026-10-22T09:00:00+08:00')),true);
  assert.equal(canStartTask(task,Date.parse('2026-10-21T09:00:00+08:00')),false);
  assert.equal(canStartTask(task,Date.parse('2026-10-22T10:01:00+08:00')),false);
  assert.equal(canStartTask(task,Date.parse('2026-10-23T09:00:00+08:00')),false);
});
