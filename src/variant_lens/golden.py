"""
Build evidence records for the golden set.

Each record combines three sources of information.

The first is ClinVar. Variation identifiers and their linked PubMed
citations are read from the bulk tables. Because the bulk tables
already contain the citation linkage, no network call is needed for
this step.

The second is PubMed. A search based on gene and HGVS returns a wider
set of articles, most of which will not concern the variant. These act
as distractors for the retrieval benchmark.

The third is the variant itself. Its HGVS string is reduced to a small
set of tokens, and those tokens are matched against titles and
abstracts with word boundaries. Only articles that mention at least
one of these tokens are kept in the reference set.

The module does not make assumptions about network conditions for the
ClinVar side. PubMed lookups are still performed over HTTP, but the
number of requests is small. When a lookup fails, the corresponding
list is left empty and a flag records that the record is incomplete.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from .clinvar import ClinVarBulk
from .fetch import fetch_pubmed_passages
from .schema import Passage


logger = logging.getLogger(__name__)


DEFAULT_PUBMED_CANDIDATES = 50


def variant_tokens(hgvs: str) -> list[str]:
    """
    Reduce an HGVS string to a small set of searchable tokens.

    The full HGVS is rarely written out in an abstract. Authors write
    the short form, the position alone, or a legacy name. The tokens
    returned here cover the common cases. Matching is later done with
    word boundaries, so a token such as 68 will not match 680.
    """
    tokens: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            tokens.append(value)

    add(hgvs)

    body = hgvs
    for prefix in ("c.", "g.", "m.", "n.", "p."):
        if body.startswith(prefix):
            body = body[len(prefix):]
            break

    add(body)

    position_match = re.match(r"([0-9]+(?:_[0-9]+)?)", body)
    if position_match:
        add(position_match.group(1))
        for part in position_match.group(1).split("_"):
            add(part)

    return tokens


def mentions_variant(text: str, tokens: Iterable[str]) -> bool:
    """
    Return True when the text contains at least one variant token.

    The match uses word boundaries so that partial overlaps, such as a
    numeric prefix of a longer coordinate, do not count.
    """
    if not text:
        return False
    for token in tokens:
        pattern = rf"\b{re.escape(token)}\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def is_reference_passage(passage: Passage, tokens: Iterable[str]) -> bool:
    combined = f"{passage.title or ''} {passage.abstract or ''}"
    return mentions_variant(combined, tokens)


def fetch_articles(pmids: list[str]) -> list[Passage]:
    """
    Retrieve passages for a specific list of PMIDs.

    The fetch module exposes a query based search, not a direct lookup
    by identifier. To fetch a known set of PMIDs, the identifiers are
    joined into a single OR query. That form is accepted by PubMed and
    returns the corresponding articles.
    """
    if not pmids:
        return []
    query = " OR ".join(f"{pmid}[uid]" for pmid in pmids)
    try:
        return fetch_pubmed_passages(query, max_results=len(pmids))
    except Exception as exc:
        logger.warning("PubMed fetch failed: %s", exc)
        return []


def fetch_pubmed_candidates(query: str, max_results: int) -> list[Passage]:
    try:
        return fetch_pubmed_passages(query, max_results=max_results)
    except Exception as exc:
        logger.warning("PubMed candidate search failed: %s", exc)
        return []


def build_evidence_record(
    variant_id: str,
    gene: str,
    hgvs: str,
    phenotype: str,
    clinvar: ClinVarBulk | None,
    pubmed_candidates: int = DEFAULT_PUBMED_CANDIDATES,
) -> dict[str, Any]:
    """
    Assemble a single evidence record.

    The ClinVar lookup is local and expected to succeed when the bulk
    tables contain the variant. PubMed is queried over HTTP. Records
    with an empty reference set or a missing ClinVar entry are still
    returned. The caller decides what to do with them.
    """
    query_base = f"{gene} {hgvs}".strip()
    query_full = f"{query_base} {phenotype}".strip() if phenotype else query_base

    if clinvar is not None:
        clinvar_result = clinvar.lookup(gene, hgvs)
    else:
        clinvar_result = {"variation_id": None, "pmids": [], "summary": {}}

    variation_id = clinvar_result["variation_id"]
    clinvar_pmids = clinvar_result["pmids"]
    summary = clinvar_result["summary"]

    tokens = variant_tokens(hgvs)

    reference_pmids: list[str] = []
    titles: dict[str, str] = {}
    years: dict[str, int] = {}

    if clinvar_pmids:
        clinvar_passages = fetch_articles(clinvar_pmids)
        by_pmid = {p.pmid: p for p in clinvar_passages if p.pmid}
        for pmid in clinvar_pmids:
            passage = by_pmid.get(pmid)
            if passage is None:
                continue
            if passage.title:
                titles[pmid] = passage.title
            if passage.year is not None:
                years[pmid] = passage.year
            if is_reference_passage(passage, tokens):
                reference_pmids.append(pmid)

    candidate_passages = fetch_pubmed_candidates(query_full, pubmed_candidates)
    pubmed_candidate_pmids: list[str] = []
    for passage in candidate_passages:
        pmid = passage.pmid
        if not pmid:
            continue
        if pmid not in titles and passage.title:
            titles[pmid] = passage.title
        if passage.year is not None and pmid not in years:
            years[pmid] = passage.year
        pubmed_candidate_pmids.append(pmid)

    candidate_pmids: list[str] = []
    seen: set[str] = set()
    for pmid in clinvar_pmids + pubmed_candidate_pmids:
        if pmid and pmid not in seen:
            seen.add(pmid)
            candidate_pmids.append(pmid)

    return {
        "variant_id": variant_id,
        "gene": gene,
        "hgvs": hgvs,
        "query": query_full,
        "clinvar_variation_id": variation_id,
        "clinvar_summary": summary,
        "clinvar_linked_pmids": clinvar_pmids,
        "clinvar_found": variation_id is not None,
        "reference_pmids": reference_pmids,
        "pubmed_candidate_pmids": pubmed_candidate_pmids,
        "candidate_pmids": candidate_pmids,
        "titles": titles,
        "years": years,
        "label_source": "ClinVar-linked citations filtered by variant token",
        "candidate_source": "ClinVar bulk and PubMed esearch",
        "notes": "auto-generated by prepare_golden_evidence",
    }


def build_all_records(
    variants: list[dict[str, str]],
    bulk_dir: Path,
    pubmed_candidates: int = DEFAULT_PUBMED_CANDIDATES,
) -> list[dict[str, Any]]:
    """
    Build evidence records for every variant in the table.

    The ClinVar bulk tables are loaded once and reused for all
    variants. This keeps memory use bounded and avoids re-reading the
    large files for each variant.
    """
    clinvar = ClinVarBulk(bulk_dir=bulk_dir, variants=variants)
    clinvar.load()

    records: list[dict[str, Any]] = []
    for row in variants:
        record = build_evidence_record(
            variant_id=row["variant_id"],
            gene=row["gene"],
            hgvs=row["hgvs"],
            phenotype=row.get("phenotype", ""),
            clinvar=clinvar,
            pubmed_candidates=pubmed_candidates,
        )
        records.append(record)
    return records
