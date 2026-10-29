# Dataset and annotation protocol

A and B share `sentiment_phrases.csv`: verbatim spans from the client's historical
Airbnb reviews, explicit sentiment, semicolon-separated categories, and original
review/guest grouping. No star-derived labels are used. An empty category means
no supported facility/service category, not a missing sentiment. All supplied
annotations and vocabulary are provisional AI work requiring human review.

Have two annotators read comments without ratings or model predictions. Label
clauses separately: positive praise, negative complaint, neutral factual or
non-evaluative statement. Preserve mixed sentiment by splitting clauses rather
than forcing mixed feedback into neutral. Mark uncertainty for adjudication.
Use the original whole review to resolve context; do not infer a facility from
an isolated clause when the subject is unclear. Correct/extend the initial
category vocabulary with the client; preserve overlapping categories only when
supported. Record annotator IDs, agreement, adjudication, and consent/licensing
provenance outside public dashboard exports. Keep all reviews by the same guest
under one Guest Group; keep Review ID for traceability. Never create fictitious
booking records or pad the neutral class.

C (`noisy_text_tests.csv`) contains ten documented synthetic implementation
fixtures from the requested examples. It is never loaded by training. Its
normalization/category checks are smoke tests, not independent research results.
Collect approximately 100–200 genuine/noise-documented held-out examples before
reporting robustness. Never tune corrections against the final holdout.

The 73 phrase annotations are still only 26 source reviews. Aim for the proposed
600–1,000 permitted, human-labeled phrases with adequate class representation;
the targets are planning guidance. A platform origin alone does not document
permission to train: retain the actual collection and permitted-use evidence.
The software does not verify platform permission.

Evaluate sentiment with accuracy, per-class precision/recall/F1, macro F1, and
confusion matrix. Current grouped CV avoids splitting one review across folds.
Word TF-IDF is the preselected deployed representation; character 3–5-gram
TF-IDF is evaluated on exactly the same folds, not used to cherry-pick results.
Use a separate grouped validation and untouched test partition once enough
independent reviews exist (70/15/15 is an option, not an assertion of current data).

Evaluate complaint matching against independent category annotations. For full
review frequency validation, annotate ALL negative categories in each full
review, then compare review-level counts (one review/category), precision,
recall, and count absolute errors. The current selected spans are not exhaustive
full-review ground truth. `pipeline_evaluation.json` is development-only.

Have the client score Gemini drafts separately for relevance, actionability,
evidence support, and unsupported claims on a fixed rubric (e.g. 1–5 plus
comments). Record draft ID/model, evidence snapshot, reviewer, and score. Approval
in the app records management acceptance, not scientific validation or proof
that any equipment defect exists. No tasks, repairs, or messages execute on approval.

Document selection bias: system feedback currently requires a completed,
fully-paid booking and may omit unresolved payment disputes. The name-hiding
checkbox is pseudonymous/identity-hidden because restricted booking association
is retained; it is not unlinkable anonymity.
