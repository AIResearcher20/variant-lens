"""
Fetch raw evidence from public APIs.

Contacts MyVariant.info, gnomAD, and PubMed. Uses the local cache first.
Never raises for individual source failures. Raises FetchError only when
the fetch layer itself cannot operate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .cache import Cache
from .config import (
    FETCH_RETRIES,
    FETCH_TIMEOUT,
    STRICT_FETCH,
)
from .schema import Passage, RawEvidence


logger = logging.getLogger(__name__)


_SOURCES = ("gnomad", "clinvar", "pubmed")

_BASE_URLS = {
    "gnomad": "https://gnomad.broadinstitute.org/api",
    "clinvar": "https://myvariant.info/v1/query",
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    "pubmed_fetch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
}


class FetchError(Exception):
    """Raised when the fetch layer itself cannot operate."""


def get_raw_evidence(hgvs: str) -> list[RawEvidence]:
    """
    Fetch raw evidence for a variant.

    Returns one RawEvidence per source. Sources that fail are recorded with
    payload=None. Never raises for individual source failures.
    """
    try:
        cache = Cache()
    except Exception as exc:
        raise FetchError(f"Cache initialization failed: {exc}") from exc

    evidence: list[RawEvidence] = []
    for source in _SOURCES:
        entry = _fetch_one(source, hgvs, cache)
        evidence.append(entry)

    return evidence


def fetch_pubmed_passages(
    query: str,
    max_results: int = 20,
) -> list[Passage]:
    """
    Fetch PubMed passages (title + abstract) for a query.

    Returns an empty list when no results are found or when PubMed is
    unavailable.
    """
    pmids = _pubmed_search(query, max_results)
    if not pmids:
        return []

    records = _pubmed_summary(pmids)
    return [_record_to_passage(record) for record in records]


def _pubmed_search(query: str, max_results: int) -> list[str]:
    try:
        payload = _http_get_json(
            _BASE_URLS["pubmed"],
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": str(max_results),
            },
            timeout=FETCH_TIMEOUT,
        )
    except (requests.RequestException, ConnectionError, ValueError) as exc:
        logger.warning("PubMed search failed: %s", exc)
        return []

    result = payload.get("esearchresult", {})
    return list(result.get("idlist", []))


def _pubmed_summary(pmids: list[str]) -> list[dict[str, Any]]:
    try:
        payload = _http_get_json(
            _BASE_URLS["pubmed_fetch"],
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
            },
            timeout=FETCH_TIMEOUT,
        )
    except (requests.RequestException, ConnectionError, ValueError) as exc:
        logger.warning("PubMed summary failed: %s", exc)
        return []

    result = payload.get("result", {})
    records: list[dict[str, Any]] = []

    for pmid in result.get("uids", []):
        record = result.get(pmid)
        if isinstance(record, dict):
            record = dict(record)
            record["pmid"] = pmid
            records.append(record)

    return records


def _record_to_passage(record: dict[str, Any]) -> Passage:
    year = _extract_year(record.get("pubdate"))
    return Passage(
        pmid=str(record.get("pmid", "")),
        title=str(record.get("title", "")).strip(),
        abstract=_extract_abstract(record.get("abstract")),
        year=year,
    )


def _extract_year(pubdate: Any) -> int | None:
    if not isinstance(pubdate, str):
        return None
    for token in pubdate.split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return None


def _extract_abstract(abstract: Any) -> str | None:
    if abstract is None:
        return None
    if isinstance(abstract, str):
        return abstract.strip() or None
    if isinstance(abstract, dict):
        text = abstract.get("text")
        if isinstance(text, str):
            return text.strip() or None
    return None


def _fetch_one(
    source: str,
    hgvs: str,
    cache: Cache,
) -> RawEvidence:
    key = f"{source}:{hgvs}:v1"
    cached = cache.get(key)
    if cached is not None:
        return _make_entry(source, hgvs, cached)

    payload = _fetch_with_retries(source, hgvs)

    if payload is None:
        if STRICT_FETCH:
            raise FetchError(f"Source {source} unavailable for {hgvs}")
        return _make_empty_entry(source, hgvs)

    cache.set(key, payload)
    return _make_entry(source, hgvs, payload)


def _fetch_with_retries(source: str, hgvs: str) -> dict[str, Any] | None:
    for attempt in range(FETCH_RETRIES):
        try:
            return _fetch_source(source, hgvs)
        except (requests.RequestException, ConnectionError, ValueError) as exc:
            logger.warning(
                "Fetch attempt %d for %s failed: %s", attempt + 1, source, exc
            )
            if attempt < FETCH_RETRIES - 1:
                time.sleep(2 ** attempt)

    return None


def _fetch_source(source: str, hgvs: str) -> dict[str, Any]:
    url = _BASE_URLS[source]
    params = _params_for(source, hgvs)
    return _http_get_json(url, params=params, timeout=FETCH_TIMEOUT)


def _params_for(source: str, hgvs: str) -> dict[str, str]:
    if source == "clinvar":
        return {"q": hgvs, "fields": "clinvar", "size": "1"}
    if source == "gnomad":
        return {"query": hgvs}
    if source == "pubmed":
        return {"db": "pubmed", "term": hgvs, "retmode": "json", "retmax": "20"}
    return {}


def _http_get_json(
    url: str,
    params: dict[str, str] | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _make_entry(
    source: str,
    hgvs: str,
    payload: dict[str, Any],
) -> RawEvidence:
    canonical = json.dumps(payload, sort_keys=True)
    response_hash = hashlib.sha256(canonical.encode()).hexdigest()
    return RawEvidence(
        source=source,
        version=None,
        query=hgvs,
        retrieved_at=_now_iso(),
        endpoint=_BASE_URLS[source],
        response_hash=response_hash,
        payload=payload,
    )


def _make_empty_entry(source: str, hgvs: str) -> RawEvidence:
    return RawEvidence(
        source=source,
        version=None,
        query=hgvs,
        retrieved_at=_now_iso(),
        endpoint=_BASE_URLS[source],
        response_hash="",
        payload=None,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
