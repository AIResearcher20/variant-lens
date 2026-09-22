"""
Warning messages for VariantLens.

Each function returns a Warning with a fixed code and a formatted message.
"""

from __future__ import annotations

from .schema import Warning, WarningCode


def w001_parse_failed(input_variant: str) -> Warning:
    return Warning(
        code=WarningCode.W001,
        message=f"Could not parse variant: {input_variant!r}",
        severity="error",
        context={"input": input_variant},
    )


def w002_ambiguous_hgvs(input_variant: str, candidates: list[str]) -> Warning:
    return Warning(
        code=WarningCode.W002,
        message=f"HGVS is ambiguous for {input_variant!r}; using {candidates[0]!r}",
        severity="warning",
        context={"input": input_variant, "candidates": candidates},
    )


def w101_no_gnomad_record(hgvs: str) -> Warning:
    return Warning(
        code=WarningCode.W101,
        message=f"No gnomAD record for {hgvs}",
        severity="warning",
        context={"hgvs": hgvs},
    )


def w102_no_clinvar_record(hgvs: str) -> Warning:
    return Warning(
        code=WarningCode.W102,
        message=f"No ClinVar record for {hgvs}",
        severity="warning",
        context={"hgvs": hgvs},
    )


def w103_no_phenotype(hgvs: str) -> Warning:
    return Warning(
        code=WarningCode.W103,
        message=f"No phenotype available in ClinVar for {hgvs}",
        severity="info",
        context={"hgvs": hgvs},
    )


def w104_af_above_threshold(hgvs: str, af: float, threshold: float) -> Warning:
    return Warning(
        code=WarningCode.W104,
        message=f"Allele frequency {af} for {hgvs} is at or above threshold {threshold}",
        severity="warning",
        context={"hgvs": hgvs, "af": af, "threshold": threshold},
    )


def w105_unsupported_type(variant_type: str) -> Warning:
    return Warning(
        code=WarningCode.W105,
        message=f"Unsupported variant type: {variant_type}",
        severity="error",
        context={"variant_type": variant_type},
    )


def w201_few_pubmed_results(count: int) -> Warning:
    return Warning(
        code=WarningCode.W201,
        message=f"Fewer than 5 PubMed results ({count})",
        severity="info",
        context={"count": count},
    )


def w202_low_rerank_confidence(score: float, threshold: float) -> Warning:
    return Warning(
        code=WarningCode.W202,
        message=f"Top rerank score {score} is below threshold {threshold}",
        severity="warning",
        context={"score": score, "threshold": threshold},
    )


def w301_vus_classification() -> Warning:
    return Warning(
        code=WarningCode.W301,
        message="Variant is classified as Uncertain Significance",
        severity="info",
        context=None,
    )
