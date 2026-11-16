# flask app for the patchdiff search ui
#
#   python -m app.server            then open http://localhost:5000

import argparse
import re
import sqlite3

from flask import Flask, jsonify, render_template, request

from patchdiff.bm25 import BM25, load_records
from patchdiff.preprocess import tokenize

DB = "data/patchdiff.db"

# player words -> words patch notes actually use
EXPANSIONS = {
    "nerf": ["reduced", "decreased", "lowered"],
    "nerfed": ["reduced", "decreased", "lowered"],
    "buff": ["increased", "raised", "improved"],
    "buffed": ["increased", "raised", "improved"],
    "bug": ["fixed", "issue"],
    "bugs": ["fixed", "issue"],
    "cd": ["cooldown"],
    "dmg": ["damage"],
}

# words in a query that ask for a change type
TYPE_WORDS = {
    "nerf": "nerf", "nerfed": "nerf", "nerfs": "nerf",
    "buff": "buff", "buffed": "buff", "buffs": "buff",
    "fix": "bug_fix", "fixed": "bug_fix", "fixes": "bug_fix", "bug": "bug_fix", "bugs": "bug_fix",
    "new": "new_content", "added": "new_content",
}

# queries that want a count or a timeline instead of a ranked list
AGGREGATE = re.compile(r"\b(how many|how often|times|count|timeline|history|which)\b", re.I)

app = Flask(__name__)
index = None
records = []


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def expand(query):
    added = []
    for word in tokenize(query, remove_stopwords=False):
        for extra in EXPANSIONS.get(word, []):
            if extra not in added:
                added.append(extra)
    return added


def keep(rec, game, change_type, year_from, year_to):
    if game and rec["game"] != game:
        return False
    if change_type and rec["change_type"] != change_type:
        return False
    year = (rec["date"] or "0000")[:4]
    if year_from and year < year_from:
        return False
    if year_to and year > year_to:
        return False
    return True


def card(rec, score=None):
    fields = ["record_id", "game", "date", "post_title", "version", "section", "parent", "text",
              "item", "item_canon", "stat", "change_type", "old_value", "new_value", "url", "flags",
              "validated", "extracted"]
    out = {}
    for f in fields:
        out[f] = rec.get(f)
    if score is not None:
        out["score"] = round(score, 2)
    return out


# longest item name that shows up in the query, so "how many times was the aug nerfed" -> "aug"
def find_item(query, game):
    q = " " + " ".join(re.sub(r"[^a-z0-9' ]", " ", query.lower()).split()) + " "
    best = None
    for rec in records:
        name = rec["item_canon"]
        if not name or (game and rec["game"] != game):
            continue
        if " " + name + " " in q and (best is None or len(name) > len(best)):
            best = name
    return best


# an item also counts when it is named inside a group like "sg553 and aug"
def names_item(canon, item):
    if not canon:
        return False
    return (" " + item + " ") in (" " + canon + " ")


def timeline_for(item, game):
    rows = []
    for rec in records:
        if names_item(rec["item_canon"], item) and (not game or rec["game"] == game):
            rows.append(card(rec))
    rows.sort(key=lambda r: r["date"] or "")
    counts = {}
    for r in rows:
        t = r["change_type"] or "other"
        counts[t] = counts.get(t, 0) + 1
    return {"item": item, "changes": rows, "counts": counts}


# "which items were nerfed 3 or more times" -> items with at least n records of that type
def leaderboard(query, game, change_type):
    nums = re.findall(r"\b(\d+)\b", query)
    at_least = int(nums[0]) if nums else 2
    counts = {}
    last = {}
    types = {}
    for rec in records:
        if not rec["item_canon"]:
            continue
        if game and rec["game"] != game:
            continue
        if change_type and rec["change_type"] != change_type:
            continue
        key = (rec["game"], rec["item_canon"])
        counts[key] = counts.get(key, 0) + 1
        if key not in last or rec["date"] > last[key]:
            last[key] = rec["date"]
        # keep the type of each change so the page can draw one square per change
        types.setdefault(key, []).append(rec["change_type"] or "other")
    rows = []
    for key in counts:
        if counts[key] >= at_least:
            rows.append({"game": key[0], "item": key[1], "count": counts[key], "last": last[key],
                         "types": sorted(types[key])})
    rows.sort(key=lambda r: (-r["count"], r["item"]))
    return {"at_least": at_least, "change_type": change_type, "items": rows}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/stats")
def stats():
    conn = connect()
    games = []
    for row in conn.execute("SELECT game, COUNT(*) AS n, COUNT(DISTINCT gid) AS posts FROM records GROUP BY game ORDER BY game"):
        games.append(dict(row))
    row = conn.execute("SELECT COUNT(*), COUNT(DISTINCT gid), MIN(date), MAX(date) FROM records").fetchone()
    conn.close()
    return jsonify({"games": games, "records": row[0], "posts": row[1], "first": row[2], "last": row[3]})


@app.route("/api/search")
def search():
    query = request.args.get("q", "").strip()
    game = request.args.get("game", "")
    change_type = request.args.get("type", "")
    year_from = request.args.get("from", "")
    year_to = request.args.get("to", "")
    k = int(request.args.get("k", 30))

    # router: counting / timeline questions get an aggregate answer
    if AGGREGATE.search(query):
        asked_type = change_type
        for word in tokenize(query, remove_stopwords=False):
            if not asked_type and word in TYPE_WORDS:
                asked_type = TYPE_WORDS[word]
        item = find_item(query, game)
        if item:
            return jsonify({"mode": "timeline", "query": query, "timeline": timeline_for(item, game)})
        if re.search(r"\bwhich\b", query, re.I):
            return jsonify({"mode": "leaderboard", "query": query, "leaderboard": leaderboard(query, game, asked_type)})

    added = expand(query)
    full_query = query + " " + " ".join(added)
    results = []
    for score, rec in index.search(full_query, k=len(index.docs)):
        if keep(rec, game, change_type, year_from, year_to):
            results.append(card(rec, score))
        if len(results) >= k:
            break
    terms = tokenize(full_query)
    return jsonify({"mode": "list", "query": query, "expanded_to": added, "terms": terms, "results": results})


@app.route("/api/timeline")
def timeline():
    item = request.args.get("item", "").strip().lower()
    game = request.args.get("game", "")
    return jsonify({"mode": "timeline", "timeline": timeline_for(item, game)})


def main():
    global index, records, DB
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()

    DB = args.db
    records = load_records(DB)
    index = BM25().fit(records)
    print(len(records), "records indexed")
    app.run(port=args.port, debug=False)


if __name__ == "__main__":
    main()
