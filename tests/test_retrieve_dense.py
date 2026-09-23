"""
Tests for dense retrieval.

The embedder is mocked so no model download is required.
"""

from variant_lens.retrieve.dense import dense_retrieve
from variant_lens.schema import Passage


def _make_passage(pmid: str, title: str) -> Passage:
    return Passage(pmid=pmid, title=title, abstract=None, year=2020)


def _fake_embedder(texts: list[str]) -> list[list[float]]:
    """
    Deterministic embedder for tests.

    Maps any text containing 'BRCA1' to a vector close to [1.0, 0.0] and
    other texts to [0.0, 1.0].
    """
    vectors: list[list[float]] = []
    for text in texts:
        if "BRCA1" in text:
            vectors.append([1.0, 0.0])
        else:
            vectors.append([0.0, 1.0])
    return vectors


def test_dense_retrieve_returns_brca1_first(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.retrieve.dense._embed",
        _fake_embedder,
    )

    passages = [
        _make_passage("1", "BRCA1 in breast cancer"),
        _make_passage("2", "TP53 in lung cancer"),
    ]

    result = dense_retrieve("BRCA1", passages, top_k=2)
    assert len(result) >= 1
    assert result[0].pmid == "1"


def test_dense_retrieve_returns_empty_for_empty_corpus(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.retrieve.dense._embed",
        _fake_embedder,
    )

    result = dense_retrieve("BRCA1", [], top_k=5)
    assert result == []


def test_dense_retrieve_returns_empty_for_empty_query(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.retrieve.dense._embed",
        _fake_embedder,
    )

    passages = [_make_passage("1", "BRCA1 in breast cancer")]
    result = dense_retrieve("", passages, top_k=2)
    assert result == []


def test_dense_retrieve_respects_top_k(monkeypatch):
    monkeypatch.setattr(
        "variant_lens.retrieve.dense._embed",
        _fake_embedder,
    )

    passages = [
        _make_passage("1", "BRCA1 in breast cancer"),
        _make_passage("2", "BRCA1 review"),
        _make_passage("3", "BRCA1 cohort study"),
    ]

    result = dense_retrieve("BRCA1", passages, top_k=2)
    assert len(result) <= 2
