"""
Report generation.

Builds a JSON-serializable report from an AnnotationResult and a list of
RankedPassage. HTML rendering is planned for a later phase.
"""

from __future__ import annotations

import json
from typing import Any

from .schema import AnnotationResult, RankedPassage


def generate(
    annotation: AnnotationResult,
    ranked_passages: list[RankedPassage],
) -> dict[str, Any]:
    """
    Build a JSON-serializable report.

    Returns a dict with three top-level keys: variant, evidence, passages.
    """
    return {
        "variant": _variant_section(annotation),
        "evidence": _evidence_section(annotation),
        "passages": _passages_section(ranked_passages),
    }


def to_json(report: dict[str, Any], indent: int = 2) -> str:
    """Serialize a report dict to JSON."""
    return json.dumps(report, indent=indent, sort_keys=True)


def _variant_section(annotation: AnnotationResult) -> dict[str, Any]:
    parsed = annotation.validation.parsed
    return {
        "input": parsed.input_variant,
        "normalized_hgvs": parsed.normalized_hgvs,
        "gene": annotation.gene,
        "variant_type": parsed.variant_type.value,
        "is_parseable": parsed.is_parseable,
        "is_supported": parsed.is_supported,
    }


def _evidence_section(annotation: AnnotationResult) -> dict[str, Any]:
    validation = annotation.validation
    return {
        "scope_status": validation.scope_status.value,
        "af_status": validation.af_status.value,
        "allele_frequency": validation.allele_frequency,
        "evidence_state": annotation.evidence_state.value,
        "evidence_availability": validation.evidence_availability.value,
        "clinvar": {
            "significance": annotation.clinvar_significance,
            "review_status": annotation.clinvar_review_status,
            "variation_id": annotation.clinvar_variation_id,
        },
        "phenotype": annotation.phenotype,
        "hgvs_c": annotation.hgvs_c,
        "hgvs_p": annotation.hgvs_p,
    }


def _passages_section(ranked_passages: list[RankedPassage]) -> list[dict[str, Any]]:
    return [
        {
            "pmid": r.passage.pmid,
            "title": r.passage.title,
            "abstract": r.passage.abstract,
            "year": r.passage.year,
            "rank": r.rank,
        }
        for r in ranked_passages
    ]
