# weekly ingest job: fetch the newest steam posts, keep the ones the classifier calls patch notes
# skeleton for the lambda deploy. right now it returns the patch posts instead of storing them.
#
#   local run:  python -m lambda_ingest.handler --appid 570 --dry-run
#   lambda:     handler = lambda_ingest.handler.handler
#               event = {"appids": [570, 730], "days": 7}   (both optional)

import argparse
import json
import os
import time

import requests

from patchdiff.classifiers import load_model
from scrape_steam_news import DEFAULT_GAMES, fetch_page

MODEL_PATH = os.environ.get("MODEL_PATH", "models/best.json")

# loaded once per lambda container, then reused across calls
model = None


def get_model():
    global model
    if model is None:
        model = load_model(MODEL_PATH)
    return model


def handler(event, context=None):
    event = event or {}
    appids = event.get("appids") or list(DEFAULT_GAMES)
    days = event.get("days", 7)
    since = time.time() - days * 24 * 3600

    clf = get_model()
    session = requests.Session()
    session.headers.update({"User-Agent": "patchnotes-search-research/0.1"})

    results = []
    for appid in appids:
        # one page (100 newest posts) is plenty for a weekly run
        data = fetch_page(session, appid)
        items = (data.get("appnews") or {}).get("newsitems") or []
        for item in items:
            if item["date"] < since:
                continue  # older than this run's window
            label = clf.predict(item)
            results.append({
                "appid": appid,
                "gid": item["gid"],
                "title": item.get("title"),
                "date": item["date"],
                "url": item.get("url"),
                "label": label,
            })

    patches = []
    for r in results:
        if r["label"] == "patch_notes":
            patches.append(r)

    # todo: write patches to storage and pass them to the bullet extraction step
    return {"checked": len(results), "patch_notes": patches}


def main():
    ap = argparse.ArgumentParser(description="Run the ingest handler locally.")
    ap.add_argument("--appid", type=int, nargs="*", help="steam appids (default: all 5 games)")
    ap.add_argument("--days", type=float, default=7, help="how far back to look")
    ap.add_argument("--dry-run", action="store_true", help="only print, don't store anything")
    args = ap.parse_args()

    out = handler({"appids": args.appid, "days": args.days})
    print(f"checked {out['checked']} posts, {len(out['patch_notes'])} patch notes")
    print(json.dumps(out["patch_notes"], indent=2))


if __name__ == "__main__":
    main()
