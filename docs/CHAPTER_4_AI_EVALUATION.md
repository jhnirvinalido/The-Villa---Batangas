# Chapter 4: AI-Based Feedback Analysis Results

For the implemented system workflow from verified feedback submission through
sentiment analysis, rule-based complaint categories, optional Gemini drafts,
and administrator approval, see
[`AI_FEEDBACK_ANALYSIS_PIPELINE.md`](./AI_FEEDBACK_ANALYSIS_PIPELINE.md).

## 4.1 Sentiment-classification dataset

The evaluation used 232 human-approved feedback excerpts from 66 review groups:
113 Negative, 19 Neutral, and 100 Positive. Group identifiers were kept intact
between folds, and duplicate normalized text was also prevented from crossing a
training/test boundary. Text labels were not changed during model development.
The source file is excluded from version control; its SHA-256 fingerprint is
`fc77f3514af33846940d688b9f4cee44ca1208315d66ebd72e31e4c012d7bf89`.

The primary method remained TF-IDF with Multinomial Naive Bayes. The fixed
baseline used word unigrams/bigrams and alpha 1.0. The tuning search compared
word and character n-grams, smoothing alpha, Neutral prior multipliers, and
Neutral oversampling confined to training folds. Macro F1 selected configurations;
ties were resolved using Neutral recall and then accuracy.

## 4.2 Evaluation design

Performance was estimated with three-fold nested, review-group-separated
cross-validation. Each outer test fold was excluded from parameter selection;
grouped inner folds selected the configuration using only that outer training
partition. TF-IDF vocabulary and inverse document frequencies were fitted inside
each training fold. Thus, the nested-CV scores below estimate the tuned selection
procedure against the approved labels. They are not scores from an independent
holdout set, nor an independent production-system accuracy measurement.

## 4.3 Baseline and tuned results

| Model | Accuracy | Macro F1 |
|---|---:|---:|
| Fixed word TF-IDF + Multinomial Naive Bayes baseline | 71.98% | 0.4993 |
| Inner-fold-selected tuned procedure (nested grouped CV) | 77.59% | 0.7196 |

| Class | Baseline precision | Baseline recall | Baseline F1 | Tuned precision | Tuned recall | Tuned F1 |
|---|---:|---:|---:|---:|---:|---:|
| Negative | 0.7302 | 0.8142 | 0.7699 | 0.8053 | 0.8053 | 0.8053 |
| Neutral | 0.0000 | 0.0000 | 0.0000 | 0.7500 | 0.4737 | 0.5806 |
| Positive | 0.7075 | 0.7500 | 0.7282 | 0.7477 | 0.8000 | 0.7729 |

Confusion matrices use actual classes for rows and predicted classes for
columns, ordered Negative, Neutral, Positive:

**Baseline**

| Actual \ Predicted | Negative | Neutral | Positive |
|---|---:|---:|---:|
| Negative | 92 | 0 | 21 |
| Neutral | 9 | 0 | 10 |
| Positive | 25 | 0 | 75 |

**Tuned nested-CV procedure**

| Actual \ Predicted | Negative | Neutral | Positive |
|---|---:|---:|---:|
| Negative | 91 | 1 | 21 |
| Neutral | 4 | 9 | 6 |
| Positive | 18 | 2 | 80 |

The baseline correctly classified 167 of 232 excerpts; the tuned nested-CV
procedure correctly classified 180 of 232. Neutral recall improved from 0/19 to
9/19. Accuracy increased by 5.60 percentage points, while macro F1 increased by
0.2203, reflecting improvements across the three classes rather than accuracy
alone.

The full-data inner-validation selection, used only to train the saved candidate,
was character 2–5 grams, alpha 0.25, Neutral prior multiplier 1.0, and threefold
Neutral oversampling during training. This setting is not the fixed model
configuration for every outer fold: configurations selected in the three outer
folds differed. Therefore, 77.59% is the nested model-selection estimate, not an
independent evaluation of this final all-data artifact.

## 4.4 Neutral-class analysis

The dataset prior for Neutral was 19/232 (8.19%), compared with 48.71% Negative
and 43.10% Positive. In the baseline out-of-fold predictions, all Neutral
excerpts were assigned a polarized class: nine Negative and ten Positive. The
baseline assigned Neutral posterior probability to these texts, but it never
ranked Neutral highest.

The approved Neutral excerpts are mostly factual or context-dependent statements:
villa identifiers, booking details, occupancy, facilities, and service
descriptions, along with terms such as “okay” and “average.” These phrases often
lack consistent sentiment-bearing features and can share vocabulary with
polarized examples. With only 19 Neutral excerpts from 13 groups, estimates of
Neutral performance remain uncertain. The tuned nested-CV procedure correctly
classified nine Neutral excerpts; six were still predicted Positive and four
Negative.

## 4.5 Controlled system integration test

A controlled API integration test submitted a human-approved feedback excerpt
through the public feedback endpoint and exercised the saved candidate through
sentiment inference, clause-level complaint classification, recommendation
drafting, and administrator approval. The analyzed evidence also included
approved Neutral and positive Taglish excerpts. Database calls and the Gemini
HTTP response were mocked; the candidate model, feedback-analysis logic, admin
API routes, and response validation ran locally. The test verified that the
evidence-supported recommendation remained a draft until an administrator
approved it, that approval recorded the administrator and timestamp, and that
guest identity/private notes were not sent to Gemini. No operational task was
created or executed.

This controlled test does not constitute a live guest-submission test against
the production database or a live Gemini quality evaluation. Gemini
recommendation quality is a separate evaluation: relevance, usefulness,
actionability, and factual support require a fixed rubric and human reviewers.
Sentiment accuracy does not validate generated recommendations.

## 4.6 Limitations

- The dataset is small, particularly the 19 Neutral excerpts; group-based
  sampling makes per-class estimates sensitive to which groups fall in each
  fold.
- Three-fold nested cross-validation is the reported performance estimate.
  There is no separate untouched grouped test set, and results should not be
  described as production accuracy or generalized beyond this dataset.
- English, Filipino, and Taglish variation, mixed sentiment, and ambiguous
  statements remain sources of error. Rule-based complaint categories are a
  separate heuristic pipeline.
- The candidate remains separate from the deployed model. Approval of a
  recommendation is an administrative workflow state, not scientific evidence
  that a defect has been verified.

## 4.7 Reproducibility

From the repository root, recreate the candidate artifacts without replacing the
deployed model:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m ml.train \
  --data data/THE_VILLA_HUMAN_APPROVED_MODEL_INPUT_232.csv \
  --output backend/ml/candidates/20261031_human_approved_232
```

The exact metrics, fold assignments, selected configurations, per-neutral
out-of-fold predictions, and candidate artifact are saved under
`backend/ml/candidates/20261031_human_approved_232/`. Gemini was mocked for
integration testing; no live provider call was made.
