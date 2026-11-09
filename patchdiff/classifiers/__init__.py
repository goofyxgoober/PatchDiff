# every classifier has fit(posts, labels), predict(post), to_dict() and from_dict(d)
# posts are dicts in the posts.jsonl format (title, contents, ...)

import json

from patchdiff.classifiers.baseline import KeywordClassifier
from patchdiff.classifiers.knn import KnnClassifier
from patchdiff.classifiers.naive_bayes import NaiveBayesClassifier
from patchdiff.classifiers.rocchio import RocchioClassifier

PATCH = "patch_notes"
OTHER = "other"
LABELS = [PATCH, OTHER]

MODEL_TYPES = {
    "keyword": KeywordClassifier,
    "naive_bayes": NaiveBayesClassifier,
    "rocchio": RocchioClassifier,
    "knn": KnnClassifier,
}


def save_model(model, path):
    data = {"type": model.name, "model": model.to_dict()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_model(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return MODEL_TYPES[data["type"]].from_dict(data["model"])
