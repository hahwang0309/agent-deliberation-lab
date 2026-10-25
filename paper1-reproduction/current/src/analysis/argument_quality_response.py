"""Link saved argument ratings to discussion responses (post-hoc, no model calls)."""
import hashlib

import numpy as np
import pandas as pd


def align_ratings(ratings, plan, original_plan):
    """Check the recorded row sequence and WA/length against identical argument plans.

    The historic CSV has no argument text/hash, so this is metadata/order alignment,
    not cryptographic verification of the original API request.
    """
    planned = {t["key"]: t for t in plan["topics"]}
    original = {t["key"]: t for t in original_plan["topics"]}
    expected = []
    for key, topic in planned.items():
        if key not in original or topic["meta"]["arguments"] != original[key]["meta"]["arguments"]:
            raise ValueError(f"Argument text differs between plans: {key}")
        for quality, arguments in topic["meta"]["arguments"].items():
            for a in arguments:
                expected.append((key, quality, a))
    if len(ratings) != len(expected):
        raise ValueError("Rating count does not match the full argument plan")
    rows = []
    for r, (key, quality, a) in zip(ratings.to_dict("records"), expected):
        if (r["topic_key"] != key or r["quality"] != quality
                or not np.isclose(float(r["wa"]), a["wa"], rtol=0, atol=1e-10)
                or int(r["tokens"]) != a["tokens"]):
            raise ValueError(f"Rating metadata/order mismatch: {key}/{quality}")
        if not np.isfinite(r["rating"]) or not 0 <= r["rating"] <= 1:
            raise ValueError("Missing or out-of-range argument rating")
        rows.append({**r, "topic": key.rsplit("-", 1)[0],
                     "argument_sha256": hashlib.sha256(a["argument"].encode()).hexdigest()})
    return pd.DataFrame(rows)


def summarize_ratings(ratings):
    keys = ["topic", "topic_key"]
    means = ratings.groupby(keys + ["quality"])["rating"].mean().unstack("quality")
    counts = ratings.groupby(keys + ["quality"]).size().unstack("quality")
    if not {"strong", "weak"}.issubset(means) or means[["strong", "weak"]].isna().any().any():
        raise ValueError("Both argument qualities must be rated for every set")
    if not counts["strong"].eq(counts["weak"]).all():
        raise ValueError("Unequal strong/weak argument counts")
    means["rating_gap"] = means["strong"] - means["weak"]
    return means.reset_index()


def response_contrasts(outcomes):
    """Full strong-minus-weak contrast, paired within support and repeat.

    In a balanced design mean(delta * sign(quality)) is HALF this contrast.
    """
    keys = ["topic", "topic_key", "engine", "support", "replicate"]
    if outcomes.duplicated(keys + ["quality"]).any():
        raise ValueError("Duplicate discussion outcome")
    pairs = outcomes.pivot(index=keys, columns="quality", values="delta")
    if not {"strong", "weak"}.issubset(pairs) or pairs[["strong", "weak"]].isna().any().any():
        raise ValueError("Incomplete strong/weak outcome pair")
    pairs["response_gap"] = pairs["strong"] - pairs["weak"]
    return pairs.reset_index().groupby(["topic", "topic_key", "engine"], as_index=False).agg(
        response_gap=("response_gap", "mean"), n_pairs=("response_gap", "size"))


def topic_bootstrap(frame, columns, n_boot, seed):
    """Equal weight for topics; preserve opposite initial sides within each topic."""
    values = frame.groupby("topic")[columns].mean()
    if len(values) < 2 or not np.isfinite(values.to_numpy()).all():
        raise ValueError("Need finite observations from at least two topics")
    x = values.to_numpy()
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(x), size=(n_boot, len(x)))
    draws = x[indices].mean(axis=1)
    lo, hi = np.quantile(draws, [.025, .975], axis=0)
    return {column: {"estimate": float(x[:, j].mean()), "ci": [float(lo[j]), float(hi[j])],
                     "n_topics": len(x)} for j, column in enumerate(columns)}
