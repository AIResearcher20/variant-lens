"""
Tests for PubMed passage fetching.

Mocks the low-level search and summary functions directly.
"""

from variant_lens.fetch import fetch_pubmed_passages
from variant_lens.schema import Passage


_SEARCH_RESULT = ["12345678", "23456789"]

_SUMMARY_RECORDS = [
    {
        "pmid": "12345678",
        "title": "BRCA1 variant in hereditary breast cancer",
        "abstract": "We describe a pathogenic BRCA1 frameshift variant.",
        "pubdate": "2020",
    },
    {
        "pmid": "23456789",
        "title": "BRCA1 and BRCA2 review",
        "abstract": None,
        "pubdate": "2021",
    },
]


def test_fetch_pubmed_passages_returns_passages(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.fetch._pubmed_search",
        lambda query, max_results: _SEARCH_RESULT,
    )
    monkeypatch.setattr(
        "variant_lens.fetch._pubmed_summary",
        lambda pmids: _SUMMARY_RECORDS,
    )

    passages = fetch_pubmed_passages("BRCA1", max_results=10)
    assert len(passages) == 2
    assert isinstance(passages[0], Passage)
    assert passages[0].pmid == "12345678"
    assert passages[0].title == "BRCA1 variant in hereditary breast cancer"
    assert passages[0].year == 2020


def test_fetch_pubmed_passages_handles_missing_abstract(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.fetch._pubmed_search",
        lambda query, max_results: _SEARCH_RESULT,
    )
    monkeypatch.setattr(
        "variant_lens.fetch._pubmed_summary",
        lambda pmids: _SUMMARY_RECORDS,
    )

    passages = fetch_pubmed_passages("BRCA1", max_results=10)
    assert passages[1].pmid == "23456789"
    assert passages[1].abstract is None


def test_fetch_pubmed_passages_handles_empty_result(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.fetch._pubmed_search",
        lambda query, max_results: [],
    )

    passages = fetch_pubmed_passages("BRCA1", max_results=10)
    assert passages == []
