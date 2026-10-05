"""Section 5.2 / F005 - Character-level narration embedding (hashed character trigrams).

A deterministic, dependency-free encoder. A trained subword/transformer encoder can replace it
behind the same function signature.
"""

from __future__ import annotations

import hashlib
import math
import re

EMBEDDING_DIM = 256


def _bucket(gram: str) -> int:
    return int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16) % EMBEDDING_DIM


def encode_narration(normalized_narration: str | None) -> dict[int, float]:
    if not normalized_narration:
        return {}
    text = re.sub(r"\d", "#", normalized_narration)
    text = f"  {text}  "
    vec: dict[int, float] = {}
    for i in range(len(text) - 2):
        b = _bucket(text[i:i + 3])
        vec[b] = vec.get(b, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {k: v / norm for k, v in vec.items()}


def cosine_similarity(a: dict[int, float], b: dict[int, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())
