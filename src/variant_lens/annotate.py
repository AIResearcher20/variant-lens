"""
Annotation.

Merges the output of parse, scope, and fetch into an AnnotationResult.
Does not contact external APIs.
"""

from __future__ import annotations

from .parse import parse_variant
from .schema import (
    AnnotationResult,
    EvidenceAvailability,
    EvidenceState,
    ParsedVariant,
    RawEvidence,
    ValidationResult,
)
from .scope import determine_scope
from .config import AF_THRESHOLD


class AnnotationError(Exception):
    """Raised when the input cannot be annotated."""


def annotate(
    parsed: ParsedVariant,
    evidence: list[RawEvidence],
) -> AnnotationResult:
    """
    Merge parse, scope, and fetch outputs into an AnnotationResult.

    Raises AnnotationError if the input is not parseable or not supported.
    """
    if not parsed.is_parseable:
        raise AnnotationError(
            f"Input is not parseable: {parsed.input_variant!r}"
        )

    if not parsed.is_supported:
        raise AnnotationError(
            f"Variant type is not supported: {parsed.variant_type.value}"
        )

    scope_status, af_status = determine_scope(parsed, evidence)
    evidence_state = _determine_evidence_state(evidence)
    evidence_availability = _determine_evidence_availability(evidence)

    validation = ValidationResult(
        parsed=parsed,
        scope_status=scope_status,
        af_status=af_status,
        allele_frequency=_extract_gnomad_af(evidence),
        evidence_availability=evidence_availability,
        warnings=list(parsed.warnings),
        provenance={},
    )

    return AnnotationResult(
        validation=validation,
        evidence_state=evidence_state,
        gene=parsed.gene,
        hgvs_c=_extract_clinvar_field(evidence, "hgvs_c"),
        hgvs_p=_extract_clinvar_field(evidence, "hgvs_p"),
        clinvar_significance=_extract_clinvar_field(evidence, "clinvar_significance"),
        clinvar_review_status=_extract_clinvar_field(evidence, "clinvar_review_status"),
        clinvar_variation_id=_extract_clinvar_field(evidence, "clinvar_variation_id"),
        phenotype=_extract_clinvar_field(evidence, "phenotype"),
        gnomad_af=_extract_gnomad_af(evidence),
        raw_evidence=evidence,
    )


def _determine_evidence_state(evidence: list[RawEvidence]) -> EvidenceState:
    """Determine the fetch-layer state from the evidence list."""
    if not evidence:
        return EvidenceState.UNAVAILABLE

    with_payload = [e for e in evidence if e.payload is not None]

    if len(with_payload) == len(evidence):
        return EvidenceState.COMPLETE

    if len(with_payload) == 0:
        return EvidenceState.UNAVAILABLE

    return EvidenceState.PARTIAL


def _determine_evidence_availability(
    evidence: list[RawEvidence],
) -> EvidenceAvailability:
    """Determine the domain-level availability of evidence fields."""
    has_af = _extract_gnomad_af(evidence) is not None
    has_clinvar = _extract_clinvar_field(evidence, "clinvar_significance") is not None
    has_phenotype = _extract_clinvar_field(evidence, "phenotype") is not None

    available = sum([has_af, has_clinvar, has_phenotype])

    if available == 3:
        return EvidenceAvailability.FULL
    if available >= 1:
        return EvidenceAvailability.PARTIAL
    return EvidenceAvailability.MINIMAL


def _extract_gnomad_af(evidence: list[RawEvidence]) -> float | None:
    """Extract gnomAD allele frequency."""
    gnomad = _find_source(evidence, "gnomad")
    if gnomad is None or gnomad.payload is None:
        return None

    af = gnomad.payload.get("af")
    if af is None:
        return None

    try:
        return float(af)
    except (TypeError, ValueError):
        return None


def _extract_clinvar_field(
    evidence: list[RawEvidence],
    field: str,
) -> str | None:
    """Extract a ClinVar field from the evidence list."""
    clinvar = _find_source(evidence, "clinvar")
    if clinvar is None or clinvar.payload is None:
        return None

    value = clinvar.payload.get(field)
    if value is None:
        return None

    return str(value)


def _find_source(
    evidence: list[RawEvidence],
    source: str,
) -> RawEvidence | None:
    """Return the first evidence entry matching the given source name."""
    for entry in evidence:
        if entry.source == source:
            return entry
    return None
