import test from 'node:test';
import assert from 'node:assert/strict';
import {feedbackCsv,feedbackDatasetColumns} from '../src/feedbackDataset.mjs';
test('export matches supplied dataset columns and respects anonymity',()=>{
  assert.deepEqual(feedbackDatasetColumns,['No.','Guest Name','Star Rating','Review Date','Guest Feedback (Verbatim)']);
  const csv=feedbackCsv([{hide_identity:true,guest_name:'Private Name',overall_rating:4,created_at:'2026-10-21T00:00:00Z',comments:'Clean rooms, helpful staff.',private_note:'private'}]);
  assert.ok(csv.includes('Anonymous guest'));assert.ok(!csv.includes('Private Name'));assert.ok(!csv.includes('private'));assert.ok(csv.includes('"4"'));
});
test('guest-authored spreadsheet formulas are exported as text',()=>{
  assert.ok(feedbackCsv([{guest_name:'=DANGEROUS()',comments:'+formula',overall_rating:1}]).includes("\"'=DANGEROUS()\""));
});
