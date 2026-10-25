"""Post-hoc within-discussion and between-discussion variance decomposition."""
import numpy as np
import pandas as pd


def paired_groups(agents, arms):
    """Keep complete five-member blocks with identical members and seeds across arms."""
    a = agents[agents.label.isin(arms)].copy()
    if a.duplicated(["item_id", "block", "label", "participant"]).any():
        raise ValueError("Duplicate participant in a block/arm")
    kept = []
    for (_, block), g in a.groupby(["item_id", "block"]):
        if set(g.label) != set(arms):
            raise ValueError(f"Unpaired block: {block}")
        pre = g.pivot(index="participant", columns="label", values="pre")
        if len(pre) != 5 or pre.isna().any().any() or not pre.eq(pre.iloc[:, 0], axis=0).all().all():
            raise ValueError(f"Members/seeds differ between arms: {block}")
        if g.post.notna().all():
            kept.append(g)
    if not kept:
        raise ValueError("No complete groups")
    return pd.concat(kept, ignore_index=True)


def decompose(agents, value="post"):
    """Equal-size groups: total variance = mean within variance + variance of means."""
    rows = []
    for (item, label), g in agents.groupby(["item_id", "label"]):
        groups = g.groupby("block")[value]
        if groups.size().nunique() != 1 or g[value].isna().any():
            raise ValueError("Requires equal-sized complete groups")
        means = groups.mean()
        w = groups.var(ddof=0).mean()
        b = means.var(ddof=0)
        t = g[value].var(ddof=0)
        rows.append(dict(item=item, label=label, n_groups=len(means), within=w,
                         between=b, total=t, between_share=b/t if t else 0.,
                         between_unbiased=means.var(ddof=1)))
    return pd.DataFrame(rows)


def item_bootstrap(frame, columns, n_boot=10000, seed=20261019):
    """Resample policy items, retaining all paired arms and all metrics together."""
    x = frame[columns].to_numpy()
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite item estimates")
    rng = np.random.default_rng(seed)
    idx = rng.integers(len(x), size=(n_boot, len(x)))
    draws = x[idx].mean(axis=1)
    lo, hi = np.quantile(draws, [.025, .975], axis=0)
    return {c: dict(estimate=float(x[:, j].mean()), ci=[float(lo[j]), float(hi[j])])
            for j, c in enumerate(columns)}
