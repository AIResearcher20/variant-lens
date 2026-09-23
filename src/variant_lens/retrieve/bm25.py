"""
BM25 retrieval.

Keyword search over passage titles and abstracts. No model, no network.
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from ..schema import Passage


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def bm25_retrieve(
    query: str,
    passages: list[Passage],
    top_k: int,
) -> list[Passage]:
    """
    Retrieve the top-k passages by BM25 score.

    Returns an empty list when there are no passages or no matches.
    """
    if not passages:
        return []

    corpus = [_tokenize(_passage_text(p)) for p in passages]

    if not any(corpus):
        return []

    bm25 = BM25Okapi(corpus)
    query_tokens = _tokenize(query)

    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        zip(passages, scores),
        key=lambda pair: pair[1],
        reverse=True,
    )

    return [p for p, score in ranked[:top_k] if score > 0]


def _tokenize(text: str) -> list[str]:
    """Lowercase and split text into alphanumeric tokens."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _passage_text(passage: Passage) -> str:
    """Concatenate the title and abstract for indexing."""
    if passage.abstract:
        return f"{passage.title} {passage.abstract}"
    return passage.title
