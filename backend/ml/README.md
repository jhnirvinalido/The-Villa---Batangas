# The Villa feedback analysis

The deployed flow is completed + fully paid stay → secure email link → star
rating + written feedback → conservative NLP → clause-level Naive Bayes with
high-confidence polarity cues →
vocabulary-based complaint categorization → distinct-review frequencies →
Gemini recommendation draft → administrator approval. Star ratings remain a
separate business statistic; they are never sentiment labels or inference input.
Existing booking eligibility, signed links, duplicate prevention, identity hiding,
and private-note exclusions remain enforced.

See [`docs/AI_FEEDBACK_ANALYSIS_PIPELINE.md`](../../docs/AI_FEEDBACK_ANALYSIS_PIPELINE.md)
for the complete stage-by-stage workflow, data boundaries, persistence behavior,
and administrator review process.

## Datasets and model development

- A/B: `datasets/sentiment_phrases.csv`: 73 verbatim spans from 26 original Airbnb
  reviews with sentiment and category annotations. All labels are provisional AI
  annotations requiring independent human review. They are not new guest reviews.
- B vocabulary: `categories.json` defines regex phrase matching. Naive Bayes only
  predicts sentiment; it is not claimed to recognize categories.
- The archived expanded candidate `datasets/sentiment_phrases_candidate_20261028.csv`
  has 233 rows across 67 review groups, all marked
  `provisional_ai_requires_human_review`. Its 19 neutral labels are not
  human-approved ground truth. It is not the final capstone dataset.
- Final `data/THE_VILLA_HUMAN_APPROVED_MODEL_INPUT_232.csv` has 232
  human-approved excerpts across 66 groups and is the source of the evaluation
  below. It is excluded from version control.
- C: `datasets/noisy_text_tests.csv`: ten documented synthetic smoke fixtures,
  held out from training. Not a substitute for independent Taglish/noisy reviews.
- Original full-review CSV stays available for historical Supabase import. Its
  whole-review annotations are not the phrase model's training source.

See `datasets/ANNOTATION_GUIDE.md` for annotation, source rights/provenance,
600–1,000 phrase collection targets, 100–200 robustness example targets,
independent evaluation, reviewer rubric, and payment-related selection bias.

Train/evaluate from repository root:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m ml.train
PYTHONPATH=backend backend/.venv/bin/python -m ml.evaluate_pipeline
```

Optional train `--data PATH --output PATH`; CSV needs explicit `Sentiment Label`
and `Guest Feedback (Verbatim)`, plus `Guest Group`/`Review ID` for grouped data.
Keep all phrases/reviews from one guest in the same group. Missing sentiment
labels are rejected, with no star fallback. Duplicate comments are deduplicated
and conflicting labels rejected before splitting. Names/contact details are
excluded from features.

The deployment baseline remains word unigram/bigram TF-IDF + Multinomial Naive
Bayes. `ml.train` now compares that fixed baseline with configurations selected
inside grouped inner folds: word 1–1/1–2/1–3 grams and character 3–5/2–5 grams,
alpha 0.25/1/2, neutral prior multipliers 1/1.5/2.5, and neutral training-only
oversampling 1/2/3. Macro F1 selects configurations, with neutral recall and then
accuracy as tie-breakers. The outer grouped folds estimate performance; outer
test labels do not select parameters. Vocabulary and IDF are fit only on each
training fold. Review groups and duplicate normalized text are kept together.

The evaluation report includes accuracy, macro F1, per-class precision/recall/F1,
and confusion matrices for both the fixed baseline and nested tuned system. The
full-dataset inner-CV score is for final configuration selection only, not a
performance estimate. The final human-approved data has been evaluated using
nested grouped validation; there is no separate untouched test set. Report
77.59% as a nested-CV estimate against these labels, not as production accuracy.
Neutral examples that are mostly factual listings provide little sentiment
vocabulary; the classifier may still misclassify them. Tagalog/Taglish errors and
small-sample instability remain. Unknown feature text abstains. Posterior scores
are not calibrated confidence.

The supplied human-approved 232-excerpt CSV is evaluated locally at
`data/THE_VILLA_HUMAN_APPROVED_MODEL_INPUT_232.csv`; the dataset is excluded from
version control. Reproduce the candidate report without replacing the deployed
artifact:

```sh
PYTHONPATH=backend python3 -m ml.train \
  --data data/THE_VILLA_HUMAN_APPROVED_MODEL_INPUT_232.csv \
  --output backend/ml/candidates/20261031_human_approved_232
