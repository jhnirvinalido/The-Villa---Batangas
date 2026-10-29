import unittest
from public_feedback import public_reviews


class PublicFeedbackTests(unittest.TestCase):
    def test_all_star_levels_and_sources_are_included_with_private_fields_excluded(self):
        rows=[{'id':'a','overall_rating':1,'source':'historical_dataset','review_date_label':'August 2026','guest_name':'Maria Cruz','guest_email':'maria@example.com','comments':'Maria Cruz reported dirty water. maria@example.com','private_note':'private','booking_id':'secret-booking'},
              {'id':'b','overall_rating':5,'comments':'A lovely and comfortable stay.','created_at':'2026-10-22T00:00:00','hide_identity':False}]
        result=public_reviews(rows)
        self.assertEqual(result['count'],2)
        self.assertEqual(result['average'],3)
        self.assertEqual(result['distribution']['1'],1)
        self.assertTrue(all('source' not in row for row in result['reviews']))
        text=str(result)
        for secret in ['Maria','Cruz','maria@example.com','secret-booking','private_note']:self.assertNotIn(secret,text)
        self.assertTrue(all(row['author']=='Anonymous' for row in result['reviews']))

    def test_duplicate_and_invalid_ratings_do_not_inflate_summary(self):
        row={'id':'a','overall_rating':4,'comments':'Nice stay.'}
        result=public_reviews([row,row,{'id':'b','overall_rating':0},{'id':'c','overall_rating':True}])
        self.assertEqual(result['count'],1)
        self.assertEqual(result['average'],4)

    def test_empty_data_does_not_invent_reviews(self):
        self.assertEqual(public_reviews([])['reviews'],[])
        self.assertIsNone(public_reviews([])['average'])

    def test_name_visibility_follows_guest_choice_while_contacts_remain_hidden(self):
        row={'id':'name','overall_rating':5,'guest_name':'Alex Reyes','hide_identity':False,
             'guest_email':'alex@example.com','guest_phone':'09123456789','booking_code':'TV-SECRET',
             'comments':'Great stay. alex@example.com 09123456789 TV-SECRET'}
        visible=public_reviews([row])['reviews'][0]
        self.assertEqual(visible['author'],'Alex Reyes')
        for contact in ('alex@example.com','09123456789','TV-SECRET'):self.assertNotIn(contact,str(visible))
        hidden=public_reviews([{**row,'hide_identity':True}])['reviews'][0]
        self.assertEqual(hidden['author'],'Anonymous')
        self.assertNotIn('Alex Reyes',str(hidden))

    def test_historical_csv_is_anonymous_even_if_legacy_flag_was_false(self):
        from feedback_policy import admin_feedback_projection
        row={'id':'csv','source':'historical_dataset','guest_name':'Original CSV Name','hide_identity':False,
             'overall_rating':4,'comments':'A pleasant stay.'}
        self.assertEqual(public_reviews([row])['reviews'][0]['author'],'Anonymous')
        projected=admin_feedback_projection(row)
        self.assertTrue(projected['hide_identity'])
        self.assertEqual(projected['guest_name'],'Anonymous guest')

    def test_system_names_match_between_admin_and_public_when_not_hidden(self):
        from feedback_policy import admin_feedback_projection
        row={'id':'system','source':'verified_stay','guest_name':'Alex Reyes','hide_identity':False,
             'overall_rating':5,'comments':'We enjoyed a comfortable stay.'}
        self.assertEqual(public_reviews([row])['reviews'][0]['author'],'Alex Reyes')
        self.assertEqual(admin_feedback_projection(row)['guest_name'],'Alex Reyes')
        self.assertEqual(public_reviews([{**row,'hide_identity':True}])['reviews'][0]['author'],'Anonymous')
        self.assertTrue(admin_feedback_projection({**row,'hide_identity':True})['hide_identity'])
