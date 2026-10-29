# The Villa feedback analysis

The deployed flow is completed + fully paid stay → secure email link → star
rating + written feedback → conservative NLP → clause-level Naive Bayes →
vocabulary-based complaint categorization → distinct-review frequencies →
Gemini recommendation draft → administrator approval. Star ratings remain a
separate business statistic; they are never sentiment labels or inference input.
Existing booking eligibility, signed links, duplicate prevention, identity hiding,
and private-note exclusions remain enforced.

## Datasets and model development

- A/B: `datasets/sentiment_phrases.csv`: 73 verbatim spans from 26 original Airbnb
  reviews with sentiment and category annotations. All labels are provisional AI
  annotations requiring independent human review. They are not new guest reviews.
- B vocabulary: `categories.json` defines regex phrase matching. Naive Bayes only
  predicts sentiment; it is not claimed to recognize categories.
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

Word unigram/bigram TF-IDF + Multinomial Naive Bayes is preselected for deployment.
Character 3–5-gram TF-IDF is compared on the same grouped folds in evaluation.json.
Each fold fits its own vocabulary/IDF; phrases from one source review stay in one
partition. No final model is evaluated against its own training predictions.
Current primary 3-fold grouped CV: 54.8% accuracy, 0.372 macro F1; fold-wise
majority baseline 35.6%. Per-class precision/recall/F1 and confusion matrices are
saved. Only four factual-neutral phrases exist, so these results are unstable.
Do not describe provisional annotations or development category scores as
independent human validation. The model can misclassify Tagalog and unseen
expressions (including friendly Tagalog phrases); the illustrative document's
outputs are not guaranteed. Unknown feature text abstains. Posterior scores
are not calibrated confidence.

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

## Automatic operation and simplified dashboard (22 October 2026)

Apply `migrations/20261022_automatic_feedback_analysis.sql` after the earlier
pipeline migration, then restart the backend. A separate worker runs at startup
and every 60 seconds, even with the admin page closed. It checks review content,
model version and NLP version before persisting Naive Bayes predictions, then
creates a Gemini recommendation draft only if the current evidence has no saved
report and negative categorized evidence exists. Immediate new-submission
analysis is retained. No negative evidence means no invented recommendations.

Supabase claims serialize generation for the same evidence fingerprint across
API processes. Draft insertion and job completion happen atomically. A five-minute
lease recovers interrupted work; provider failures retry after five minutes,
with at most four claims per evidence fingerprint. An interrupted provider call
may have been charged before recovery; exactly-once external billing is not
promised. Unchanged snapshots reuse existing manual or approved reports. New
feedback/model changes produce a new draft requiring administrator review.
System-generated drafts have generation_source=automatic and no fabricated staff
creator; approval still records the actual administrator and timestamp.

`FEEDBACK_ANALYSIS_WORKER_ENABLED` defaults to true and can disable the worker
for test environments. Missing migrations/configuration produce status messages;
feedback collection remains available. The UI polls for updates and has no
manual analysis/generation controls or source/date/rating filters. It retains
one Average filtered rating card (now covering all displayed reviews), reviews,
and recommendations, with evidence collapsed under each action. Source metadata
remains in Supabase even though repeated source labels are omitted on cards.

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
