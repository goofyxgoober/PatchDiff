import argparse, hashlib, html, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path 
from patchdiff.labels import PATCH, weak_label 
from patchdiff.preprocess import BBCODE_PATTERN, HTML_PATTERN, IMG_PATTERN, URL_PATTERN, load_posts 
from dotenv import load_dotenv 
import os 

load_dotenv()
NUM = r"\d+(?:\.\d+)?"
TAGS = re.compile(r"(\[/?(?:h\d|o?list|\*)[^\]]*\]|</?(?:h\d|ul|ol|li)[^>]*>|\n)", re.I)
SKIP = re.compile(r"\b(store|sales?|giveaway|merch|esports|tournaments?|credits|streams?)\b", re.I)
FROM_TO = re.compile(rf"from\s+({NUM}%?)\s+to\s+({NUM}%?)|({NUM}%?)\s*(?:->|\u2192)\s*({NUM}%?)", re.I)
CHANGES = ("buff", "nerf", "bug_fix", "new_content", "other")
COLS = ["record_id", "appid", "game", "gid", "url", "date", "post_title", "version",
        "section", "parent", "text", "full_text"]
SCHEMA = f"""CREATE TABLE IF NOT EXISTS records ({', '.join(COLS)}, item, item_canon, stat,
    change_type, old_value, new_value, validated, flags, extracted DEFAULT 0, PRIMARY KEY (record_id))"""
PROMPT = """Label bullets from video game patch notes. Reply with only a JSON array, one object per bullet:
{"id": n, "item": ..., "stat": ..., "change_type": ..., "old_value": ..., "new_value": ...}
item = the hero/weapon/thing changed, written exactly as in the bullet or parent. stat = what changed (damage, cooldown...).
change_type is one of buff, nerf, bug_fix, new_content, other. old_value/new_value are copied exactly from the text.
Use null when unsure.
 
"""

def clean(raw):
    text = HTML_PATTERN.sub(" ", BBCODE_PATTERN.sub(" ", URL_PATTERN.sub(" ", raw)))
    return re.sub(r"^[-\u2022\u2013*]+\s+", "", " ".join(html.unescape(text).split()))
 
 
# returns (section, depth, parent, text) per bullet. depth = open lists, parents come from lower depths
def segment(raw):
    items, stack, section, depth, buf, head = [], {}, "", 0, "", False
 
    def flush():
        nonlocal buf
        text, buf = clean(buf), ""
        if len(text) < 2:
            return
        for d in [d for d in stack if d >= depth]:
            del stack[d]
        items.append((section, depth, " > ".join(stack[d] for d in sorted(stack)), text))
        if depth > 0 or text.endswith(":"):
            stack[depth] = text
 
    for i, p in enumerate(TAGS.split(IMG_PATTERN.sub(" ", raw or ""))):
        if i % 2 == 0:
            buf += p
            continue
        t = p.lower()
        if re.match(r"[\[<]/h\d", t):
            section, buf, head = clean(buf), "", False
        elif re.match(r"[\[<]h\d", t):
            flush()
            head = True
        elif not head:
            flush()
            if re.match(r"[\[<]/?(o?list|ul|ol)", t):
                depth = max(0, depth + (-1 if "/" in t[:3] else 1))
    flush()
    return items



def make_records(post):
    items = segment(post.get("contents"))
    ver = re.search(r"\b\d+\.\d+[a-z]?\b", post.get("title") or "")
    day = datetime.fromtimestamp(int(post.get("date") or 0), timezone.utc).date().isoformat()
    out = []
    for i, (sec, d, parent, text) in enumerate(items):
        # a bare parent like "Abaddon" only passes its name to its children
        bare = i + 1 < len(items) and items[i + 1][1] > d and len(text.split()) <= 8 and not re.search(r"\d", text)
        if bare or len(text.split()) < 2 or SKIP.search(sec):
            continue
        full = f"{parent}: {text}" if parent else text
        out.append(dict(record_id=hashlib.sha1(f"{post['gid']}|{i}|{full}".encode()).hexdigest()[:16],
                        appid=str(post.get("appid") or ""), game=post.get("game"), gid=str(post["gid"]),
                        url=post.get("url"), date=day, post_title=post.get("title"),
                        version=ver.group(0) if ver else "", section=sec, parent=parent,
                        text=text[:800], full_text=full[:1000]))
    return out
 
 
