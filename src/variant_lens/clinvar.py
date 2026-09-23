"""
Build evidence records for the golden set.

For each variant, three sources are combined.

The first is ClinVar. Its records link to PubMed articles, and those
linkages are exposed through elink. The linked identifiers are useful,
but they include articles that discuss the gene in general rather than
the variant specifically. A filter is applied afterwards.

The second is PubMed. A search based on gene and HGVS returns a wider
set of articles, most of which will not concern the variant. These act
as distractors for the retrieval benchmark.

The third is the variant itself. Its HGVS string is reduced to a small
set of tokens, and those tokens are matched against titles and
abstracts with word boundaries. Only articles that mention at least
one of these tokens are kept in the reference set.

The module does not make assumptions about network conditions. When a
ClinVar or PubMed lookup fails, the corresponding list is left empty
and a flag records that the record is incomplete. The caller decides
whether to keep such a record in the golden set.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from .clinvar import fetch_clinvar_pmids
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
    phenotype: str = "",
    pubmed_candidates: int = DEFAULT_PUBMED_CANDIDATES,
    lookup_clinvar: bool = True,
) -> dict[str, Any]:
    """
    Assemble a single evidence record.

    The function performs the network calls, applies the variant filter
    to the ClinVar linked identifiers, and merges everything into a
    dictionary. Records with an empty reference set or an incomplete
    ClinVar lookup are still returned. The caller decides what to do
    with them.
    """
    query_base = f"{gene} {hgvs}".strip()
    query_full = f"{query_base} {phenotype}".strip() if phenotype else query_base

    if lookup_clinvar:
        clinvar_result = fetch_clinvar_pmids(hgvs)
        clinvar_uids = clinvar_result.get("uids", [])
        clinvar_pmids = clinvar_result.get("pmids", [])
        clinvar_complete = clinvar_result.get("complete", True)
    else:
        clinvar_uids = []
        clinvar_pmids = []
        clinvar_complete = True

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
        "clinvar_uids": clinvar_uids,
        "clinvar_linked_pmids": clinvar_pmids,
        "clinvar_complete": clinvar_complete,
        "reference_pmids": reference_pmids,
        "pubmed_candidate_pmids": pubmed_candidate_pmids,
        "candidate_pmids": candidate_pmids,
        "titles": titles,
        "years": years,
        "label_source": "ClinVar-linked citations filtered by variant token",
        "candidate_source": "ClinVar elink and PubMed esearch",
        "notes": "auto-generated by prepare_golden_evidence",
    }
