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
from .schema import RawEvidence


logger = logging.getLogger(__name__)


_SOURCES = ("gnomad", "clinvar", "pubmed")

_BASE_URLS = {
    "gnomad": "https://gnomad.broadinstitute.org/api",
    "clinvar": "https://myvariant.info/v1/query",
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
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


def _fetch_one(
    source: str,
    hgvs: str,
    cache: Cache,
) -> RawEvidence:
    key = f"{source}:{hgvs}:v1"
    cached = cache.get(key)
    if cached is not None:
        return _make_entry(source, hgvs, cached, from_cache=True)

    payload = _fetch_with_retries(source, hgvs)

    if payload is None:
        if STRICT_FETCH:
            raise FetchError(f"Source {source} unavailable for {hgvs}")
        return _make_empty_entry(source, hgvs)

    cache.set(key, payload)
    return _make_entry(source, hgvs, payload, from_cache=False)


def _fetch_with_retries(source: str, hgvs: str) -> dict[str, Any] | None:
    for attempt in range(FETCH_RETRIES):
        try:
            return _fetch_source(source, hgvs)
        except (requests.RequestException, ValueError) as exc:
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
    from_cache: bool,
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
