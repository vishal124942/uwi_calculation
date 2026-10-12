"""Section 7.3 - Probability calibration.

Temperature scaling per direction. The default artifact (T=1.0) is the identity; ``fit_temperature``
fits T on held-out adjudicated labels. Reliability and Brier diagnostics support Section 27.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from se_income_engine.common.stats import normalise
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.versions import COMPONENT_VERSIONS


@dataclass(frozen=True)
class CalibrationArtifact:
    artifact_id: str
    temperature_credit: float = 1.0
    temperature_debit: float = 1.0


def _scale(probs: dict[str, float], temperature: float) -> dict[str, float]:
    if temperature == 1.0:
        return dict(probs)
    return normalise({r: (max(p, 1e-12) ** (1.0 / temperature)) for r, p in probs.items()})


def probability_calibrator(predictions: dict[str, RolePrediction], artifact: CalibrationArtifact) -> dict[str, RolePrediction]:
    for pred in predictions.values():
        is_credit = next(iter(pred.role_probabilities)).startswith("C")
        t = artifact.temperature_credit if is_credit else artifact.temperature_debit
        pred.final_probabilities = _scale(pred.role_probabilities, t)
    return predictions


def default_calibration_artifact(temperature_credit: float = 1.0, temperature_debit: float = 1.0) -> CalibrationArtifact:
    return CalibrationArtifact(COMPONENT_VERSIONS["probability_calibrator"], temperature_credit, temperature_debit)


def log_loss(prob_rows: list[dict[str, float]], labels: list[str]) -> float:
    return -sum(math.log(max(row.get(y, 0.0), 1e-12)) for row, y in zip(prob_rows, labels)) / max(1, len(labels))


def brier_score(prob_rows: list[dict[str, float]], labels: list[str]) -> float:
    total = 0.0
    for row, y in zip(prob_rows, labels):
        total += sum((p - (1.0 if r == y else 0.0)) ** 2 for r, p in row.items())
    return total / max(1, len(labels))


def fit_temperature(prob_rows: list[dict[str, float]], labels: list[str]) -> float:
    grid = [0.5 + 0.05 * i for i in range(51)]
    return min(grid, key=lambda t: log_loss([_scale(r, t) for r in prob_rows], labels))


def reliability_curve(prob_rows: list[dict[str, float]], labels: list[str], bins: int = 10) -> list[dict[str, float]]:
    buckets = [[0, 0.0, 0] for _ in range(bins)]
    for row, y in zip(prob_rows, labels):
        top = max(row, key=row.get)
        b = min(bins - 1, int(row[top] * bins))
        buckets[b][0] += 1
        buckets[b][1] += row[top]
        buckets[b][2] += int(top == y)
    return [
        {"bin": i, "count": n, "mean_confidence": s / n, "accuracy": c / n}
        for i, (n, s, c) in enumerate(buckets) if n
    ]
