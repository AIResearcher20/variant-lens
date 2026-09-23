"""
Tests for the golden evidence builder.

The ClinVar lookup is replaced with an in-memory stub, and the PubMed
calls are mocked. No test touches the network.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from variant_lens.golden import (
    build_all_records,
    build_evidence_record,
    is_reference_passage,
    mentions_variant,
    variant_tokens,
)
from variant_lens.schema import Passage


class FakeClinVar:
    """Minimal stand-in for ClinVarBulk used in tests."""

    def __init__(self, entries: dict[tuple[str, str], dict]) -> None:
        self.entries = entries

    def lookup(self, gene: str, hgvs: str) -> dict:
        return self.entries.get(
            (gene, hgvs),
            {"variation_id": None, "pmids": [], "summary": {}},
        )

    def load(self) -> None:
        return None


def test_tokens_include_full_hgvs():
    tokens = variant_tokens("c.68_69delAG")
    assert "c.68_69delAG" in tokens


def test_tokens_include_body_without_prefix():
    tokens = variant_tokens("c.68_69delAG")
    assert "68_69delAG" in tokens


def test_tokens_include_position():
    tokens = variant_tokens("c.68_69delAG")
    assert "68_69" in tokens


def test_tokens_include_individual_positions():
    tokens = variant_tokens("c.68_69delAG")
    assert "68" in tokens
    assert "69" in tokens


def test_tokens_handle_single_position():
    tokens = variant_tokens("c.743G>A")
    assert "743" in tokens


def test_tokens_empty_input():
    tokens = variant_tokens("")
    assert tokens == []


def test_mentions_variant_matches_full_hgvs():
    text = "The c.68_69delAG variant in BRCA1 is pathogenic."
    assert mentions_variant(text, ["c.68_69delAG"])


def test_mentions_variant_matches_position_only():
    text = "We identified the 68_69 deletion in a cohort of patients."
    assert mentions_variant(text, ["68_69"])


def test_mentions_variant_respects_word_boundaries():
    text = "The variant is at position 680."
    assert not mentions_variant(text, ["68"])


def test_mentions_variant_empty_text():
    assert not mentions_variant("", ["68"])


def test_mentions_variant_case_insensitive():
    text = "BRCA1 C.68_69DELAG is a founder mutation."
    assert mentions_variant(text, ["c.68_69delAG"])


def test_is_reference_passage_from_title():
    passage = Passage(
        pmid="1",
        title="c.68_69delAG in BRCA1",
        abstract=None,
        year=2000,
    )
    assert is_reference_passage(passage, ["c.68_69delAG"])


def test_is_reference_passage_from_abstract():
    passage = Passage(
        pmid="2",
        title="A study of BRCA1 mutations",
        abstract="We report the 68_69 deletion in three families.",
        year=2001,
    )
    assert is_reference_passage(passage, ["68_69"])


def test_is_reference_passage_no_match():
    passage = Passage(
        pmid="3",
        title="A study of BRCA1 mutations",
        abstract="We report the 5266dupC variant in three families.",
        year=2002,
    )
    assert not is_reference_passage(passage, ["68_69"])


def test_is_reference_passage_empty_passage():
    passage = Passage(pmid="4", title=None, abstract=None, year=None)
    assert not is_reference_passage(passage, ["68"])


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
def test_build_evidence_record_full_flow(mock_articles, mock_candidates):
    clinvar = FakeClinVar({
        ("BRCA1", "c.68_69delAG"): {
            "variation_id": "100",
            "pmids": ["111", "222", "333"],
            "summary": {
                "name": "NM_007294.4(BRCA1):c.68_69delAG",
                "clinical_significance": "Pathogenic",
                "review_status": "reviewed by expert panel",
                "phenotypes": "Hereditary breast and ovarian cancer",
                "chromosome": "17",
                "position_vcf": 43071077,
                "ref_vcf": "C",
                "alt_vcf": "T",
            },
        },
    })
    mock_articles.return_value = [
        Passage(
            pmid="111",
            title="The c.68_69delAG variant in BRCA1",
            abstract="Pathogenic in hereditary breast cancer.",
            year=2005,
        ),
        Passage(
            pmid="222",
            title="BRCA1 mutations in a cohort",
            abstract="We identified 5266dupC in several families.",
            year=2006,
        ),
        Passage(
            pmid="333",
            title="Review of BRCA1 and BRCA2",
            abstract="General review without specific variants.",
            year=2007,
        ),
    ]
    mock_candidates.return_value = [
        Passage(
            pmid="444",
            title="Unrelated article about BRCA1",
            abstract="No specific variant mentioned.",
            year=2008,
        ),
    ]

    record = build_evidence_record(
        variant_id="brca1_c68_69delag",
        gene="BRCA1",
        hgvs="c.68_69delAG",
        phenotype="Hereditary breast and ovarian cancer",
        clinvar=clinvar,
    )

    assert record["variant_id"] == "brca1_c68_69delag"
    assert record["gene"] == "BRCA1"
    assert record["clinvar_variation_id"] == "100"
    assert record["clinvar_found"] is True
    assert record["clinvar_linked_pmids"] == ["111", "222", "333"]
    assert record["reference_pmids"] == ["111"]
    assert record["pubmed_candidate_pmids"] == ["444"]
    assert record["candidate_pmids"] == ["111", "222", "333", "444"]
    assert record["titles"]["111"] == "The c.68_69delAG variant in BRCA1"
    assert record["years"]["111"] == 2005
    assert record["label_source"].startswith("ClinVar-linked")
    assert record["candidate_source"] == "ClinVar bulk and PubMed esearch"


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
def test_build_evidence_record_no_clinvar_match(mock_articles, mock_candidates):
    clinvar = FakeClinVar({})
    mock_articles.return_value = []
    mock_candidates.return_value = [
        Passage(pmid="555", title="Some article", abstract=None, year=2010),
    ]

    record = build_evidence_record(
        variant_id="x",
        gene="GENE",
        hgvs="c.100A>T",
        phenotype="",
        clinvar=clinvar,
    )

    assert record["clinvar_variation_id"] is None
    assert record["clinvar_found"] is False
    assert record["clinvar_linked_pmids"] == []
    assert record["reference_pmids"] == []
    assert record["pubmed_candidate_pmids"] == ["555"]
    assert record["candidate_pmids"] == ["555"]


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
def test_build_evidence_record_no_reference_after_filter(
    mock_articles,
    mock_candidates,
):
    clinvar = FakeClinVar({
        ("CFTR", "c.1521_1523delCTT"): {
            "variation_id": "200",
            "pmids": ["900", "901"],
            "summary": {},
        },
    })
    mock_articles.return_value = [
        Passage(
            pmid="900",
            title="General review of CFTR",
            abstract="No specific variant discussed.",
            year=2015,
        ),
        Passage(
            pmid="901",
            title="Another general review",
            abstract="Overview of CFTR mutations.",
            year=2016,
        ),
    ]
    mock_candidates.return_value = []

    record = build_evidence_record(
        variant_id="cftr_f508del",
        gene="CFTR",
        hgvs="c.1521_1523delCTT",
        phenotype="Cystic fibrosis",
        clinvar=clinvar,
    )

    assert record["clinvar_linked_pmids"] == ["900", "901"]
    assert record["reference_pmids"] == []


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
def test_candidate_pmids_deduplicated(mock_articles, mock_candidates):
    clinvar = FakeClinVar({
        ("BRCA1", "c.68_69delAG"): {
            "variation_id": "300",
            "pmids": ["700", "701"],
            "summary": {},
        },
    })
    mock_articles.return_value = [
        Passage(pmid="700", title="c.68_69delAG in BRCA1", abstract=None, year=2000),
        Passage(pmid="701", title="Other BRCA1 variant", abstract=None, year=2001),
    ]
    mock_candidates.return_value = [
        Passage(pmid="701", title="Overlap", abstract=None, year=2001),
        Passage(pmid="702", title="New", abstract=None, year=2002),
    ]

    record = build_evidence_record(
        variant_id="x",
        gene="BRCA1",
        hgvs="c.68_69delAG",
        phenotype="",
        clinvar=clinvar,
    )

    assert record["candidate_pmids"] == ["700", "701", "702"]


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
def test_build_evidence_record_without_clinvar(mock_articles, mock_candidates):
    mock_articles.return_value = []
    mock_candidates.return_value = []

    record = build_evidence_record(
        variant_id="x",
        gene="GENE",
        hgvs="c.1A>T",
        phenotype="",
        clinvar=None,
    )

    assert record["clinvar_variation_id"] is None
    assert record["clinvar_found"] is False
    assert record["clinvar_linked_pmids"] == []


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
@patch("variant_lens.golden.ClinVarBulk")
def test_build_all_records(mock_bulk, mock_articles, mock_candidates):
    mock_bulk.return_value = FakeClinVar({
        ("BRCA1", "c.68_69delAG"): {
            "variation_id": "100",
            "pmids": ["111"],
            "summary": {},
        },
    })
    mock_articles.return_value = [
        Passage(pmid="111", title="c.68_69delAG", abstract=None, year=2000),
    ]
    mock_candidates.return_value = []

    variants = [
        {"variant_id": "v1", "gene": "BRCA1", "hgvs": "c.68_69delAG", "phenotype": ""},
    ]

    records = build_all_records(
        variants=variants,
        bulk_dir=Path("/tmp/clinvar"),
    )

    assert len(records) == 1
    assert records[0]["variant_id"] == "v1"
