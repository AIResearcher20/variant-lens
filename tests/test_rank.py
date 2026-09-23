"""
Tests for variant_lens.rank.

Uses in-memory passages. Cross-encoder is attempted but falls back to
retrieval order when the model is unavailable.
"""

from variant_lens.rank import rerank
from variant_lens.schema import Passage


def _make_passage(pmid: str, title: str, abstract: str | None = None) -> Passage:
    return Passage(
        pmid=pmid,
        title=title,
        abstract=abstract,
        year=2020,
    )


def _sample_passages() -> list[Passage]:
    return [
        _make_passage("1", "BRCA1 variant in breast cancer"),
        _make_passage("2", "TP53 variant in lung cancer"),
        _make_passage("3", "BRCA1 and BRCA2 review"),
    ]


def test_rerank_returns_ranked_passages():
    passages = _sample_passages()
    result = rerank("BRCA1", passages, top_k=3)
    assert len(result) == 3
    for entry in result:
        assert entry.rank >= 1
        assert entry.passage.pmid in {"1", "2", "3"}


def test_rerank_respects_top_k():
    passages = _sample_passages()
    result = rerank("BRCA1", passages, top_k=2)
    assert len(result) == 2


def test_rerank_returns_empty_for_empty_corpus():
    result = rerank("BRCA1", [], top_k=5)
    assert result == []


def test_rerank_ranks_are_sequential():
    passages = _sample_passages()
    result = rerank("BRCA1", passages, top_k=3)
    ranks = [entry.rank for entry in result]
    assert ranks == list(range(1, len(result) + 1))


def test_rerank_is_deterministic():
    passages = _sample_passages()
    first = rerank("BRCA1", passages, top_k=3)
    second = rerank("BRCA1", passages, top_k=3)
    assert [e.passage.pmid for e in first] == [e.passage.pmid for e in second]


def test_rerank_handles_empty_query():
    passages = _sample_passages()
    result = rerank("", passages, top_k=3)
    assert len(result) <= 3
