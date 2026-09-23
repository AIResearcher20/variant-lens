"""
Tests for hybrid retrieval via Reciprocal Rank Fusion.
"""

from variant_lens.retrieve.hybrid import rrf_fuse
from variant_lens.schema import Passage


def _make_passage(pmid: str, title: str = "") -> Passage:
    return Passage(pmid=pmid, title=title or f"PMID {pmid}", abstract=None, year=2020)


def test_rrf_fuse_combines_two_lists():
    list_a = [_make_passage("1"), _make_passage("2"), _make_passage("3")]
    list_b = [_make_passage("2"), _make_passage("1"), _make_passage("4")]

    result = rrf_fuse([list_a, list_b], top_k=3)
    pmids = [p.pmid for p in result]
    assert "1" in pmids
    assert "2" in pmids


def test_rrf_fuse_handles_empty_input():
    assert rrf_fuse([], top_k=5) == []
    assert rrf_fuse([[]], top_k=5) == []


def test_rrf_fuse_respects_top_k():
    list_a = [_make_passage(str(i)) for i in range(1, 6)]
    list_b = [_make_passage(str(i)) for i in range(6, 11)]

    result = rrf_fuse([list_a, list_b], top_k=4)
    assert len(result) == 4


def test_rrf_fuse_deduplicates():
    list_a = [_make_passage("1"), _make_passage("2")]
    list_b = [_make_passage("1"), _make_passage("2")]

    result = rrf_fuse([list_a, list_b], top_k=10)
    pmids = [p.pmid for p in result]
    assert len(pmids) == len(set(pmids))
