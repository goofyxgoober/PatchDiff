# baseline: count patch-note words in the body, no learning
# only looks at the body, same as the learned models, so the comparison is fair

from patchdiff.preprocess import post_tokens

PATCH_WORDS = set("""
fixed fix fixes bug bugs crash crashes issue issues increased decreased reduced
nerf nerfed buff buffed adjusted changed removed added cooldown damage hotfix
patch exploit
""".split())


class KeywordClassifier:
    name = "keyword"

    # min_hits: how many patch words a post needs to count as patch notes
    def __init__(self, min_hits=5):
        self.min_hits = min_hits

    def fit(self, posts, labels):
        return self  # nothing to learn

    def predict(self, post):
        hits = 0
        for word in post_tokens(post):
            if word in PATCH_WORDS:
                hits += 1

        if hits >= self.min_hits:
            return "patch_notes"
        return "other"

    def to_dict(self):
        return {"min_hits": self.min_hits}

    @classmethod
    def from_dict(cls, d):
        return cls(d["min_hits"])
