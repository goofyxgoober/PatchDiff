# PatchDiff

A search engine for video game patch notes built on Steam news posts. Most Steam posts are not patch notes (events, esports, store sales), so the first step is a text classifier that filters posts down to the ones that are.

## Checkpoint 2: core algorithm (patch-note classifier)

Four binary classifiers (`patch_notes` vs `other`), written from scratch in plain Python:

| Model | File | Idea |
|---|---|---|
| Keyword baseline | `patchdiff/classifiers/baseline.py` | count patch words ("fixed", "reduced", "nerf", ...) in the body |
| Multinomial Naive Bayes | `patchdiff/classifiers/naive_bayes.py` | log prior + add-1 smoothed log P(word \| class) |
| Rocchio | `patchdiff/classifiers/rocchio.py` | tf-idf class centroids, nearest centroid wins |
| kNN | `patchdiff/classifiers/knn.py` | cosine similarity on tf-idf, majority vote of k neighbors |

Shared pieces: `patchdiff/preprocess.py` (strip Steam BBCode/HTML, tokenize, stopwords) and `patchdiff/vectorize.py` (tf-idf, cosine).

## Setup

Python 3.10+. The classifiers only use the standard library; `requests` is needed for the scraper and the ingest job.

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

## Run

Tests on a small hand-made corpus (no install needed):

```bash
python -m unittest discover tests -v
```

Train and evaluate all four models on the scraped data (~20 s):

```bash
python -m patchdiff.evaluate
```

This prints precision, recall, F1, accuracy and confusion counts on dev and test splits, and saves the best model (by dev F1) to `models/best.json`.

Run the weekly ingest job locally (fetches the newest posts and keeps the patch notes):

```bash
python -m lambda_ingest.handler --appid 570 730 --days 30 --dry-run
```

Re-scrape the data:

```bash
python scrape_steam_news.py
```

## Labels

- **Training labels** are weak labels from post titles (`patchdiff/labels.py`): titles like "7.36a Gameplay Patch" or "Release Notes for ..." count as `patch_notes`, with exceptions for "Store Update", "Battle Pass Update", etc. The models only see the post **body**, never the title, so they can't just copy the rule.
- **Gold labels** are for the final evaluation and are labeled by hand. `python -m patchdiff.labels` writes 200 candidate posts (40 per game, both classes) to `data/labels/gold_candidates.csv`. Fill in the `label` column and save it as `data/labels/gold_posts.csv`. `evaluate` then also scores every model on the gold set and keeps those posts out of training.

## Results

Gold set: 200 hand-labeled posts (90 `patch_notes`, 110 `other`), never used for training or tuning. Hyperparameters (keyword threshold, k) were picked on the dev split.

| Model | P | R | F1 | Acc |
|---|---|---|---|---|
| Keyword baseline (hits=2) | 0.764 | 0.756 | 0.760 | 0.785 |
| **Naive Bayes** | **0.851** | **0.889** | **0.870** | **0.880** |
| Rocchio | 0.822 | 0.822 | 0.822 | 0.840 |
| kNN (k=3) | 0.743 | 0.867 | 0.800 | 0.805 |

Naive Bayes is also best on the dev split, so it is the model saved to `models/best.json` and used by the ingest job. On the weak-label test split (567 posts) the order is the same: NB 0.821 F1, Rocchio 0.790, keyword 0.727, kNN 0.721.

## Data

`data/<appid>_<game>/posts.jsonl`: about 4,000 developer announcements from Counter-Strike 2, Dota 2, Apex Legends, PUBG and Rainbow Six Siege, collected with `scrape_steam_news.py` from Steam's `ISteamNews/GetNewsForApp` API.
