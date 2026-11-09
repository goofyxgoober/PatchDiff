# small hand-made corpus where the right answers are obvious
#
#   python -m unittest discover tests     (or: python -m pytest tests)

import os
import tempfile
import unittest

from patchdiff.classifiers import (
    KeywordClassifier,
    KnnClassifier,
    NaiveBayesClassifier,
    RocchioClassifier,
    load_model,
    save_model,
)
from patchdiff.labels import weak_label
from patchdiff.preprocess import post_tokens, strip_markup
from patchdiff.vectorize import TfidfVectorizer, cosine

PATCH = "patch_notes"
OTHER = "other"


def post(contents, title=""):
    return {"title": title, "contents": contents}


TRAIN = [
    (post("[list][*] Fixed a crash when loading maps [*] Reduced rifle damage from 30 to 25[/list]"), PATCH),
    (post("[list][*] Fixed bug where reload animation was skipped [*] Increased smg recoil by 10%[/list]"), PATCH),
    (post("Fixed crash on startup. Reduced grenade damage. Fixed reload bug in ranked."), PATCH),
    (post("[p]Increased cooldown of dash to 12 seconds. Fixed a bug with crouch jumping.[/p]"), PATCH),
    (post("[list][*] Reduced shotgun damage [*] Fixed crash with voice chat [*] Increased armor[/list]"), PATCH),
    (post("[p]Watch the championship finals live this weekend! Teams compete for the trophy.[/p]"), OTHER),
    (post("The summer sale is here: new skins and bundles in the store for a limited time."), OTHER),
    (post("[p]Join the tournament broadcast. Our casters will cover every team and match.[/p]"), OTHER),
    (post("Celebrate the holiday event with new cosmetic skins, bundles and a festive store."), OTHER),
    (post("Congratulations to the champions! The finals crowd watched an amazing match."), OTHER),
]
TRAIN_POSTS = [p for p, _ in TRAIN]
TRAIN_LABELS = [label for _, label in TRAIN]

TEST = [
    (post("[list][*] Fixed a crash in the main menu [*] Reduced pistol damage[/list]"), PATCH),
    (post("Tune in to watch the finals match and see which team wins the trophy."), OTHER),
    (post("New skins in the store during the event sale, grab a bundle."), OTHER),
]


class PreprocessTest(unittest.TestCase):
    def test_strip_bbcode_and_images(self):
        raw = '[p][img src="{STEAM_CLAN_LOC_IMAGE}/1/a.png"][/img][/p][list][*][b]Fixed[/b] a crash[/list]'
        text = strip_markup(raw)
        self.assertNotIn("[", text)
        self.assertNotIn("STEAM_CLAN", text)
        self.assertIn("Fixed", text)

    def test_strip_html(self):
        self.assertEqual(strip_markup("<p>Hello &amp; bye</p>").split(), ["Hello", "&", "bye"])

    def test_tokens_keep_numbers_and_percent(self):
        tokens = post_tokens(post("Damage reduced by 15% in patch 7.36a"))
        self.assertIn("15%", tokens)
        self.assertIn("7.36a", tokens)
        self.assertNotIn("in", tokens)  # stopword


class VectorizeTest(unittest.TestCase):
    def test_cosine_of_same_doc_is_one(self):
        docs = [["fixed", "crash"], ["fixed", "bug"], ["skins", "store"]]
        vectorizer = TfidfVectorizer(min_df=1).fit(docs)
        vec = vectorizer.transform(["fixed", "crash"])
        self.assertAlmostEqual(cosine(vec, vec), 1.0)
        self.assertEqual(cosine(vec, vectorizer.transform(["skins", "store"])), 0.0)


class ClassifierTest(unittest.TestCase):
    def check_model(self, model):
        model.fit(TRAIN_POSTS, TRAIN_LABELS)
        for doc, label in TEST:
            self.assertEqual(model.predict(doc), label, doc["contents"])

        # saving and loading gives back the same predictions
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            save_model(model, path)
            loaded = load_model(path)
            for doc, _ in TEST:
                self.assertEqual(loaded.predict(doc), model.predict(doc))
        finally:
            os.remove(path)

    def test_keyword(self):
        self.check_model(KeywordClassifier(min_hits=2))

    def test_naive_bayes(self):
        self.check_model(NaiveBayesClassifier())

    def test_rocchio(self):
        self.check_model(RocchioClassifier(min_df=1))

    def test_knn(self):
        self.check_model(KnnClassifier(k=3, min_df=1))

    def test_naive_bayes_probabilities(self):
        model = NaiveBayesClassifier().fit(TRAIN_POSTS, TRAIN_LABELS)
        probs = model.predict_proba(TEST[0][0])
        self.assertAlmostEqual(probs[PATCH] + probs[OTHER], 1.0)
        self.assertGreater(probs[PATCH], 0.5)


class WeakLabelTest(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(weak_label(post("", "7.36a Gameplay Patch")), PATCH)
        self.assertEqual(weak_label(post("", "Release Notes for 2/2/2023")), PATCH)
        self.assertEqual(weak_label(post("", "September Store Update 2024")), OTHER)
        self.assertEqual(weak_label(post("", "The Frankfurt Major Champions")), OTHER)


if __name__ == "__main__":
    unittest.main()
