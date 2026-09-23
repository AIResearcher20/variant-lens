"""
Retrieval interface.

Dispatches to the configured strategy. Dense and hybrid are optional and
may fail if their dependencies are not installed.
"""

from __future__ import annotations

import logging

from ..schema import Passage, RetrievalStrategy
from .bm25 import bm25_retrieve
from .hybrid import rrf_fuse


logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    passages: list[Passage],
    strategy: RetrievalStrategy,
    top_k: int,
) -> list[Passage]:
    """
    Retrieve the top-k passages for a query.

    BM25 is always available. Dense and hybrid require
    sentence-transformers. When the dense backend is unavailable, hybrid
    falls back to BM25.
    """
    if strategy == RetrievalStrategy.BM25:
        return bm25_retrieve(query, passages, top_k)

    if strategy == RetrievalStrategy.DENSE:
        return _dense_or_empty(query, passages, top_k)

    if strategy == RetrievalStrategy.HYBRID:
        return _hybrid(query, passages, top_k)

    raise NotImplementedError(
        f"Retrieval strategy {strategy.value} is not implemented."
    )


def _dense_or_empty(
    query: str,
    passages: list[Passage],
    top_k: int,
) -> list[Passage]:
    try:
        from .dense import dense_retrieve
    except ImportError:
        logger.info("Dense retrieval is not available.")
        return []
    return dense_retrieve(query, passages, top_k)


def _hybrid(
    query: str,
    passages: list[Passage],
    top_k: int,
) -> list[Passage]:
    bm25_results = bm25_retrieve(query, passages, top_k)
    dense_results = _dense_or_empty(query, passages, top_k)

    if not dense_results:
        return bm25_results

    return rrf_fuse([bm25_results, dense_results], top_k=top_k)
