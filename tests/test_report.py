"""
Tests for variant_lens.report.

Uses in-memory annotation and ranked passages. No network.
"""

import json

from variant_lens.annotate import annotate
from variant_lens.parse import parse_variant
from variant_lens.rank import rerank
from variant_lens.report import generate, to_json
from variant_lens.schema import Passage, RawEvidence


def _make_evidence(source: str, payload: dict | None) -> RawEvidence:
    return RawEvidence(
        source=source,
        version=None,
        query="test",
        retrieved_at="2026-01-01T00:00:00Z",
        endpoint=f"https://example.org/{source}",
        response_hash="0" * 64,
        payload=payload,
    )


def _full_evidence() -> list[RawEvidence]:
    return [
        _make_evidence("gnomad", {"af": 0.0001}),
        _make_evidence(
            "clinvar",
            {
                "clinvar_significance": "Pathogenic",
                "clinvar_review_status": "criteria provided, multiple submitters",
                "clinvar_variation_id": "12345",
                "phenotype": "Hereditary breast cancer",
                "hgvs_c": "c.68_69delAG",
                "hgvs_p": "p.Glu23ValfsTer17",
                "gene": "BRCA1",
            },
        ),
        _make_evidence("pubmed", {"count": 2, "pmids": ["1", "2"]}),
    ]


def _sample_passages() -> list[Passage]:
    return [
        Passage(pmid="1", title="BRCA1 variant", abstract=None, year=2020),
        Passage(pmid="2", title="BRCA2 variant", abstract=None, year=2021),
    ]


def _build_annotation():
    parsed = parse_variant("BRCA1 c.68_69delAG")
    evidence = _full_evidence()
    return annotate(parsed, evidence)


def test_report_has_expected_fields():
    annotation = _build_annotation()
    ranked = rerank("BRCA1", _sample_passages(), top_k=2)
    report = generate(annotation, ranked)

    assert "variant" in report
    assert "evidence" in report
    assert "passages" in report
    assert report["variant"]["gene"] == "BRCA1"


def test_to_json_produces_valid_json():
    annotation = _build_annotation()
    ranked = rerank("BRCA1", _sample_passages(), top_k=2)
    report = generate(annotation, ranked)
    text = to_json(report)
    parsed = json.loads(text)
    assert parsed["variant"]["gene"] == "BRCA1"


def test_report_handles_empty_passages():
    annotation = _build_annotation()
    report = generate(annotation, [])
    assert report["passages"] == []


def test_report_serializes_to_dict():
    annotation = _build_annotation()
    report = generate(annotation, [])
    assert isinstance(report, dict)
