"""Robust statistics used across services. Inputs are floats derived from Decimal aggregates."""

from __future__ import annotations

import math
from collections.abc import Sequence

DAYS_PER_MONTH = 30.4375


def safe_div(numerator: float, denominator: float, default: float | None = 0.0) -> float | None:
    if denominator is None or denominator == 0 or numerator is None:
        return default
    return numerator / denominator


def median(values: Sequence[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def quantile(values: Sequence[float], q: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def mad(values: Sequence[float]) -> float | None:
    m = median(values)
    if m is None:
        return None
    return median([abs(v - m) for v in values if v is not None])


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> float | None:
    pairs = sorted((v, w) for v, w in zip(values, weights) if v is not None and w > 0)
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2.0:
            return v
    return pairs[-1][0]


def trimmed_mean(values: Sequence[float], fraction: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = int(len(vals) * fraction)
    core = vals[k : len(vals) - k] or vals
    return sum(core) / len(core)


def huber_location(values: Sequence[float], k: float = 1.345, iterations: int = 50) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    mu = median(vals)
    scale = (mad(vals) or 0.0) * 1.4826
    if scale == 0:
        return mu
    for _ in range(iterations):
        weights = []
        for v in vals:
            r = abs(v - mu) / scale
            weights.append(1.0 if r <= k else k / r)
        new_mu = sum(w * v for w, v in zip(weights, vals)) / sum(weights)
        if abs(new_mu - mu) < 1e-9:
            break
        mu = new_mu
    return mu


def mean(values: Sequence[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def stdev(values: Sequence[float]) -> float | None:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def theil_sen_slope(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    slopes = []
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            if xs[j] != xs[i]:
                slopes.append((ys[j] - ys[i]) / (xs[j] - xs[i]))
    return median(slopes)


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def softmax(logits: dict[str, float]) -> dict[str, float]:
    m = max(logits.values())
    exps = {k: math.exp(v - m) for k, v in logits.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


def normalise(probs: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in probs.values())
    if total <= 0:
        n = len(probs)
        return {k: 1.0 / n for k in probs}
    return {k: max(0.0, v) / total for k, v in probs.items()}


def normalised_entropy(probs: dict[str, float]) -> float:
    n = len(probs)
    if n <= 1:
        return 0.0
    h = -sum(p * math.log(p) for p in probs.values() if p > 0)
    return h / math.log(n)


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
