"""Group-paired uncertainty for ADV-10 saved probabilities (no inference)."""

import numpy as np

from models.train import metrics


def verdict(probabilities):
    p = np.asarray(probabilities)
    return np.where(p < 0.3, 0, np.where(p > 0.7, 2, 1))


def group_weights(rows, replicates=2000, seed=42):
    """Stratify whole groups; a multi-source group must never be split apart."""
    groups = {}
    for index, row in enumerate(rows):
        groups.setdefault(row["group_id"], []).append(index)
    strata = {}
    for group, indices in groups.items():
        labels = {rows[i]["label"] for i in indices}
        if len(labels) != 1:
            raise ValueError("Group has contradictory labels")
        key = (tuple(sorted({rows[i]["source"] for i in indices})), next(iter(labels)))
        strata.setdefault(key, []).append(group)
    rng = np.random.default_rng(seed)
    weights = np.zeros((replicates, len(rows)), dtype=np.float64)
    for key in sorted(strata):
        members = sorted(strata[key])
        draws = rng.integers(0, len(members), (replicates, len(members)))
        offsets = np.arange(replicates)[:, None] * len(members)
        counts = np.bincount(
            (draws + offsets).ravel(), minlength=replicates * len(members)
        ).reshape(replicates, len(members))
        for index, group in enumerate(members):
            weights[:, groups[group]] = counts[:, index, None]
    return weights


def weighted_stats(y, p, weights):
    """Vectorized binary statistics and tie-aware weighted AUROC per replicate."""
    y, p = np.asarray(y), np.asarray(p)
    w = np.atleast_2d(weights)
    positive = p >= 0.5
    tp = w @ (positive & (y == 1))
    fp = w @ (positive & (y == 0))
    fn = w @ (~positive & (y == 1))
    tn = w @ (~positive & (y == 0))
    with np.errstate(divide="ignore", invalid="ignore"):
        out = {
            "accuracy": (tp + tn) / w.sum(axis=1),
            "precision": tp / (tp + fp),
            "recall": tp / (tp + fn),
            "false_positive_rate": fp / (fp + tn),
            "false_negative_rate": fn / (tp + fn),
            "uncertain_rate": (w @ ((p >= 0.3) & (p <= 0.7))) / w.sum(axis=1),
        }
        out["balanced_accuracy"] = (out["recall"] + tn / (tn + fp)) / 2
        order = np.argsort(p, kind="stable")
        starts = np.r_[0, np.flatnonzero(np.diff(p[order])) + 1]
        pos = np.add.reduceat(w[:, order] * (y[order] == 1), starts, axis=1)
        neg = np.add.reduceat(w[:, order] * (y[order] == 0), starts, axis=1)
        below = np.cumsum(neg, axis=1) - neg
        out["auroc"] = (pos * (below + neg / 2)).sum(axis=1) / (
            pos.sum(axis=1) * neg.sum(axis=1)
        )
        out["a_eff"] = np.maximum(out["auroc"], 1 - out["auroc"])
    return out


def interval(values, n_groups, *, defined=True):
    valid = np.isfinite(values)
    reason = (
        "undefined_original_metric"
        if not defined
        else "fewer_than_two_groups"
        if n_groups < 2
        else "undefined_bootstrap_replicates"
        if not valid.all()
        else None
    )
    return {
        "ci95": None if reason else np.percentile(values, [2.5, 97.5]).tolist(),
        "n_boot_valid": int(valid.sum()),
        "reason": reason,
    }


def summarize_probabilities(rows, probabilities, baseline=None, *, replicates=2000):
    """Use existing point metrics; bootstrap saved outputs with shared weights."""
    y, p = np.array([r["label"] for r in rows]), np.asarray(probabilities, dtype=float)
    point = metrics(y, p, 0.5)
    n_groups = len({r["group_id"] for r in rows})
    w = group_weights(rows, replicates=replicates)
    boot = weighted_stats(y, p, w)
    original = weighted_stats(y, p, np.ones((1, len(rows))))
    point.update(
        {
            key: float(values[0]) if np.isfinite(values[0]) else None
            for key, values in original.items()
            if key not in {"precision", "recall"}
        }
    )
    predicted = p >= 0.5
    denominators = {"precision": int(predicted.sum()), "recall": int((y == 1).sum())}
    point["metric_definition"] = {
        key: {"defined": denominator > 0, "denominator": denominator}
        for key, denominator in denominators.items()
    }
    point["intervals"] = {
        key: interval(values, n_groups, defined=np.isfinite(original[key][0]))
        for key, values in boot.items()
    }
    point.update(
        n_total=len(rows),
        n_scored=len(rows),
        n_failed=0,
        n_groups=n_groups,
        n_real=int((y == 0).sum()),
        n_ai=int((y == 1).sum()),
    )
    if baseline is not None:
        base = np.asarray(baseline)
        metrics(y, base, 0.5)
        base_boot = weighted_stats(y, base, w)
        base_point = weighted_stats(y, base, np.ones((1, len(rows))))
        flips = verdict(p) != verdict(base)
        point["paired"] = {
            "n_pairs": len(rows),
            "flip_rate": float(flips.mean()),
            "flip_interval": interval((w @ flips) / w.sum(axis=1), n_groups),
            "mean_score_delta": float((p - base).mean()),
            "score_delta_interval": interval(
                (w @ (p - base)) / w.sum(axis=1), n_groups
            ),
            "transitions": np.bincount(verdict(base) * 3 + verdict(p), minlength=9)
            .reshape(3, 3)
            .tolist(),
            "deltas": {},
        }
        for key in boot:
            direction = -1 if key == "accuracy" else 1
            delta = direction * (original[key][0] - base_point[key][0])
            name = "accuracy_degradation" if key == "accuracy" else key
            point["paired"]["deltas"][name] = {
                "value": float(delta) if np.isfinite(delta) else None,
                **interval(
                    direction * (boot[key] - base_boot[key]),
                    n_groups,
                    defined=np.isfinite(delta),
                ),
            }
    return point
