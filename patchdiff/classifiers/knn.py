# k nearest neighbors with cosine similarity on tf-idf vectors

from patchdiff.preprocess import post_tokens
from patchdiff.vectorize import TfidfVectorizer, cosine


class KnnClassifier:
    name = "knn"

    def __init__(self, k=5, min_df=2):
        self.k = k
        self.vectorizer = TfidfVectorizer(min_df)
        self.vectors = []
        self.labels = []

    def fit(self, posts, labels):
        docs = []
        for post in posts:
            docs.append(post_tokens(post))
        self.vectorizer.fit(docs)

        # knn just remembers every training vector
        self.vectors = []
        for tokens in docs:
            self.vectors.append(self.vectorizer.transform(tokens))
        self.labels = list(labels)
        return self

    # similarity to every training doc, best first
    def neighbors(self, post):
        vec = self.vectorizer.transform(post_tokens(post))
        sims = []
        for i in range(len(self.vectors)):
            sims.append((cosine(vec, self.vectors[i]), self.labels[i]))
        sims.sort(reverse=True)
        return sims

    def predict(self, post, k=None):
        if k is None:
            k = self.k
        top = self.neighbors(post)[:k]

        # majority vote, ties go to the label with the higher total similarity
        votes = {}
        sim_total = {}
        for sim, label in top:
            votes[label] = votes.get(label, 0) + 1
            sim_total[label] = sim_total.get(label, 0.0) + sim

        max_label = None
        for label in sorted(votes):
            if max_label is None:
                max_label = label
            elif votes[label] > votes[max_label]:
                max_label = label
            elif votes[label] == votes[max_label] and sim_total[label] > sim_total[max_label]:
                max_label = label
        return max_label

    def to_dict(self):
        return {
            "k": self.k,
            "vectorizer": self.vectorizer.to_dict(),
            "vectors": self.vectors,
            "labels": self.labels,
        }

    @classmethod
    def from_dict(cls, d):
        model = cls(d["k"])
        model.vectorizer = TfidfVectorizer.from_dict(d["vectorizer"])
        model.vectors = d["vectors"]
        model.labels = d["labels"]
        return model
