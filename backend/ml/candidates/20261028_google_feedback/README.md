# Experimental feedback model — 28 October 2026

This candidate has been trained but is **not the active application model**.
The user authorized experimental training with AI-proposed labels. None of the new labels have been independently reviewed by humans.

## Data

Source: user-supplied `THE VILLA FEEDBACKS.docx`.
SHA-256: `643eaa56c627cfd732752eb2ee736ce2ea140afc66df5a3287b127c1f3420020`.

- 44 review sections; 41 contain written feedback. Three rating/metadata-only sections were excluded.
- 160 selected, exact verbatim spans from those 41 reviews, with provisional AI sentiment labels.
- Combined with 73 existing phrases from 26 Airbnb reviews: **233 phrases, 67 source-review groups**.
- Distribution: 113 negative, 101 positive, 19 neutral.
- Reviewer names, account review counts, photo counts, copied star glyphs, and subratings are excluded from training features. Relative review dates are preserved as labels in the extraction CSV, not converted into invented dates.
- Two malformed pasted review headings were reconciled during extraction. Original source text remains unchanged. Some review comments end in ellipses and may be incomplete.
- Categories in the new phrase CSV are unreviewed keyword suggestions, not independent category ground truth. This work evaluates sentiment; it does not validate complaint categories or recommendation quality.

## Evaluation

Word unigram/bigram TF-IDF and Multinomial Naive Bayes, same preselected settings as the active model. Vocabulary and IDF are fitted only on each training fold. All selected phrases from a review stay together. Exact duplicate spans are checked by the existing training loader. There are no exact normalized reviewer-name overlaps between the two source collections; cross-posted/near-duplicate reviews and undisclosed identities still require human review.

`comparison.json` evaluates the original-data baseline and expanded-data candidate on **identical grouped test folds**. The original-data baseline excludes held-out original review groups; candidate training excludes every held-out group.

| Evaluation | Original-data baseline | Candidate |
|---|---:|---:|
| Combined held-out accuracy | 57.9% | 70.4% |
| Combined macro F1 | 0.402 | 0.488 |
| Original-source accuracy | 54.8% | 78.1% |
| New-source accuracy | 59.4% | 66.9% |

The candidate's **neutral-class F1 is 0.000**. Overall accuracy hides this weakness. Accuracy for two other predetermined group-shuffle seeds is 77.3% and 75.5%; these are sensitivity checks, not a reason to select a favorable seed. Scores measure agreement with provisional AI labels, not independently validated guest sentiment. No tuned alternative is deployed based on these development results.

## Files and reproduction

- `../../datasets/google_feedback_20261028.csv`: extracted written reviews, unlabeled.
- `../../datasets/google_sentiment_phrases_20261028.csv`: AI-proposed annotations for human review.
- `../../datasets/sentiment_phrases_candidate_20261028.csv`: combined candidate training file.
- `sentiment_model.json`: experimental candidate artifact.
- `evaluation.json`: grouped evaluation, class metrics, feature comparison, seed sensitivity.
- `comparison.json`: same-fold comparison with the original-data baseline.

Run from the repository root:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m ml.train --data backend/ml/datasets/sentiment_phrases_candidate_20261028.csv --output backend/ml/candidates/20261028_google_feedback
PYTHONPATH=backend backend/.venv/bin/python -m ml.compare_candidate --original backend/ml/datasets/sentiment_phrases.csv --expanded backend/ml/datasets/sentiment_phrases_candidate_20261028.csv --output backend/ml/candidates/20261028_google_feedback/comparison.json
```

Human-review the labels, especially neutral/ambiguous/mixed clauses, and evaluate on independent human-labeled feedback before promoting this model. This training does not publish the document's reviews, import them into bookings, or modify the live feedback database. `ml/artifacts/sentiment_model.json` remains unchanged.
