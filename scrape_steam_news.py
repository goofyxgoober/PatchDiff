#!/usr/bin/env python3

import argparse
import json
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

# Default: 5 popular competitive multiplayer games on Steam.
DEFAULT_GAMES = {
    730: "counter-strike-2",
    570: "dota-2",
    1172470: "apex-legends",
    578080: "pubg-battlegrounds",
    359550: "rainbow-six-siege",
}

DEV_FEED = "steam_community_announcements"
PAGE_SIZE = 100  # posts per request

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


class RateLimiter:
    """Thread-safe global limiter: at most `max_rps` requests/sec across ALL threads."""

    def __init__(self, max_rps):
        self.interval = 1.0 / max_rps
        self.lock = threading.Lock()
        self.next_ok = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_ok)
            self.next_ok = slot + self.interval
        time.sleep(max(0.0, slot - now))


LIMITER = RateLimiter(3.0)  # overwritten in main() from --max-rps


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fetch_page(session, appid, enddate=None, feeds=DEV_FEED, retries=5):
    """Fetch one page of news with exponential backoff on errors / rate limits."""
    params = {
        "appid": appid,
        "count": PAGE_SIZE,
        "maxlength": 0,  # 0 = full content, no truncation
        "format": "json",
    }
    if enddate:
        params["enddate"] = enddate  # only posts with date <= enddate
    if feeds:
        params["feeds"] = feeds

    for attempt in range(retries):
        try:
            LIMITER.wait()
            r = session.get(API_URL, params=params, timeout=30)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                log(f"    rate limited (429), sleeping {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            wait = 2 ** attempt * 2
            log(f"    error: {e} (retry in {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch appid={appid} enddate={enddate}")


def load_existing(posts_path: Path):
    """Return {gids, oldest, newest} from an existing posts.jsonl."""
    gids, dates = set(), []
    if posts_path.exists():
        with posts_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    p = json.loads(line)
                except json.JSONDecodeError:
                    continue
                gids.add(p["gid"])
                dates.append(p["date"])
    return {
        "gids": gids,
        "oldest": min(dates) if dates else None,
        "newest": max(dates) if dates else None,
    }


def scrape_game(session, appid, name, out_root, delay, feeds):
    game_dir = out_root / f"{appid}_{slugify(name)}"
    raw_dir = game_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    posts_path = game_dir / "posts.jsonl"

    state = load_existing(posts_path)
    seen, oldest, newest = state["gids"], state["oldest"], state["newest"]
    log(f"[{name}] start — {len(seen)} posts already saved")

    total_new = 0

    def run_pass(start_enddate, stop_when_older_than=None):
        """Walk backwards from start_enddate until the API runs dry."""
        nonlocal total_new
        enddate = start_enddate
        page = 0
        while True:
            data = fetch_page(session, appid, enddate, feeds)
            items = (data.get("appnews") or {}).get("newsitems") or []
            if not items:
                break

            stamp = enddate if enddate else "latest"
            (raw_dir / f"page_{stamp}_{page}.json").write_text(
                json.dumps(data), encoding="utf-8"
            )

            fresh = []
            for it in items:
                if it["gid"] in seen:
                    continue
                seen.add(it["gid"])
                fresh.append(
                    {
                        "gid": it["gid"],
                        "appid": appid,
                        "game": name,
                        "title": it.get("title"),
                        "url": it.get("url"),
                        "author": it.get("author"),
                        "feedlabel": it.get("feedlabel"),
                        "feedname": it.get("feedname"),
                        "feed_type": it.get("feed_type"),
                        "date": it["date"],
                        "date_iso": datetime.fromtimestamp(
                            it["date"], tz=timezone.utc
                        ).isoformat(),
                        "tags": it.get("tags", []),
                        "contents": it.get("contents", ""),  # FULL body (BBCode/HTML)
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

            if fresh:
                with posts_path.open("a", encoding="utf-8") as f:
                    for p in fresh:
                        f.write(json.dumps(p, ensure_ascii=False) + "\n")
                total_new += len(fresh)

            page_oldest = min(it["date"] for it in items)
            log(
                f"[{name}] page {page}: {len(items)} items, {len(fresh)} new, "
                f"oldest={datetime.fromtimestamp(page_oldest, tz=timezone.utc):%Y-%m-%d}"
            )

            if stop_when_older_than and page_oldest <= stop_when_older_than:
                break
            if len(items) < PAGE_SIZE:
                break
            if enddate is not None and page_oldest - 1 >= enddate:
                break  # no progress, avoid infinite loop

            enddate = page_oldest - 1
            page += 1
            time.sleep(delay)

        return

    # grab anything newer than what we already have (or everything if fresh start)
    run_pass(None, stop_when_older_than=newest)
    time.sleep(delay)
    #  continue backwards past the oldest saved post
    if oldest:
        run_pass(oldest - 1)

    log(f"[{name}] done — {total_new} new posts -> {posts_path}")
    return total_new


def main():
    ap = argparse.ArgumentParser(description="Scrape full Steam news for games.")
    ap.add_argument("--games", nargs="*", type=int, help="Steam appids (default: top 5 preset)")
    ap.add_argument("--out", default="data", help="Output directory (default: ./data)")
    ap.add_argument("--delay", type=float, default=0.3, help="Extra per-game pause between pages")
    ap.add_argument("--workers", type=int, default=5, help="Games scraped in parallel (default 5)")
    ap.add_argument("--max-rps", type=float, default=3.0, help="Global cap on requests/sec across all threads")
    ap.add_argument(
        "--all-feeds",
        action="store_true",
        help="Include third-party press feeds, not just developer announcements",
    )
    args = ap.parse_args()

    games = (
        {a: DEFAULT_GAMES.get(a, f"app-{a}") for a in args.games}
        if args.games
        else DEFAULT_GAMES
    )
    feeds = None if args.all_feeds else DEV_FEED

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    global LIMITER
    LIMITER = RateLimiter(args.max_rps)

    def worker(appid, name):
        # requests.Session isn't guaranteed thread-safe -> one session per worker
        session = requests.Session()
        session.headers.update({"User-Agent": "patchnotes-search-research/0.1"})
        try:
            return scrape_game(session, appid, name, out_root, args.delay, feeds)
        except Exception as e:
            log(f"[{name}] !! {e}\n{traceback.format_exc()}")
            return 0

    total = 0
    ex = ThreadPoolExecutor(max_workers=max(1, args.workers))
    try:
        futures = [ex.submit(worker, a, n) for a, n in games.items()]
        for f in as_completed(futures):
            total += f.result() or 0
    except KeyboardInterrupt:
        log("\nInterrupted — cancelling, progress saved. Re-run to resume.")
        ex.shutdown(wait=False, cancel_futures=True)
        sys.exit(1)
    ex.shutdown()
    print(f"\nTotal new posts: {total}")
    print("\nDone.")


if __name__ == "__main__":
    main()