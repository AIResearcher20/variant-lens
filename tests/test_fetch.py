"""
Tests for variant_lens.fetch.

Uses monkeypatch to avoid real network calls. Written before the
implementation.
"""

from variant_lens.fetch import get_raw_evidence
from variant_lens.schema import RawEvidence


def test_returns_empty_evidence_on_all_sources_down(monkeypatch):
    def fake_get(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr("variant_lens.fetch._http_get_json", fake_get)

    evidence = get_raw_evidence("TP53 c.743G>A")
    assert isinstance(evidence, list)
    for entry in evidence:
        assert isinstance(entry, RawEvidence)
        assert entry.payload is None


def test_successful_gnomad_response(monkeypatch):
    def fake_get(url, params=None, timeout=10):
        return {"af": 0.0001}

    monkeypatch.setattr("variant_lens.fetch._http_get_json", fake_get)

    evidence = get_raw_evidence("TP53 c.743G>A")
    gnomad_entries = [e for e in evidence if e.source == "gnomad"]
    assert len(gnomad_entries) == 1
    assert gnomad_entries[0].payload == {"af": 0.0001}


def test_response_hash_is_set(monkeypatch):
    def fake_get(url, params=None, timeout=10):
        return {"af": 0.0001}

    monkeypatch.setattr("variant_lens.fetch._http_get_json", fake_get)

    evidence = get_raw_evidence("TP53 c.743G>A")
    for entry in evidence:
        assert entry.response_hash
        assert len(entry.response_hash) == 64
