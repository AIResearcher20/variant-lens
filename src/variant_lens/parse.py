"""
Variant parsing.

Handles HGVS nomenclature and VCF-style coordinates. No network access.
"""

from __future__ import annotations

import re

from .schema import ParsedVariant, VariantType, Warning
from .warnings import w001_parse_failed, w105_unsupported_type


_HGVS_RE = re.compile(
    r"^(?P<gene>[A-Za-z0-9\-]+)\s+"
    r"(?P<change>c\.[0-9_]+(?:del|ins|dup|>)[A-Za-z]*)$"
)

_HGVS_SUBSTITUTION_RE = re.compile(r"^c\.[0-9]+[ACGT]>[ACGT]$")
_HGVS_INDEL_RE = re.compile(r"^c\.[0-9_]+(del|ins|dup)[A-Za-z]*$")

_VCF_RE = re.compile(
    r"^(?P<chr>chr[0-9XYM]+):"
    r"(?P<pos>[0-9]+):"
    r"(?P<ref>[ACGTN]+):"
    r"(?P<alt>[ACGTN]+)$"
)


def parse_variant(input_variant: str) -> ParsedVariant:
    """
    Parse a variant string.

    Returns a ParsedVariant. Never raises for malformed input.
    """
    if not isinstance(input_variant, str) or not input_variant.strip():
        return _unparseable(input_variant, "empty or non-string input")

    text = input_variant.strip()

    hgvs_match = _HGVS_RE.match(text)
    if hgvs_match:
        return _from_hgvs(text, hgvs_match)

    vcf_match = _VCF_RE.match(text)
    if vcf_match:
        return _from_vcf(text, vcf_match)

    return _unparseable(text, "unrecognized format")


def _from_hgvs(text: str, match: re.Match) -> ParsedVariant:
    gene = match.group("gene")
    change = match.group("change")

    if _HGVS_SUBSTITUTION_RE.match(change):
        variant_type = VariantType.SNV
    elif _HGVS_INDEL_RE.match(change):
        variant_type = VariantType.INDEL
    else:
        variant_type = VariantType.UNKNOWN

    return ParsedVariant(
        input_variant=text,
        normalized_hgvs=f"{gene} {change}",
        gene=gene,
        variant_type=variant_type,
        is_parseable=True,
        is_supported=variant_type in (VariantType.SNV, VariantType.INDEL),
        warnings=[],
    )


def _from_vcf(text: str, match: re.Match) -> ParsedVariant:
    ref = match.group("ref")
    alt = match.group("alt")

    if len(ref) == 1 and len(alt) == 1:
        variant_type = VariantType.SNV
    elif len(ref) != len(alt):
        variant_type = VariantType.INDEL
    else:
        variant_type = VariantType.UNKNOWN

    return ParsedVariant(
        input_variant=text,
        normalized_hgvs=None,
        gene=None,
        variant_type=variant_type,
        is_parseable=True,
        is_supported=variant_type in (VariantType.SNV, VariantType.INDEL),
        warnings=[],
    )


def _unparseable(text: str, reason: str) -> ParsedVariant:
    warning = w001_parse_failed(text)
    return ParsedVariant(
        input_variant=text if isinstance(text, str) else str(text),
        normalized_hgvs=None,
        gene=None,
        variant_type=VariantType.UNKNOWN,
        is_parseable=False,
        is_supported=False,
        warnings=[warning],
    )
