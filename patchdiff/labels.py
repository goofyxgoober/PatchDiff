# weak labels from titles, plus the hand-labeled gold set
#
#   python -m patchdiff.labels   -> writes data/labels/gold_candidates.csv to label by hand

import csv
import random
import re
from pathlib import Path

from patchdiff.preprocess import load_posts, strip_markup

PATCH = "patch_notes"
OTHER = "other"

GOLD_PATH = Path("data/labels/gold_posts.csv")
CANDIDATES_PATH = Path("data/labels/gold_candidates.csv")

# titles that look like a changelog
PATCH_TITLE = re.compile(
    r"patch|release notes|hotfix|designer'?s notes|known issues|bug ?fix|\bupdate\b",
    re.I,
)
# titles that say "update" or "patch" but are really news, store or esports posts
NOT_PATCH_TITLE = re.compile(
    r"store|sale|countdown|anti.?cheat|bans|trailer|livestream|compendium|battle ?pass"
    r"|event pass|roadmap|teaser|coming soon|patch day",
    re.I,
)


def weak_label(post):
    title = post.get("title") or ""
    if PATCH_TITLE.search(title) and not NOT_PATCH_TITLE.search(title):
        return PATCH
    return OTHER


# returns {gid: label} for rows that have a label filled in
def load_gold(path=GOLD_PATH):
    gold = {}
    if not Path(path).exists():
        return gold
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            label = (row.get("label") or "").strip()
            if label not in (PATCH, OTHER):
                continue  # not labeled yet
            gold[row["gid"]] = label
    return gold


# pick per_game posts per game, half that look like patches by title and half that don't,
# so the gold set has both classes. the label column is left empty on purpose.
def make_gold_candidates(posts, per_game=40, seed=470):
    rng = random.Random(seed)

    by_game = {}
    for post in posts:
        game = post["game"]
        if game not in by_game:
            by_game[game] = {PATCH: [], OTHER: []}
        by_game[game][weak_label(post)].append(post)

    rows = []
    for game in sorted(by_game):
        for label in (PATCH, OTHER):
            group = by_game[game][label]
            rng.shuffle(group)
            for post in group[: per_game // 2]:
                snippet = " ".join(strip_markup(post.get("contents", "")).split())[:300]
                rows.append({
                    "gid": post["gid"],
                    "game": game,
                    "title": post.get("title"),
                    "url": post.get("url"),
                    "snippet": snippet,
                    "label": "",
                })
    rng.shuffle(rows)  # so you don't see them grouped while labeling
    return rows


def main():
    rows = make_gold_candidates(load_posts())
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATES_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["gid", "game", "title", "url", "snippet", "label"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"wrote {len(rows)} rows to {CANDIDATES_PATH}")
    print(f"fill the label column with {PATCH} or {OTHER}, then save it as {GOLD_PATH}")


if __name__ == "__main__":
    main()
