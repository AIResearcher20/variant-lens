"""
Retrieval interface.

Exposes a single entry point that dispatches to the configured strategy.
"""

from __future__ import annotations

from ..schema import Passage, RetrievalStrategy
from .bm25 import bm25_retrieve


def retrieve(
    query: str,
    passages: list[Passage],
    strategy: RetrievalStrategy,
    top_k: int,
) -> list[Passage]:
    """
    Retrieve the top-k passages for a query.

    Only BM25 is implemented in the MVP. Dense and hybrid strategies are
    planned for Phase 2.
    """
    if strategy == RetrievalStrategy.BM25:
        return bm25_retrieve(query, passages, top_k)

    raise NotImplementedError(
        f"Retrieval strategy {strategy.value} is not implemented yet."
    )
