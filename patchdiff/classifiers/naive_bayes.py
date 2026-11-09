# multinomial naive bayes with add-1 smoothing, all math in log space

import math

from patchdiff.preprocess import post_tokens


class NaiveBayesClassifier:
    name = "naive_bayes"

    def __init__(self):
        self.labels = []
        self.doc_counts = {}   # label -> number of training docs
        self.word_counts = {}  # label -> {word: count}
        self.total_words = {}  # label -> total word count
        self.vocab = set()

    def fit(self, posts, labels):
        self.labels = sorted(set(labels))
        self.doc_counts = {}
        self.word_counts = {}
        self.vocab = set()
        for label in self.labels:
            self.doc_counts[label] = 0
            self.word_counts[label] = {}

        for i in range(len(posts)):
            label = labels[i]
            self.doc_counts[label] += 1
            counts = self.word_counts[label]
            for word in post_tokens(posts[i]):
                counts[word] = counts.get(word, 0) + 1
                self.vocab.add(word)

        # total word count per class (denominator part of P(w|c))
        self.total_words = {}
        for label in self.labels:
            total = 0
            for word in self.word_counts[label]:
                total += self.word_counts[label][word]
            self.total_words[label] = total
        return self

    # log P(c) + sum of log P(w|c) for each label
    def log_scores(self, post):
        tokens = post_tokens(post)
        n_docs = 0
        for label in self.labels:
            n_docs += self.doc_counts[label]
        v = len(self.vocab)

        scores = {}
        for label in self.labels:
            # log prior
            score = math.log(self.doc_counts[label] / n_docs)
            counts = self.word_counts[label]
            for word in tokens:
                if word not in self.vocab:
                    continue  # never seen in training, ignore it
                score += math.log((counts.get(word, 0) + 1) / (self.total_words[label] + v))
            scores[label] = score
        return scores

    def predict(self, post):
        scores = self.log_scores(post)
        max_score = None
        max_label = None
        for label in self.labels:
            if max_score is None or scores[label] > max_score:
                max_score = scores[label]
                max_label = label
        return max_label

    # turn log scores into probabilities that sum to 1
    def predict_proba(self, post):
        scores = self.log_scores(post)
        max_score = None
        for label in scores:
            if max_score is None or scores[label] > max_score:
                max_score = scores[label]

        # subtract the max first so exp() doesn't underflow to 0
        total = 0.0
        probs = {}
        for label in scores:
            probs[label] = math.exp(scores[label] - max_score)
            total += probs[label]
        for label in probs:
            probs[label] = probs[label] / total
        return probs

    def to_dict(self):
        return {
            "labels": self.labels,
            "doc_counts": self.doc_counts,
            "word_counts": self.word_counts,
            "total_words": self.total_words,
            "vocab": sorted(self.vocab),
        }

    @classmethod
    def from_dict(cls, d):
        model = cls()
        model.labels = d["labels"]
        model.doc_counts = d["doc_counts"]
        model.word_counts = d["word_counts"]
        model.total_words = d["total_words"]
        model.vocab = set(d["vocab"])
        return model
