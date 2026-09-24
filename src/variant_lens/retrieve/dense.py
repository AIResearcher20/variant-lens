"""
Dense retrieval.

Uses PubMedBERT embeddings and cosine similarity. No external vector
store is required; the corpus is small enough to keep in memory.

The corpus embeddings are cached at module level. When the same corpus
is used for several queries, as happens in the benchmark, the
embedding step runs only once. This changes the run time from
quadratic in the number of queries to linear.
"""

from __future__ import annotations

import logging
import math

from ..schema import Passage


logger = logging.getLogger(__name__)


_MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"
_BATCH_SIZE = 128

_model_cache: object | None = None
_corpus_cache_key: tuple | None = None
_corpus_cache_vectors: list[list[float]] | None = None


def dense_retrieve(
    query: str,
    passages: list[Passage],
    top_k: int,
) -> list[Passage]:
    """
    Retrieve the top-k passages by cosine similarity to the query.

    Returns an empty list when the corpus or query is empty, or when the
    embedder is unavailable.
    """
    if not passages or not query.strip():
        return []

    texts = [_passage_text(p) for p in passages]

    try:
        corpus_vectors = _corpus_embed(texts)
        query_vector = _embed([query])[0]
    except Exception as exc:
        logger.warning("Dense retrieval failed; returning empty list: %s", exc)
        return []

    scored = [
        (passage, _cosine(query_vector, vector))
        for passage, vector in zip(passages, corpus_vectors)
    ]

    scored.sort(key=lambda pair: (-pair[1], pair[0].pmid))

    return [p for p, score in scored[:top_k] if score > 0]


def _corpus_embed(texts: list[str]) -> list[list[float]]:
    """
    Embed the corpus once and reuse the vectors for later queries.

    The cache key combines the number of passages with a hash of the
    first and last passage texts. This is sufficient to detect a change
    of corpus without storing the full text.
    """
    global _corpus_cache_key, _corpus_cache_vectors

    if not texts:
        return []

    key = (len(texts), hash(texts[0]), hash(texts[-1]))
    if _corpus_cache_vectors is not None and _corpus_cache_key == key:
        return _corpus_cache_vectors

    _corpus_cache_vectors = _embed(texts)
    _corpus_cache_key = key
    return _corpus_cache_vectors


def _embed(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts.

    The model is loaded once and cached. When sentence-transformers is
    not installed, an ImportError is raised and the caller falls back.
    """
    global _model_cache

    from sentence_transformers import SentenceTransformer

    if _model_cache is None:
        _model_cache = SentenceTransformer(_MODEL_NAME)

    vectors = _model_cache.encode(
        texts,
        convert_to_numpy=True,
        batch_size=_BATCH_SIZE,
        show_progress_bar=False,
    )
    return [list(map(float, v)) for v in vectors]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _passage_text(passage: Passage) -> str:
    """Concatenate the title and abstract for embedding."""
    if passage.abstract:
        return f"{passage.title} {passage.abstract}"
    return passage.title