```

For this file (SHA-256
`fc77f3514af33846940d688b9f4cee44ca1208315d66ebd72e31e4c012d7bf89`), 3-fold
nested grouped CV compared the fixed word TF-IDF baseline (accuracy 0.7198,
macro F1 0.4993) with inner-fold-selected configurations (accuracy 0.7759,
macro F1 0.7196). Tuned per-class F1 was 0.8053 negative, 0.5806 neutral, and
0.7729 positive. Neutral recall improved from 0/19 to 9/19; the report includes
all neutral out-of-fold predictions. The full-data inner-CV selection chose
character 2–5 grams, alpha 0.25, neutral prior multiplier 1.0, and neutral
training-fold oversampling 3. Outer-fold selections varied, so treat this as a
candidate configuration, not a guaranteed fixed-model score. These results
estimate performance against the human-approved labels on this small dataset;
do not use the inner-CV selection score as an independent estimate.

The full-data candidate is saved separately at
`ml/candidates/20261031_human_approved_232/sentiment_model.json`, version
`pilot-phrase-tfidf-nb-fc77f3514af3`; it is not the deployed model. To smoke-test
the application inference path without changing deployment:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_sentiment_pilot
```

The integration smoke test includes authentic approved excerpts covering all
three classes, mixed Tagalog/English, and ambiguous wording; these are not a
separate accuracy evaluation. Empty or wholly out-of-vocabulary text has no
predicted sentiment (abstention), rather than receiving the majority-prior label.
See [`docs/CHAPTER_4_AI_EVALUATION.md`](../../docs/CHAPTER_4_AI_EVALUATION.md)
for the formatted dataset, nested-CV, per-class, confusion-matrix, Neutral-class,
integration-test, and limitation results for the thesis chapter.

`pipeline_evaluation.json` separately checks normalization, vocabulary matching,
and distinct-review category counts with reference sentiment. It is explicitly
development-only; collect exhaustive human-reviewed full-review complaint labels
before reporting end-to-end frequency accuracy. Evaluate Gemini separately with
client reviewers for relevance, actionability, evidence support and unsupported
claims. The application approval flag is not a scientific evaluation score.

## NLP and complaints

`preprocessing.py` applies an explicit small correction dictionary (drrty→dirty,
poool→pool, mahinaa→mahina, slooow→slow, gud→good), case/Unicode normalization,
and conservative clause splitting. It preserves negation and meaningful Tagalog;
there is no blind spellchecker or promised translation. Original comments stay
unchanged. Inspect per-phrase original/normalized text in the admin dashboard.
The clause analyzer uses a versioned, high-confidence polarity lexicon to correct
clear cues such as “clean” and “dirty” when the pilot model disagrees; ambiguous
or mixed-polarity clauses remain with the model. This is a targeted correction,
not a claim that the pilot classifier is generally accurate.

Each category is counted once per distinct review if at least one matched clause
is predicted negative. Positive staff comments do not automatically count as
staff complaints. One review can count in several categories. Clause splitting
and category attribution are heuristic: missing subjects and mixed clauses can
still cause errors. No match/unknown sentiment is not proof of no complaint.

## Database and Gemini setup

Apply migrations in order (earlier booking/feedback migrations first):

1. `20261021_feedback_dataset_alignment.sql`
2. `20261021_import_historical_guest_feedback.sql`
3. `20261021_feedback_text_sentiment.sql`
4. `20261021_feedback_analysis_pipeline.sql`
5. `20261102_feedback_recommendation_jobs.sql` (after the existing `feedback_recommendation_reports` table exists)

