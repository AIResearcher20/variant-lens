"""
Reranking.

Reranks passages with a cross-encoder when one is available. Falls back
to the input order when the model cannot be loaded, so the pipeline
continues in offline or restricted environments.
"""

from __future__ import annotations

import logging

from .config import RERANK_TOP_K
from .schema import Passage, RankedPassage


logger = logging.getLogger(__name__)


_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def rerank(
    query: str,
    passages: list[Passage],
    top_k: int = RERANK_TOP_K,
) -> list[RankedPassage]:
    """
    Rerank passages for a query.

    Returns a list of RankedPassage with rank starting at 1. Ties are
    broken by PMID. Falls back to the input order when no cross-encoder
    is available.
    """
    if not passages:
        return []

    order = _cross_encoder_order(query, passages)

    if order is None:
        order = _fallback_order(passages)

    ranked = order[:top_k]

    return [
        RankedPassage(
            passage=passages[i],
            retrieval_score=None,
            rerank_score=None,
            rank=rank,
        )
        for rank, i in enumerate(ranked, start=1)
    ]


def _cross_encoder_order(
    query: str,
    passages: list[Passage],
) -> list[int] | None:
    """Return indices of passages sorted by cross-encoder score, or None."""
    if not query.strip():
        return None

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.info("sentence-transformers is not installed; using fallback order.")
        return None

    try:
        model = CrossEncoder(_CROSS_ENCODER_MODEL)
        pairs = [(query, _passage_text(p)) for p in passages]
        scores = model.predict(pairs)
    except Exception as exc:
        logger.warning("Cross-encoder failed; using fallback order: %s", exc)
        return None

    indexed = list(enumerate(scores))
    indexed.sort(key=lambda pair: (-pair[1], passages[pair[0]].pmid))

    return [i for i, _ in indexed]


def _fallback_order(passages: list[Passage]) -> list[int]:
    """Return passage indices in input order, with PMID as tiebreaker."""
    indexed = list(enumerate(passages))
    indexed.sort(key=lambda pair: pair[1].pmid)
    return [i for i, _ in indexed]


def _passage_text(passage: Passage) -> str:
    """Concatenate the title and abstract for scoring."""
    if passage.abstract:
        return f"{passage.title} {passage.abstract}"
    return passage.title
