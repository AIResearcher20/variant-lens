"""
Scope determination.

Takes a ParsedVariant and a list of RawEvidence, returns ScopeStatus and
AfStatus. No network access.
"""

from __future__ import annotations

from .config import AF_THRESHOLD
from .schema import AfStatus, ParsedVariant, RawEvidence, ScopeStatus


def determine_scope(
    parsed: ParsedVariant,
    evidence: list[RawEvidence],
) -> tuple[ScopeStatus, AfStatus]:
    """
    Determine scope status and allele frequency status.

    Returns (ScopeStatus, AfStatus). Never raises.
    """
    if not parsed.is_parseable:
        return ScopeStatus.UNCERTAIN, AfStatus.SOURCE_UNAVAILABLE

    af_status = _determine_af_status(evidence)

    if not parsed.is_supported:
        return ScopeStatus.OUT_OF_SCOPE_TYPE, af_status

    if af_status == AfStatus.SOURCE_UNAVAILABLE:
        return ScopeStatus.UNCERTAIN, af_status

    if af_status == AfStatus.NOT_IN_GNOMAD:
        return ScopeStatus.IN_SCOPE, af_status

    af_value = _extract_af(evidence)
    if af_value is None:
        return ScopeStatus.UNCERTAIN, AfStatus.SOURCE_UNAVAILABLE

    if af_value < AF_THRESHOLD:
        return ScopeStatus.IN_SCOPE, af_status

    return ScopeStatus.OUT_OF_SCOPE_COMMON, af_status


def _determine_af_status(evidence: list[RawEvidence]) -> AfStatus:
    """Determine AfStatus from the gnomAD evidence entry."""
    gnomad = _find_source(evidence, "gnomad")
    if gnomad is None:
        return AfStatus.SOURCE_UNAVAILABLE

    if gnomad.payload is None:
        return AfStatus.SOURCE_UNAVAILABLE

    if "af" not in gnomad.payload:
        return AfStatus.SOURCE_UNAVAILABLE

    if gnomad.payload["af"] is None:
        return AfStatus.NOT_IN_GNOMAD

    return AfStatus.KNOWN


def _extract_af(evidence: list[RawEvidence]) -> float | None:
    """Extract the allele frequency value from gnomAD evidence."""
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


def _find_source(
    evidence: list[RawEvidence],
    source: str,
) -> RawEvidence | None:
    """Return the first evidence entry matching the given source name."""
    for entry in evidence:
        if entry.source == source:
            return entry
    return None
