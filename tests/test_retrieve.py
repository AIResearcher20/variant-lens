"""
Tests for variant_lens.retrieve.

Uses in-memory passages. No network, no external index.
"""

import pytest

from variant_lens.retrieve import retrieve
from variant_lens.retrieve.bm25 import bm25_retrieve
from variant_lens.schema import Passage, RetrievalStrategy


def _make_passage(pmid: str, title: str, abstract: str | None = None) -> Passage:
    return Passage(
        pmid=pmid,
        title=title,
        abstract=abstract,
        year=2020,
    )


def _sample_passages() -> list[Passage]:
    return [
        _make_passage(
            "1",
            "BRCA1 c.68_69delAG in hereditary breast cancer",
            "We describe a pathogenic BRCA1 frameshift variant.",
        ),
        _make_passage(
            "2",
            "TP53 mutations in lung cancer",
            "A study of TP53 variants in lung adenocarcinoma.",
        ),
        _make_passage(
            "3",
            "BRCA1 and BRCA2 in ovarian cancer",
            "Review of BRCA1 and BRCA2 germline variants.",
        ),
        _make_passage(
            "4",
            "Unrelated study on protein folding",
            "Structural biology of a model protein.",
        ),
    ]


def test_bm25_returns_brca1_passages_first():
    passages = _sample_passages()
    result = bm25_retrieve("BRCA1 c.68_69delAG", passages, top_k=3)
    pmids = [p.pmid for p in result]
    assert "1" in pmids
    assert "3" in pmids


def test_bm25_excludes_unrelated_passage():
    passages = _sample_passages()
    result = bm25_retrieve("BRCA1 c.68_69delAG", passages, top_k=4)
    pmids = [p.pmid for p in result]
    assert "4" not in pmids


def test_bm25_returns_empty_for_empty_corpus():
    result = bm25_retrieve("BRCA1", [], top_k=5)
    assert result == []


def test_bm25_returns_empty_for_empty_query():
    passages = _sample_passages()
    result = bm25_retrieve("", passages, top_k=3)
    assert result == []


def test_bm25_respects_top_k():
    passages = _sample_passages()
    result = bm25_retrieve("BRCA1 cancer variant", passages, top_k=2)
    assert len(result) <= 2


def test_retrieve_dispatches_to_bm25():
    passages = _sample_passages()
    result = retrieve(
        query="BRCA1",
        passages=passages,
        strategy=RetrievalStrategy.BM25,
        top_k=2,
    )
    assert len(result) <= 2


def test_retrieve_raises_on_unimplemented_strategy():
    passages = _sample_passages()
    with pytest.raises(NotImplementedError):
        retrieve(
            query="BRCA1",
            passages=passages,
            strategy=RetrievalStrategy.DENSE,
            top_k=2,
        )
