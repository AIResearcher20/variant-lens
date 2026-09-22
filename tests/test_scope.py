"""
Tests for variant_lens.scope.

Written before the implementation. Each test states one contract claim.
"""

from variant_lens.parse import parse_variant
from variant_lens.scope import determine_scope
from variant_lens.schema import (
    AfStatus,
    RawEvidence,
    ScopeStatus,
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


def test_af_below_threshold_is_in_scope():
    parsed = parse_variant("TP53 c.743G>A")
    evidence = [_make_evidence("gnomad", {"af": 0.0001})]
    scope, af = determine_scope(parsed, evidence)
    assert scope == ScopeStatus.IN_SCOPE
    assert af == AfStatus.KNOWN


def test_af_above_threshold_is_out_of_scope_common():
    parsed = parse_variant("TP53 c.743G>A")
    evidence = [_make_evidence("gnomad", {"af": 0.05})]
    scope, af = determine_scope(parsed, evidence)
    assert scope == ScopeStatus.OUT_OF_SCOPE_COMMON
    assert af == AfStatus.KNOWN


def test_af_equal_to_threshold_is_out_of_scope_common():
    parsed = parse_variant("TP53 c.743G>A")
    evidence = [_make_evidence("gnomad", {"af": 0.001})]
    scope, af = determine_scope(parsed, evidence)
    assert scope == ScopeStatus.OUT_OF_SCOPE_COMMON
    assert af == AfStatus.KNOWN


def test_no_gnomad_record_is_in_scope_not_in_gnomad():
    parsed = parse_variant("TP53 c.743G>A")
    evidence = [_make_evidence("gnomad", {"af": None})]
    scope, af = determine_scope(parsed, evidence)
    assert scope == ScopeStatus.IN_SCOPE
    assert af == AfStatus.NOT_IN_GNOMAD


def test_gnomad_unavailable_is_uncertain():
    parsed = parse_variant("TP53 c.743G>A")
    evidence = [_make_evidence("gnomad", None)]
    scope, af = determine_scope(parsed, evidence)
    assert scope == ScopeStatus.UNCERTAIN
    assert af == AfStatus.SOURCE_UNAVAILABLE


def test_unparseable_input_is_uncertain():
    parsed = parse_variant("not-a-variant")
    evidence = []
    scope, af = determine_scope(parsed, evidence)
    assert scope == ScopeStatus.UNCERTAIN
    assert af == AfStatus.SOURCE_UNAVAILABLE


def test_determine_scope_is_deterministic():
    parsed = parse_variant("TP53 c.743G>A")
    evidence = [_make_evidence("gnomad", {"af": 0.0001})]
    first = determine_scope(parsed, evidence)
    second = determine_scope(parsed, evidence)
    assert first == second