These have not been applied to your live database by this change. The final
migration adds stored phrase analysis and private recommendation reports. Original
`guest_feedback` remains the single feedback table; historical rows retain their
source and review month with no fake bookings. To reconcile the original CSV:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m ml.import_historical
```

Add to backend environment (never frontend):

```dotenv
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=your_supported_generateContent_model
```

Choose a model with structured JSON output support in your Google project.
Restart the backend. In Admin → Guest Feedback, run Analyze saved reviews to
persist clause analysis on both historical and verified rows. Analysis reports
also compute from current comments/model on demand. Filter source, villa, stars,
and month range; the recommendation snapshot respects exactly those filters.
Historical dates are month/year, so date filtering is explicitly by month.

Generate draft sends Gemini only aggregated ratings, source counts, complaint
counts and bounded redacted evidence—not names, contacts, booking IDs or private
notes. The endpoint uses Google's generateContent structured-output REST
contract: https://ai.google.dev/gemini-api/docs/generate-content/structured-output
Responses are schema-validated; unsupported/duplicate categories are rejected,
and displayed counts/evidence are server-owned. Missing keys, errors, blocks,
and malformed responses produce explicit errors, never fake recommendations.

Drafts are persisted with evidence/model fingerprints. Administrator approval
records actor/time. Changed evidence/model requires a new draft. Approval never
creates tasks or performs maintenance. Reports are accessible only via admin
APIs; database RLS and service-role permissions protect storage. Unconfigured
Gemini shows its setup state and does not block feedback collection or analysis.

## Validation

Run backend unittest discovery and frontend lint/build. Automated database and
Gemini tests use mocks; no live Gemini call was made (keys are not configured).
Actual training and grouped evaluation use the local phrase CSV. Category
smoke evaluation does not substitute for a client-reviewed benchmark.

## Automatic sentiment analysis and queued recommendations

The backend sentiment worker checks feedback every 60 seconds and persists
analysis when feedback text, model version, or preprocessing version changes.
The separate recommendation worker claims queued jobs using a database
`FOR UPDATE SKIP LOCKED` lease, so multiple API processes cannot claim the same
job simultaneously. Jobs are unique per evidence/model fingerprint; report
persistence takes a transaction advisory lock and reuses an existing report.
Apply `migrations/20261102_feedback_recommendation_jobs.sql` after the existing
feedback analysis schema. The migration adds a unique active-report index and
stops without changing data if duplicate active fingerprints already exist;
review those rows before retrying it. The recommendation worker can be disabled with
`FEEDBACK_RECOMMENDATION_WORKER_ENABLED=false`; do so only when an external
worker runs `feedback_recommendations.process_recommendation_job`.

In Admin → Guest Feedback, an administrator clicks **Generate recommendations**
to queue a Gemini draft from current negative categorized evidence. The button
appears only when Gemini is configured, recommendation storage is available,
and complaint evidence exists. The panel reports queued, processing, retry,
failed, and completed states. Transient errors receive at most three attempts
with 30- and 60-second backoff. Invalid provider output is marked failed
without retry. Admin approval records the actor and time and never creates
tasks or performs maintenance.

The worker is at-least-once with respect to the external Gemini request: if a
process loses its lease after Gemini responds but before saving the report, a
retry can make another provider request and may incur another charge. Database
claims and idempotent report persistence prevent duplicate active reports, but
cannot promise exactly-once provider billing. Expired claims recover
automatically; jobs that exhaust attempts stay failed and can be requeued by
an administrator. Unchanged evidence reuses its existing job/report; changed
feedback or model version creates a distinct fingerprint.

## Exact historical dates

The original Airbnb CSV supplies month/year only. `Exact Review Date` is a new
optional column for a source-verified ISO date (`YYYY-MM-DD`). Its cells remain
empty until actual dates are supplied. Do not fabricate the day, use the import
timestamp, or overwrite the original `Review Date` (used by legacy import keys).
Apply `migrations/20261022_exact_feedback_review_dates.sql`, fill known exact
dates, then rerun `python -m ml.import_historical` with PYTHONPATH=backend.
The importer updates the existing reviews and preserves their database names
and hide_identity choices; blank exact-date cells do not clear saved dates.
Public reviews prefer saved exact dates, otherwise retain the historical month.
New system submissions use their Philippine submission date. Public authors
follow the saved hide_identity choice, with contacts/private notes excluded.

## Display names by source

All historical CSV reviews are displayed/imported as anonymous, even if a legacy
row had hide_identity=false. System feedback shows the saved booking/guest name
when hide_identity=false; guests who select anonymity remain anonymous on both
the admin dashboard and public website. Apply
`20261022_feedback_identity_visibility.sql` to reconcile legacy database rows:
it anonymizes historical records and restores a missing system-review name from
its actual booking only when that guest has not chosen anonymity. It never
turns off a guest's anonymity choice. Historical reimport preserves exact dates
but always keeps CSV identity hidden (superseding the earlier preservation note).
