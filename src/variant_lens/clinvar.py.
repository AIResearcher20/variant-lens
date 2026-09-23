"""
ClinVar lookups for the golden set.

Given a variant in HGVS notation, this module finds the ClinVar record
and returns the PubMed identifiers linked to that record. The linkage
comes from NCBI elink, which exposes the same citation relationships
that appear on the ClinVar page.

NCBI asks that every E-utilities request carries a tool name and, when
possible, a contact email. Both are read from the environment so that
deployments and local runs behave the same way.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from .config import FETCH_TIMEOUT
from .fetch import FetchError


logger = logging.getLogger(__name__)


_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

_TOOL = os.environ.get("NCBI_TOOL", "variant-lens")
_EMAIL = os.environ.get("NCBI_EMAIL", "")
_API_KEY = os.environ.get("NCBI_API_KEY", "")

if not _EMAIL:
    logger.warning(
        "NCBI_EMAIL is not set. NCBI prefers a contact address for E-utilities."
    )

_PAUSE = 0.11 if _API_KEY else 0.34


def _shared_params() -> dict[str, str]:
    params = {"tool": _TOOL}
    if _EMAIL:
        params["email"] = _EMAIL
    if _API_KEY:
        params["api_key"] = _API_KEY
    return params


def _pause() -> None:
    time.sleep(_PAUSE)


def _get(url: str, params: dict[str, str]) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"request to {url} failed: {exc}") from exc

    _pause()

    try:
        return response.json()
    except ValueError as exc:
        raise FetchError(f"response from {url} was not valid JSON: {exc}") from exc


def search_clinvar(hgvs: str, max_results: int = 5) -> list[str]:
    """
    Return ClinVar UIDs that match the given HGVS string.

    The search is deliberately narrow: we pass the HGVS term as-is and
    let ClinVar's own indexing decide what matches. Broadening the term
    would pull in records for neighbouring variants and complicate the
    downstream linkage step.
    """
    params = _shared_params()
    params.update(
        {
            "db": "clinvar",
            "term": hgvs,
            "retmode": "json",
            "retmax": str(max_results),
        }
    )

    payload = _get(f"{_EUTILS}/esearch.fcgi", params)
    return list(payload.get("esearchresult", {}).get("idlist", []))


def get_clinvar_linked_pmids(clinvar_uid: str) -> list[str]:
    """
    Return PMIDs that ClinVar links to the given record.

    elink is the intended interface for this. It returns the same
    citation relationships shown on the ClinVar page, without us having
    to parse the full XML record.
    """
    params = _shared_params()
    params.update(
        {
            "dbfrom": "clinvar",
            "db": "pubmed",
            "id": clinvar_uid,
            "retmode": "json",
        }
    )

    payload = _get(f"{_EUTILS}/elink.fcgi", params)
    return _extract_pmids(payload)


def _extract_pmids(payload: dict[str, Any]) -> list[str]:
    """
    Pull PMIDs out of an elink response.

    elink wraps the identifiers in a linkset. A single ClinVar record
    can produce more than one linkset if the linkage exists through
    multiple paths, so we walk all of them and de-duplicate.
    """
    pmids: list[str] = []
    seen: set[str] = set()

    for linkset in payload.get("linksets", []):
        for linkdb in linkset.get("linksetdbs", []):
            if linkdb.get("dbto") != "pubmed":
                continue
            for raw in linkdb.get("links", []):
                pmid = str(raw)
                if pmid not in seen:
                    seen.add(pmid)
                    pmids.append(pmid)

    return pmids


def fetch_clinvar_pmids(hgvs: str) -> dict[str, Any]:
    """
    Convenience wrapper: search ClinVar, then collect linked PMIDs.

    A variant can appear in ClinVar more than once, for instance when
    different submitters have filed separate records. We union the
    PMIDs across all matches so that the caller does not have to think
    about which record was chosen.

    Returns a dictionary with two keys, ``uids`` and ``pmids``. The
    ``uids`` list is kept for debugging and for the evidence file, so
    that a later reader can trace which ClinVar records contributed.
    """
    uids = search_clinvar(hgvs)
    if not uids:
        return {"uids": [], "pmids": []}

    collected: list[str] = []
    seen: set[str] = set()

    for uid in uids:
        try:
            pmids = get_clinvar_linked_pmids(uid)
        except FetchError as exc:
            logger.warning("elink failed for ClinVar uid %s: %s", uid, exc)
            continue
        for pmid in pmids:
            if pmid not in seen:
                seen.add(pmid)
                collected.append(pmid)

    return {"uids": uids, "pmids": collected}
