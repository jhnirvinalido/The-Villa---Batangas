from datetime import date
import unittest

from booking import _villa_operational
from person_names import validate_person_name
from villa_catalog import DEFAULT_VILLA_CATALOG, get_villa_catalog_map
from test_maintenance import TaskStore


class ScheduledAvailabilityTests(unittest.TestCase):
    def test_catalog_carries_schedule_into_booking_validation(self):
        store = TaskStore()
        store.catalog = [{**DEFAULT_VILLA_CATALOG[0], 'status':'Available'}]
        store.records = [{'id':'work', 'source':'manual-maintenance-request', 'status':'In Progress',
                          'due_date':'2099-11-02', 'status_history':[{'maintenance':{
                              'villaId':store.catalog[0]['id'], 'blocksBooking':True, 'kind':'Repair'}}]}]
        villa = get_villa_catalog_map(store)[store.catalog[0]['id']]
        self.assertEqual(villa['maintenance_dates'], ['2099-11-02'])
        self.assertFalse(_villa_operational(villa,date(2099,11,2)))
        self.assertTrue(_villa_operational(villa,date(2099,11,3)))

    def test_only_scheduled_maintenance_day_is_blocked(self):
        villa={'operational_status':'under_maintenance','manual_operational_status':'available',
               'maintenance_dates':['2026-11-02','2026-11-04']}
        self.assertTrue(_villa_operational(villa,date(2026,11,1)))
        self.assertFalse(_villa_operational(villa,date(2026,11,2)))
        self.assertTrue(_villa_operational(villa,date(2026,11,3)))
        self.assertFalse(_villa_operational(villa,date(2026,11,4)))

    def test_explicit_manual_or_undated_block_is_not_ignored(self):
        for extra in ({'manual_operational_status':'under_maintenance'},{'undated_maintenance':True}):
            villa={'operational_status':'under_maintenance','maintenance_dates':['2026-11-02'],**extra}
            self.assertFalse(_villa_operational(villa,date(2026,11,3)))

    def test_human_names_preserve_accents_and_punctuation_but_reject_numbers(self):
        for name in ("María-José", "O'Connor", 'De la Cruz'):
            self.assertEqual(validate_person_name(name),name)
        for name in ('Guest123','Guest１２','Guest²'):
            with self.assertRaises(ValueError):
                validate_person_name(name)
