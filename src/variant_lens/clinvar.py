"""
ClinVar lookups for the golden set.

Given a variant in HGVS notation, this module finds the ClinVar record
and returns the PubMed identifiers linked to that record. The linkage
comes from NCBI elink, which exposes the same citation relationships
shown on the ClinVar page.

Two design choices matter here. The first is batching. Instead of
sending one elink request per ClinVar identifier, the identifiers are
joined and sent in a single request. NCBI accepts comma separated
identifiers, and this reduces the request count considerably.

The second is pacing. NCBI documents a limit of three requests per
second without an API key, and the limit is enforced more strictly
than the nominal rate suggests. The pause between requests is set to
half a second by default, which leaves a margin of safety. When an API
key is present, the pause is shortened but remains above the strict
minimum.

Responses are cached through the shared Cache class. Repeated runs on
the same variants do not touch the network.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from .cache import Cache
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

_PAUSE = 0.2 if _API_KEY else 0.5

_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


def _shared_params() -> dict[str, str]:
    params = {"tool": _TOOL}
    if _EMAIL:
        params["email"] = _EMAIL
    if _API_KEY:
        params["api_key"] = _API_KEY
    return params


def _pause() -> None:
    time.sleep(_PAUSE)


def _get(
    url: str,
    params: dict[str, str],
    cache: Cache | None = None,
    cache_key: str | None = None,
) -> dict[str, Any]:
    if cache is not None and cache_key is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=FETCH_TIMEOUT)
            if response.status_code == 429:
                wait = _BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "rate limited by NCBI, waiting %.1f seconds", wait
                )
                time.sleep(wait)
                last_error = FetchError("rate limited")
                continue
            response.raise_for_status()
        except requests.RequestException as exc:
            raise FetchError(f"request to {url} failed: {exc}") from exc

        _pause()

        try:
            payload = response.json()
        except ValueError as exc:
            raise FetchError(
                f"response from {url} was not valid JSON: {exc}"
            ) from exc

        if cache is not None and cache_key is not None:
            try:
                cache.set(cache_key, payload)
            except Exception as exc:
                logger.warning("failed to write cache entry %s: %s", cache_key, exc)

        return payload

    raise FetchError(f"giving up after {_MAX_RETRIES} attempts: {last_error}")


def search_clinvar(hgvs: str, max_results: int = 5) -> list[str]:
    """
    Return ClinVar UIDs that match the given HGVS string.

    The search term is passed as-is. Broadening it with gene symbols or
    phenotype terms would return neighbouring variants and make the
    downstream linkage ambiguous.
    """
    cache = Cache()
    cache_key = f"clinvar:{hgvs}:esearch"

    params = _shared_params()
    params.update(
        {
            "db": "clinvar",
            "term": hgvs,
            "retmode": "json",
            "retmax": str(max_results),
        }
    )

    payload = _get(
        f"{_EUTILS}/esearch.fcgi",
        params,
        cache=cache,
        cache_key=cache_key,
    )
    return list(payload.get("esearchresult", {}).get("idlist", []))


def get_clinvar_linked_pmids(clinvar_uids: list[str]) -> list[str]:
    """
    Return PMIDs that ClinVar links to the given records.

    All identifiers are sent in one request. NCBI accepts a comma
    separated list in the id parameter, and returns one linkset per
    identifier. The results are merged and de-duplicated.
    """
    if not clinvar_uids:
        return []

    cache = Cache()
    joined = ",".join(clinvar_uids)
    cache_key = f"clinvar:{joined}:elink"

    params = _shared_params()
    params.update(
        {
            "dbfrom": "clinvar",
            "db": "pubmed",
            "id": joined,
            "retmode": "json",
        }
    )

    payload = _get(
        f"{_EUTILS}/elink.fcgi",
        params,
        cache=cache,
        cache_key=cache_key,
    )
    return _extract_pmids(payload)


def _extract_pmids(payload: dict[str, Any]) -> list[str]:
    """
    Pull PMIDs out of an elink response.

    A single response can carry several linksets if the identifiers
    belong to different records. The function walks all of them and
    drops empty entries, which can appear when a ClinVar record has no
    linked publications.
    """
    pmids: list[str] = []
    seen: set[str] = set()

    for linkset in payload.get("linksets", []):
        for linkdb in linkset.get("linksetdbs", []):
            if linkdb.get("dbto") != "pubmed":
                continue
            for raw in linkdb.get("links", []):
                pmid = str(raw).strip()
                if not pmid:
                    continue
                if pmid not in seen:
                    seen.add(pmid)
                    pmids.append(pmid)

    return pmids


def fetch_clinvar_pmids(hgvs: str) -> dict[str, Any]:
    """
    Search ClinVar for a variant and return its linked PubMed IDs.

    Returns a dictionary with three keys. The uids list is kept for
    traceability. The pmids list is the union of everything linked to
    the matched records. The complete flag reports whether every
    ClinVar record was successfully processed.
    """
    uids = search_clinvar(hgvs)
    if not uids:
        return {"uids": [], "pmids": [], "complete": True}

    try:
        pmids = get_clinvar_linked_pmids(uids)
    except FetchError as exc:
        logger.warning("elink failed for %s: %s", hgvs, exc)
        return {"uids": uids, "pmids": [], "complete": False}

    return {"uids": uids, "pmids": pmids, "complete": True}
