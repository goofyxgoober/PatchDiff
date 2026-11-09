# train all four classifiers, tune on dev, report on test (and gold if it exists),
# save the best one to models/best.json
#
#   python -m patchdiff.evaluate

import random
from pathlib import Path

from patchdiff.classifiers import (
    KeywordClassifier,
    KnnClassifier,
    NaiveBayesClassifier,
    RocchioClassifier,
    save_model,
)
from patchdiff.labels import OTHER, PATCH, load_gold, weak_label
from patchdiff.preprocess import load_posts

SEED = 470
KEYWORD_HITS = [2, 3, 5, 8, 12]
KNN_KS = [1, 3, 5, 9, 15]
BEST_PATH = Path("models/best.json")


# shuffle each class on its own so train/dev/test keep the same class mix
def split(posts, labels, dev_frac=0.15, test_frac=0.15, seed=SEED):
    rng = random.Random(seed)
    by_label = {}
    for i in range(len(posts)):
        by_label.setdefault(labels[i], []).append(i)

    parts = {"train": [], "dev": [], "test": []}
    for label in sorted(by_label):
        idx = by_label[label]
        rng.shuffle(idx)
        n_dev = int(len(idx) * dev_frac)
        n_test = int(len(idx) * test_frac)
        parts["dev"] += idx[:n_dev]
        parts["test"] += idx[n_dev:n_dev + n_test]
        parts["train"] += idx[n_dev + n_test:]

    result = {}
    for name in parts:
        result[name] = ([posts[i] for i in parts[name]], [labels[i] for i in parts[name]])
    return result


# precision / recall / f1 for the patch_notes class, plus accuracy and confusion counts
def score(gold, pred):
    tp = fp = fn = tn = 0
    for i in range(len(gold)):
        if pred[i] == PATCH and gold[i] == PATCH:
            tp += 1
        elif pred[i] == PATCH:
            fp += 1
        elif gold[i] == PATCH:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(gold) if gold else 0.0
    return {"p": precision, "r": recall, "f1": f1, "acc": accuracy,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def predict_all(model, posts):
    preds = []
    for post in posts:
        preds.append(model.predict(post))
    return preds


def print_table(title, results):
    print(f"\n{title}")
    print(f"{'model':<22}{'P':>7}{'R':>7}{'F1':>7}{'Acc':>7}   TP   FP   FN   TN")
    for name in results:
        m = results[name]
        print(f"{name:<22}{m['p']:7.3f}{m['r']:7.3f}{m['f1']:7.3f}{m['acc']:7.3f}"
              f" {m['tp']:4d} {m['fp']:4d} {m['fn']:4d} {m['tn']:4d}")


def main():
    posts = load_posts()
    gold = load_gold()

    # gold posts are only for testing, keep them out of training
    train_pool = []
    for post in posts:
        if post["gid"] in gold:
            continue
        train_pool.append(post)
    labels = []
    for post in train_pool:
        labels.append(weak_label(post))

    n_patch = labels.count(PATCH)
    print(f"{len(posts)} posts, {len(gold)} gold labeled, "
          f"weak labels: {n_patch} {PATCH} / {len(labels) - n_patch} {OTHER}")

    data = split(train_pool, labels)
    train_x, train_y = data["train"]
    dev_x, dev_y = data["dev"]
    test_x, test_y = data["test"]
    print(f"train {len(train_x)}, dev {len(dev_x)}, test {len(test_x)}")

    models = {}
    dev_results = {}

    # keyword baseline: pick min_hits on dev
    best = None
    for hits in KEYWORD_HITS:
        result = score(dev_y, predict_all(KeywordClassifier(hits), dev_x))
        if best is None or result["f1"] > best[1]["f1"]:
            best = (hits, result)
    models[f"keyword (hits={best[0]})"] = KeywordClassifier(best[0])
    dev_results[f"keyword (hits={best[0]})"] = best[1]

    nb = NaiveBayesClassifier().fit(train_x, train_y)
    models["naive_bayes"] = nb
    dev_results["naive_bayes"] = score(dev_y, predict_all(nb, dev_x))

    rocchio = RocchioClassifier().fit(train_x, train_y)
    models["rocchio"] = rocchio
    dev_results["rocchio"] = score(dev_y, predict_all(rocchio, dev_x))

    # knn: rank neighbors once per dev doc, then try every k on that ranking
    knn = KnnClassifier().fit(train_x, train_y)
    ranked = []
    for post in dev_x:
        ranked.append(knn.neighbors(post))
    best = None
    for k in KNN_KS:
        preds = []
        for sims in ranked:
            votes = {}
            for sim, label in sims[:k]:
                votes[label] = votes.get(label, 0) + 1
            preds.append(PATCH if votes.get(PATCH, 0) > votes.get(OTHER, 0) else OTHER)
        result = score(dev_y, preds)
        if best is None or result["f1"] > best[1]["f1"]:
            best = (k, result)
    knn.k = best[0]
    models[f"knn (k={best[0]})"] = knn
    dev_results[f"knn (k={best[0]})"] = best[1]

    print_table("dev (weak labels, used for tuning)", dev_results)

    test_results = {}
    for name in models:
        test_results[name] = score(test_y, predict_all(models[name], test_x))
    print_table("test (weak labels, held out)", test_results)

    if gold:
        gold_posts = []
        gold_y = []
        for post in posts:
            if post["gid"] in gold:
                gold_posts.append(post)
                gold_y.append(gold[post["gid"]])
        gold_results = {}
        for name in models:
            gold_results[name] = score(gold_y, predict_all(models[name], gold_posts))
        print_table("gold (hand labeled)", gold_results)
    else:
        print("\nno gold labels yet: run `python -m patchdiff.labels`, label the csv, "
              "save it as data/labels/gold_posts.csv")

    # pick the best model by dev f1, never by test or gold
    best_name = None
    for name in dev_results:
        if best_name is None or dev_results[name]["f1"] > dev_results[best_name]["f1"]:
            best_name = name
    BEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_model(models[best_name], BEST_PATH)
    print(f"\nbest on dev: {best_name} -> saved to {BEST_PATH}")


if __name__ == "__main__":
    main()
