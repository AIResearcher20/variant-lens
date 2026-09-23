"""
Hybrid retrieval.

Combines ranked lists from multiple strategies via Reciprocal Rank Fusion.
"""

from __future__ import annotations

from ..schema import Passage


_DEFAULT_RRF_K = 60


def rrf_fuse(
    ranked_lists: list[list[Passage]],
    top_k: int,
    k: int = _DEFAULT_RRF_K,
) -> list[Passage]:
    """
    Fuse multiple ranked lists into one using Reciprocal Rank Fusion.

    RRF score for a passage is the sum of 1/(k + rank) over all lists it
    appears in. The parameter k smooths the contribution of high ranks.
    """
    scores: dict[str, float] = {}
    passages_by_id: dict[str, Passage] = {}

    for ranked in ranked_lists:
        for rank, passage in enumerate(ranked, start=1):
            scores[passage.pmid] = scores.get(passage.pmid, 0.0) + 1.0 / (k + rank)
            passages_by_id.setdefault(passage.pmid, passage)

    ordered = sorted(
        scores.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )

    return [passages_by_id[pmid] for pmid, _ in ordered[:top_k]]
