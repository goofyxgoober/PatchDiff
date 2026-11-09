# tf-idf vectors stored as sparse dicts {term: weight}, plus cosine

import math


class TfidfVectorizer:
    def __init__(self, min_df=2):
        self.min_df = min_df
        self.idf = {}

    # docs is a list of token lists
    def fit(self, docs):
        # document frequency of each term
        df = {}
        for tokens in docs:
            for word in set(tokens):
                df[word] = df.get(word, 0) + 1

        n = len(docs)
        self.idf = {}
        for word in df:
            if df[word] < self.min_df:
                continue  # too rare, likely a typo or one-off name
            self.idf[word] = math.log10(n / df[word])
        return self

    def transform(self, tokens):
        # raw term counts
        tf = {}
        for word in tokens:
            if word not in self.idf:
                continue  # never seen in training, ignore it
            tf[word] = tf.get(word, 0) + 1

        # log tf times idf
        vec = {}
        for word in tf:
            weight = (1 + math.log10(tf[word])) * self.idf[word]
            if weight > 0:
                vec[word] = weight
        return normalize(vec)

    def to_dict(self):
        return {"min_df": self.min_df, "idf": self.idf}

    @classmethod
    def from_dict(cls, d):
        vectorizer = cls(d["min_df"])
        vectorizer.idf = d["idf"]
        return vectorizer


def normalize(vec):
    total = 0.0
    for word in vec:
        total += vec[word] * vec[word]
    length = math.sqrt(total)

    if length == 0:
        return {}

    result = {}
    for word in vec:
        result[word] = vec[word] / length
    return result


# both vectors are already normalized, so the dot product is the cosine
def cosine(a, b):
    # loop over the shorter one
    if len(a) > len(b):
        a, b = b, a

    score = 0.0
    for word in a:
        if word in b:
            score += a[word] * b[word]
    return score