def save(conn, r, o):
    full, flags = r["full_text"], []
    nums = re.findall(NUM, full)
 
    def val(key):
        v = o.get(key)
        v = str(v).strip() if v not in (None, "") else None
        if v and not (all(n in nums for n in re.findall(NUM, v)) if re.search(r"\d", v) else v.lower() in full.lower()):
            flags.append(key + "_not_in_text")
            return None
        return v
 
    old, new = val("old_value"), val("new_value")
    item = str(o.get("item") or "").strip() or None
    if item and item.lower() not in full.lower():
        flags.append("item_not_in_text")
        item = None
    change = str(o.get("change_type")).lower().replace(" ", "_").replace("-", "_")
    if change not in CHANGES:
        change = "other"
        flags.append("bad_change_type")
    m = FROM_TO.search(full)  # regex beats the llm when they disagree
    if m and (old, new) != (m.group(1) or m.group(3), m.group(2) or m.group(4)):
        old, new = m.group(1) or m.group(3), m.group(2) or m.group(4)
        flags.append("regex_override")
    canon = " ".join(re.sub(r"[^a-z0-9' ]", " ", item.lower()).split()) if item else None
    conn.execute("UPDATE records SET item=?, item_canon=?, stat=?, change_type=?, old_value=?, new_value=?,"
                 " validated=?, flags=?, extracted=1 WHERE record_id=?",
                 (item, canon, o.get("stat"), change, old, new, int(not flags), ",".join(flags), r["record_id"]))
 
 
def extract(conn, llm, n=20):
    rows = conn.execute("SELECT record_id, section, parent, text, full_text FROM records WHERE extracted = 0").fetchall()
    for s in range(0, len(rows), n):
        batch = rows[s:s + n]
        lines = [f"[{i}] section: {r['section']} | parent: {r['parent']} | text: {r['text'][:500]}"
                 for i, r in enumerate(batch)]
        reply = llm.invoke(PROMPT + "\n".join(lines)).content
        try:
            data = json.loads(reply[reply.find("["):reply.rfind("]") + 1])
        except json.JSONDecodeError:
            continue  # stays extracted=0, next run retries
        for o in data:
            if isinstance(o, dict) and isinstance(o.get("id"), int) and 0 <= o["id"] < len(batch):
                save(conn, batch[o["id"]], o)
        conn.commit()
        print(f"{min(s + n, len(rows))}/{len(rows)}")
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--limit-posts", type=int)
    ap.add_argument("--db", default="data/patchdiff.db")
    args = ap.parse_args()
 
    try:
        from patchdiff.classifiers import load_model
        model = load_model("models/best.json")
    except Exception:
        model = None  # falls back to title rules
    posts = [p for p in load_posts() if (model.predict(p) if model else weak_label(p)) == PATCH]
    posts.sort(key=lambda p: int(p.get("date") or 0))
 
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    seen = set()
    for post in posts[:args.limit_posts]:
        recs = make_records(post)
        sig = hash(tuple(r["full_text"] for r in recs))
        if not recs or sig in seen:  # skip reposts with identical bullets
            continue
        seen.add(sig)
        conn.executemany(f"INSERT OR IGNORE INTO records ({', '.join(COLS)}) VALUES ({', '.join(':' + c for c in COLS)})", recs)
    conn.commit()
    print(conn.execute("SELECT COUNT(*) FROM records").fetchone()[0], "records stored")
 
    if not args.no_llm:
        from langchain_openai import ChatOpenAI
        extract(conn, ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=4096,
                             api_key=os.environ["OPENAI_API_KEY"]))
 
 
if __name__ == "__main__":
    main()
