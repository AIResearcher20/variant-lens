"""
Tests for variant_lens.parse.

Written before the implementation. Each test states one contract claim.
"""

from variant_lens.parse import parse_variant
from variant_lens.schema import VariantType


def test_parses_hgvs_cdna():
    result = parse_variant("BRCA1 c.68_69delAG")
    assert result.is_parseable is True
    assert result.gene == "BRCA1"
    assert result.variant_type == VariantType.INDEL


def test_parses_hgvs_substitution():
    result = parse_variant("TP53 c.743G>A")
    assert result.is_parseable is True
    assert result.gene == "TP53"
    assert result.variant_type == VariantType.SNV


def test_parses_vcf_style_indel():
    result = parse_variant("chr17:43124028:CT:C")
    assert result.is_parseable is True
    assert result.variant_type == VariantType.INDEL
    assert result.gene is None


def test_parses_vcf_style_snv():
    result = parse_variant("chr13:32340614:C:T")
    assert result.is_parseable is True
    assert result.variant_type == VariantType.SNV


def test_rejects_empty_string():
    result = parse_variant("")
    assert result.is_parseable is False


def test_rejects_gibberish():
    result = parse_variant("not-a-variant")
    assert result.is_parseable is False


def test_deterministic_output():
    first = parse_variant("BRCA1 c.68_69delAG")
    second = parse_variant("BRCA1 c.68_69delAG")
    assert first == second
