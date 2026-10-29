export const feedbackDatasetColumns=['No.','Guest Name','Star Rating','Review Date','Guest Feedback (Verbatim)'];
const cell=value=>{
  let text=String(value ?? '');
  // Keep spreadsheet applications from evaluating guest-authored formulas.
  if (/^[\s]*[=+@-]/.test(text)) text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
};
export function feedbackCsv(rows) {
  return '\uFEFF'+[feedbackDatasetColumns,...rows.map((row,index)=>[index+1,row.hide_identity?'Anonymous guest':row.guest_name || 'Guest',row.overall_rating,row.review_date || row.review_date_label || String(row.created_at || '').slice(0,10),row.comments])].map(row=>row.map(cell).join(',')).join('\r\n');
}
