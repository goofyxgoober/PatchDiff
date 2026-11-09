# rocchio: one centroid per class, predict the class with the closest centroid

from patchdiff.preprocess import post_tokens
from patchdiff.vectorize import TfidfVectorizer


class RocchioClassifier:
    name = "rocchio"

    def __init__(self, min_df=2):
        self.vectorizer = TfidfVectorizer(min_df)
        self.centroids = {}     # label -> {word: weight}
        self.centroid_len = {}  # label -> |centroid|^2

    def fit(self, posts, labels):
        docs = []
        for post in posts:
            docs.append(post_tokens(post))
        self.vectorizer.fit(docs)

        # add up the vectors of each class
        sums = {}
        counts = {}
        for i in range(len(docs)):
            label = labels[i]
            if label not in sums:
                sums[label] = {}
                counts[label] = 0
            counts[label] += 1
            vec = self.vectorizer.transform(docs[i])
            for word in vec:
                sums[label][word] = sums[label].get(word, 0.0) + vec[word]

        # divide by class size to get the average vector
        self.centroids = {}
        self.centroid_len = {}
        for label in sums:
            centroid = {}
            length = 0.0
            for word in sums[label]:
                centroid[word] = sums[label][word] / counts[label]
                length += centroid[word] * centroid[word]
            self.centroids[label] = centroid
            self.centroid_len[label] = length
        return self

    def predict(self, post):
        vec = self.vectorizer.transform(post_tokens(post))

        # |c - d|^2 = |c|^2 - 2 c.d + |d|^2, and |d|^2 is 1 for every class so we skip it
        min_dist = None
        min_label = None
        for label in sorted(self.centroids):
            centroid = self.centroids[label]
            dot = 0.0
            for word in vec:
                if word in centroid:
                    dot += vec[word] * centroid[word]
            dist = self.centroid_len[label] - 2 * dot
            if min_dist is None or dist < min_dist:
                min_dist = dist
                min_label = label
        return min_label

    def to_dict(self):
        return {
            "vectorizer": self.vectorizer.to_dict(),
            "centroids": self.centroids,
            "centroid_len": self.centroid_len,
        }

    @classmethod
    def from_dict(cls, d):
        model = cls()
        model.vectorizer = TfidfVectorizer.from_dict(d["vectorizer"])
        model.centroids = d["centroids"]
        model.centroid_len = d["centroid_len"]
        return model
