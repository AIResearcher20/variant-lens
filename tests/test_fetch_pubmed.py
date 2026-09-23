"""
Tests for PubMed passage fetching.

Uses monkeypatch to avoid real network calls.
"""

from variant_lens.fetch import fetch_pubmed_passages
from variant_lens.schema import Passage


def _fake_pubmed_response(*args, **kwargs):
    return {
        "result": {
            "uids": ["12345678", "23456789"],
            "12345678": {
                "title": "BRCA1 variant in hereditary breast cancer",
                "abstract": "We describe a pathogenic BRCA1 frameshift variant.",
                "pubdate": "2020",
            },
            "23456789": {
                "title": "BRCA1 and BRCA2 review",
                "abstract": None,
                "pubdate": "2021",
            },
        }
    }


def test_fetch_pubmed_passages_returns_passages(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.fetch._http_get_json",
        _fake_pubmed_response,
    )

    passages = fetch_pubmed_passages("BRCA1", max_results=10)
    assert len(passages) == 2
    assert isinstance(passages[0], Passage)
    assert passages[0].pmid == "12345678"
    assert passages[0].title == "BRCA1 variant in hereditary breast cancer"
    assert passages[0].year == 2020


def test_fetch_pubmed_passages_handles_missing_abstract(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.fetch._http_get_json",
        _fake_pubmed_response,
    )

    passages = fetch_pubmed_passages("BRCA1", max_results=10)
    second = passages[1]
    assert second.pmid == "23456789"
    assert second.abstract is None


def test_fetch_pubmed_passages_handles_empty_result(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.fetch._http_get_json",
        lambda *args, **kwargs: {"result": {"uids": []}},
    )

    passages = fetch_pubmed_passages("BRCA1", max_results=10)
    assert passages == []
