# turn raw steam post bodies (bbcode or html) into token lists

import html
import json
import re
from pathlib import Path

# image tags carry no useful words, drop them with their urls
IMG_PATTERN = re.compile(r"\[img[^\]]*\].*?\[/img\]|<img[^>]*>", re.I | re.S)
URL_PATTERN = re.compile(r"(https?://|\{STEAM_[A-Z_]+\})\S*")
BBCODE_PATTERN = re.compile(r"\[/?[a-z0-9*]+(=[^\]]*)?[^\]]*\]", re.I)
HTML_PATTERN = re.compile(r"<[^>]+>")
# words, numbers like 7.36a or 1.5, and percentages like 15%
TOKEN_PATTERN = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)*[a-z]?%?")

STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for
from further had has have having he her here hers herself him himself his how i if in
into is it its itself just me more most my myself no nor not now of off on once only or
other our ours ourselves out over own same she should so some such than that the their
theirs them themselves then there these they this those through to too under until up
very was we were what when where which while who whom why will with you your yours
yourself yourselves us also get got let s t ll re ve d m
""".split())


def strip_markup(text):
    if not text:
        return ""

    text = IMG_PATTERN.sub(" ", text)
    text = URL_PATTERN.sub(" ", text)

    # bullets become line breaks so sections stay separated
    text = re.sub(r"\[\*\]|<li[^>]*>", "\n", text, flags=re.I)
    text = BBCODE_PATTERN.sub(" ", text)
    text = HTML_PATTERN.sub(" ", text)
    return html.unescape(text)


def tokenize(text, remove_stopwords=True):
    tokens = []
    for word in TOKEN_PATTERN.findall(text.lower()):
        if remove_stopwords and (word in STOPWORDS or len(word) < 2):
            continue
        tokens.append(word)
    return tokens


# body only, titles stay out so models can't just copy the title rules
def post_tokens(post):
    return tokenize(strip_markup(post.get("contents", "")))


# read every data/<appid>_<slug>/posts.jsonl into one list
def load_posts(data_dir="data"):
    posts = []
    for path in sorted(Path(data_dir).glob("*/posts.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    posts.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # skip a half-written line
    return posts
