"""
Tests for variant_lens.annotate.

Written before the implementation.
"""

import pytest

from variant_lens.annotate import AnnotationError, annotate
from variant_lens.parse import parse_variant
from variant_lens.schema import (
    EvidenceState,
    RawEvidence,
)


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
        _make_evidence("pubmed", {"count": 12, "pmids": ["12345", "67890"]}),
    ]


def test_annotate_with_full_evidence():
    parsed = parse_variant("BRCA1 c.68_69delAG")
    evidence = _full_evidence()
    result = annotate(parsed, evidence)

    assert result.evidence_state == EvidenceState.COMPLETE
    assert result.gene == "BRCA1"
    assert result.hgvs_c == "c.68_69delAG"
    assert result.hgvs_p == "p.Glu23ValfsTer17"
    assert result.clinvar_significance == "Pathogenic"
    assert result.phenotype == "Hereditary breast cancer"
    assert result.gnomad_af == 0.0001


def test_annotate_with_partial_evidence():
    parsed = parse_variant("BRCA1 c.68_69delAG")
    evidence = [
        _make_evidence("gnomad", {"af": 0.0001}),
        _make_evidence("clinvar", None),
        _make_evidence("pubmed", {"count": 0, "pmids": []}),
    ]
    result = annotate(parsed, evidence)

    assert result.evidence_state == EvidenceState.PARTIAL
    assert result.gnomad_af == 0.0001
    assert result.clinvar_significance is None


def test_annotate_with_no_evidence():
    parsed = parse_variant("BRCA1 c.68_69delAG")
    evidence = [
        _make_evidence("gnomad", None),
        _make_evidence("clinvar", None),
        _make_evidence("pubmed", None),
    ]
    result = annotate(parsed, evidence)

    assert result.evidence_state == EvidenceState.UNAVAILABLE


def test_annotate_raises_on_unparseable():
    parsed = parse_variant("not-a-variant")
    with pytest.raises(AnnotationError):
        annotate(parsed, [])


def test_annotate_raises_on_unsupported_type():
    parsed = parse_variant("chr17:43000000:100:200")
    with pytest.raises(AnnotationError):
        annotate(parsed, [])
