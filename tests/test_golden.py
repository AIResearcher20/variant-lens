"""
Tests for the golden evidence builder.

Network calls are replaced with fixed values so that the tests run
without external services. The purpose is to verify the logic of the
builder: token extraction, variant matching, and how the three sources
are combined.
"""

from __future__ import annotations

from unittest.mock import patch

from variant_lens.golden import (
    build_evidence_record,
    is_reference_passage,
    mentions_variant,
    variant_tokens,
)
from variant_lens.schema import Passage


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
@patch("variant_lens.golden.fetch_clinvar_pmids")
def test_build_evidence_record_full_flow(
    mock_clinvar,
    mock_fetch_articles,
    mock_candidates,
):
    mock_clinvar.return_value = {
        "uids": ["100"],
        "pmids": ["111", "222", "333"],
        "complete": True,
    }
    mock_fetch_articles.return_value = [
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
    )

    assert record["variant_id"] == "brca1_c68_69delag"
    assert record["gene"] == "BRCA1"
    assert record["clinvar_uids"] == ["100"]
    assert record["clinvar_linked_pmids"] == ["111", "222", "333"]
    assert record["clinvar_complete"] is True
    assert record["reference_pmids"] == ["111"]
    assert record["pubmed_candidate_pmids"] == ["444"]
    assert record["candidate_pmids"] == ["111", "222", "333", "444"]
    assert record["titles"]["111"] == "The c.68_69delAG variant in BRCA1"
    assert record["years"]["111"] == 2005
    assert record["label_source"].startswith("ClinVar-linked")
    assert record["candidate_source"] == "ClinVar elink and PubMed esearch"


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
@patch("variant_lens.golden.fetch_clinvar_pmids")
def test_build_evidence_record_no_clinvar_match(
    mock_clinvar,
    mock_fetch_articles,
    mock_candidates,
):
    mock_clinvar.return_value = {"uids": [], "pmids": [], "complete": True}
    mock_fetch_articles.return_value = []
    mock_candidates.return_value = [
        Passage(pmid="555", title="Some article", abstract=None, year=2010),
    ]

    record = build_evidence_record(
        variant_id="x",
        gene="GENE",
        hgvs="c.100A>T",
    )

    assert record["clinvar_uids"] == []
    assert record["clinvar_linked_pmids"] == []
    assert record["clinvar_complete"] is True
    assert record["reference_pmids"] == []
    assert record["pubmed_candidate_pmids"] == ["555"]
    assert record["candidate_pmids"] == ["555"]


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
@patch("variant_lens.golden.fetch_clinvar_pmids")
def test_build_evidence_record_no_reference_after_filter(
    mock_clinvar,
    mock_fetch_articles,
    mock_candidates,
):
    mock_clinvar.return_value = {
        "uids": ["200"],
        "pmids": ["900", "901"],
        "complete": True,
    }
    mock_fetch_articles.return_value = [
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
    )

    assert record["clinvar_linked_pmids"] == ["900", "901"]
    assert record["reference_pmids"] == []


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
@patch("variant_lens.golden.fetch_clinvar_pmids")
def test_candidate_pmids_deduplicated(
    mock_clinvar,
    mock_fetch_articles,
    mock_candidates,
):
    mock_clinvar.return_value = {
        "uids": ["300"],
        "pmids": ["700", "701"],
        "complete": True,
    }
    mock_fetch_articles.return_value = [
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
    )

    assert record["candidate_pmids"] == ["700", "701", "702"]


@patch("variant_lens.golden.fetch_pubmed_candidates")
@patch("variant_lens.golden.fetch_articles")
@patch("variant_lens.golden.fetch_clinvar_pmids")
def test_build_evidence_record_incomplete_clinvar(
    mock_clinvar,
    mock_fetch_articles,
    mock_candidates,
):
    mock_clinvar.return_value = {
        "uids": ["400"],
        "pmids": [],
        "complete": False,
    }
    mock_fetch_articles.return_value = []
    mock_candidates.return_value = []

    record = build_evidence_record(
        variant_id="x",
        gene="GENE",
        hgvs="c.1A>T",
    )

    assert record["clinvar_uids"] == ["400"]
    assert record["clinvar_linked_pmids"] == []
    assert record["clinvar_complete"] is False


@patch("variant_lens.golden.fetch_clinvar_pmids")
@patch("variant_lens.golden.fetch_pubmed_candidates")
def test_lookup_clinvar_disabled(mock_candidates, mock_clinvar):
    mock_candidates.return_value = []
    record = build_evidence_record(
        variant_id="x",
        gene="GENE",
        hgvs="c.1A>T",
        lookup_clinvar=False,
    )
    assert record["clinvar_uids"] == []
    assert record["clinvar_linked_pmids"] == []
    assert record["clinvar_complete"] is True
    mock_clinvar.assert_not_called()
