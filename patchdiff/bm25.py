import argparse
import math
import sqlite3

from patchdiff.preprocess import tokenize


class BM25:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = []    # the record dicts
        self.tf = []      # term counts for each doc
        self.lens = []
        self.df = {}
        self.avg_len = 0.0

    def fit(self, records):
        for rec in records:
            tokens = tokenize(rec["full_text"])
            counts = {}
            for word in tokens:
                counts[word] = counts.get(word, 0) + 1
            self.docs.append(rec)
            self.tf.append(counts)
            self.lens.append(len(tokens))
            for word in counts:
                self.df[word] = self.df.get(word, 0) + 1
        if self.lens:
            self.avg_len = sum(self.lens) / len(self.lens)
        return self

    def idf(self, word):
        n = len(self.docs)
        df = self.df[word]
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens, i):
        total = 0.0
        for word in query_tokens:
            tf = self.tf[i].get(word, 0)
            if tf == 0:
                continue
            norm = 1 - self.b + self.b * self.lens[i] / self.avg_len
            total += self.idf(word) * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        return total

    # loops over every doc, no inverted index yet
    def search(self, query, k=10):
        q = tokenize(query)
        scored = []
        for i in range(len(self.docs)):
            s = self.score(q, i)
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [(s, self.docs[i]) for s, i in scored[:k]]


def load_records(db="data/patchdiff.db"):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT * FROM records")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--db", default="data/patchdiff.db")
    args = ap.parse_args()

    index = BM25().fit(load_records(args.db))
    print(len(index.docs), "records indexed")
    for score, rec in index.search(args.query, args.k):
        print(f"{score:6.2f}  {rec['game']} {rec['date']}  {rec['full_text'][:100]}")


if __name__ == "__main__":
    main()