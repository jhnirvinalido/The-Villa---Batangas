import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from datetime import datetime
from zoneinfo import ZoneInfo
from task_workflow import staff_checklist_update, task_start_is_available

MANILA = ZoneInfo("Asia/Manila")

class StaffChecklistTests(unittest.TestCase):
    def setUp(self):
        self.stored=[{'id':'one','label':'Inspect villa','done':False},{'id':'two','label':'Prepare linens','done':False}]
    def test_staff_updates_completion_but_cannot_rewrite_instructions(self):
        checklist,progress=staff_checklist_update(self.stored,[{'id':'two','done':False},{'id':'one','label':'changed','done':True}],'task')
        self.assertEqual(progress,50)
        self.assertEqual(checklist[0],{'id':'one','label':'Inspect villa','done':True})
        self.assertFalse(self.stored[0]['done'])
    def test_removed_added_and_duplicate_steps_are_rejected(self):
        for incoming in [[{'id':'one'}],[{'id':'one'},{'id':'two'},{'id':'new'}],[{'id':'one'},{'id':'one'}]]:
            with self.subTest(incoming=incoming),self.assertRaises(ValueError):
                staff_checklist_update(self.stored,incoming,'task')
    def test_unchecking_restores_correct_progress(self):
        checklist,progress=staff_checklist_update(self.stored,[{'id':'one','done':False},{'id':'two','done':False}],'task')
        self.assertEqual(progress,0)
        self.assertFalse(any(i['done'] for i in checklist))
    def test_legacy_steps_without_ids_use_frontend_fallback(self):
        checklist,progress=staff_checklist_update([{'text':'Inspect'}],[{'id':'task-check-0','done':True}],'task')
        self.assertEqual(progress,100)
        self.assertEqual(checklist[0]['label'],'Inspect')

class TaskStartScheduleTests(unittest.TestCase):
    def test_task_is_available_on_assigned_day_before_deadline(self):
        now=datetime(2026,10,22,9,59,tzinfo=MANILA)
        self.assertTrue(task_start_is_available('2026-10-22','10:00:00',now))

    def test_task_is_available_at_deadline(self):
        scheduled=datetime(2026,10,22,10,0,tzinfo=MANILA)
        self.assertTrue(task_start_is_available('2026-10-22','10:00',scheduled))
        self.assertTrue(task_start_is_available('2026-10-22','10:00:00',scheduled))

    def test_missing_or_invalid_schedule_is_unavailable(self):
        now=datetime(2026,10,22,10,0,tzinfo=MANILA)
        for due_date,due_time in [('', '10:00'),('2026-10-22',''),('bad-date','10:00'),('2026-10-22','bad-time')]:
            with self.subTest(due_date=due_date,due_time=due_time):
                self.assertFalse(task_start_is_available(due_date,due_time,now))

    def test_cannot_start_on_other_dates_or_after_deadline(self):
        for now in [datetime(2026,10,21,9,0,tzinfo=MANILA), datetime(2026,10,22,10,1,tzinfo=MANILA), datetime(2026,10,23,9,0,tzinfo=MANILA)]:
            self.assertFalse(task_start_is_available('2026-10-22','10:00',now))
