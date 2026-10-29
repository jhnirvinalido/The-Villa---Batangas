"""Date bypass applies only to checkout; payment and arrival guards remain."""
import ast
import unittest
from datetime import date
from pathlib import Path

class RestrictionError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)

class CheckoutDateTesting(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'admin.py').read_text())
        names={'enforce_booking_lifecycle_date','booking_lifecycle_date'}
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[])
        self.env={'date':date,'HTTPException':RestrictionError,'villa_business_today':lambda:date(2026,10,20)}
        exec(compile(ast.fix_missing_locations(module),'admin.py','exec'),self.env)
    def test_checkout_accepts_past_future_and_missing_dates(self):
        for booking in [{'check_out_date':'2026-10-19'},{'check_out_date':'2026-10-21'},{}]:
            with self.subTest(booking=booking):self.env['enforce_booking_lifecycle_date'](booking,'check_out')
    def test_checkin_still_enforces_scheduled_arrival(self):
        self.env['enforce_booking_lifecycle_date']({'check_in_date':'2026-10-20'},'check_in')
        with self.assertRaises(RestrictionError):self.env['enforce_booking_lifecycle_date']({'check_in_date':'2026-10-21'},'check_in')
    def test_checkout_keeps_payment_and_checked_in_guards(self):
        source=(Path(__file__).parents[1]/'admin.py').read_text()
        route=next(node for node in ast.parse(source).body if isinstance(node,ast.FunctionDef) and node.name=='checkout_booking')
        route.decorator_list=[]
        env={'Depends':lambda _:None,'require_admin':None,'HTTPException':RestrictionError,'booking_stay_state':lambda record:record['stay_status'],'fetch_booking':lambda _:self.record,'money':lambda value:float(value or 0),'enforce_booking_lifecycle_date':lambda *_:None,'pending_front_desk_intents':lambda _:[]}
        mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),route],type_ignores=[])
        exec(compile(ast.fix_missing_locations(mod),'admin.py','exec'),env)
        for record in [{'stay_status':'Not Checked In','booking_status':'Confirmed','balance_amount':0},{'stay_status':'Checked In','booking_status':'Checked In','balance_amount':500}]:
            self.record=record
            with self.subTest(record=record),self.assertRaises(RestrictionError) as raised:env['checkout_booking']('booking',None,{'account':{'id':'admin'}})
            self.assertEqual(raised.exception.status_code,409)
