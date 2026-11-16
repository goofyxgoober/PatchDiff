# PatchDiff

A search engine for video game patch notes. PatchDiff turns Steam patch posts into individual changes (item, change type, stat, old → new value) that you can search all at once.

Games: Counter-Strike 2, Dota 2, Apex Legends, PUBG: Battlegrounds and Rainbow Six Siege.

## Run the UI

You need Python 3.10+. You don't need an API key: the UI reads the sample database in the repo (`data/patchdiff.db`).

**1. Install** (first time only):

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

On macOS/Linux, activate with `source venv/bin/activate`.

**2. Start the server:**

```bash
python -m app.server
```

**3. Open** http://localhost:5000. Stop the server with `Ctrl+C`.

Options: `--db data/test.db` uses another database, and `--port 8000` uses another port.

### Things to try

| Type | You get |
|---|---|
| `aug`, `c4 radius` | Matching changes, ranked |
| `recoil nerf` | The same, and "nerf" is also searched as *reduced, decreased, lowered* |
| `how many times was the aug changed` | The item's history, grouped by patch |
| `which items were nerfed 2 or more times` | A table of items and their counts |

Filter by game, year or change type on the left. Click an item name to see its history.

### If something's off

- **`No module named 'flask'`:** the venv isn't active. Rerun step 1.
- **Port 5000 is busy:** use `--port 8000`.
- **Changes don't show up:** restart the server. It loads the page template and database at startup.
- **Only 2014 CS/Dota results:** the included database is a small sample. [Build a bigger one](#build-the-database).

## Build the database

This is optional. It extracts changes with an LLM through [OpenRouter](https://openrouter.ai).

**1.** Create a `.env` file in the project folder (it's gitignored):

```
OPENAI_API_KEY=your-openrouter-key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-oss-120b
```

**2.** Extract the newest posts of each game, starting small:

```bash
python -m patchdiff.records --per-game 1 --db data/test.db
```

**3.** Point the UI at it:

```bash
python -m app.server --db data/test.db
```

Running step 2 again resumes where it stopped. Other options: `--no-llm` splits posts into bullets only (no item or change type), and `--limit-posts N` takes the oldest N posts overall.

## Other commands

| Command | What it does |
|---|---|
| `python -m unittest discover tests` | Runs the tests |
| `python -m patchdiff.evaluate` | Trains and scores the classifiers, saves the best to `models/best.json` |
| `python -m patchdiff.bm25 "aug recoil"` | Searches from the terminal |
| `python scrape_steam_news.py` | Fetches new Steam posts (only the ones you don't have yet) |
| `python -m lambda_ingest.handler --days 30 --dry-run` | Runs the weekly ingest job locally |

## Project layout

```
app/                 the web UI (Flask server, page, CSS, JS)
patchdiff/           classifiers, record extraction (records.py), BM25 search (bm25.py)
lambda_ingest/       weekly ingest job
scrape_steam_news.py Steam scraper
data/                scraped posts, hand labels, records database
models/best.json     the trained classifier
tests/               unit tests
```

## Classifier results

Most Steam posts aren't patch notes, so four classifiers written from scratch filter them. Each one is trained on weak labels from post titles but only sees the post body. They're scored on 200 posts labeled by hand:

| Model | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|
| Keyword baseline | 0.764 | 0.756 | 0.760 | 0.785 |
| **Naive Bayes** | **0.851** | **0.889** | **0.870** | **0.880** |
| Rocchio | 0.822 | 0.822 | 0.822 | 0.840 |
| kNN (k=3) | 0.743 | 0.867 | 0.800 | 0.805 |

Naive Bayes is the model the rest of the pipeline uses.

## Data

- **Posts:** about 4,000 developer posts from Steam's public news API, in `data/<appid>_<game>/posts.jsonl`.
- **Records:** `data/patchdiff.db` holds one row per extracted change. The included copy is a 200-record sample.
