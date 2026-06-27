"""Small starter taxonomy for pilot normalization.

This is intentionally conservative. Real AIHub profiling should expand it.
"""

from __future__ import annotations

from .ids import normalize_term


ALIASES: dict[str, dict[str, str]] = {
    "SkinConcern": {
        "여드름": "acne",
        "트러블": "acne",
        "홍조": "redness",
        "붉은기": "redness",
        "건조": "dryness",
        "색소침착": "pigmentation",
        "모공": "pores",
        "민감": "sensitivity",
    },
    "SkinType": {
        "건성": "dry",
        "지성": "oily",
        "복합성": "combination",
        "중성": "normal",
        "민감성": "sensitive",
    },
    "Effect": {
        "보습": "moisturizing",
        "진정": "soothing",
        "피지 조절": "sebum_control",
        "장벽": "barrier_support",
        "각질": "exfoliation",
        "브라이트닝": "brightening",
    },
    "Caution": {
        "자극": "irritation",
        "광민감": "photosensitivity",
        "과각질": "over_exfoliation",
        "여드름 악화": "acne_aggravation",
    },
}


def normalize_alias(label: str, value: str) -> str:
    term = normalize_term(value)
    alias_map = ALIASES.get(label, {})
    return alias_map.get(term, term.replace(" ", "_"))

