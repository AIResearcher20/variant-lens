"""
Fetch raw evidence from public APIs.

Contacts MyVariant.info, gnomAD, and PubMed. Uses the local cache first.
Never raises for individual source failures. Raises FetchError only when
the fetch layer itself cannot operate.

PubMed requests are paced conservatively and retried on transient
failures. Pacing, batching, and retry parameters are read from config
so that they can be adjusted without editing this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import requests

from .cache import Cache
from .config import (
    FETCH_RETRIES,
    FETCH_TIMEOUT,
    STRICT_FETCH,
    PUBMED_ATTEMPTS,
    PUBMED_BACKOFF_BASE,
    PUBMED_BATCH_SIZE,
    pubmed_pause,
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
    pmids = _pubmed_search(query, max_results)
    if not pmids:
        return []
    return fetch_pubmed_abstracts_by_pmids(pmids)


def fetch_pubmed_abstracts_by_pmids(pmids: list[str]) -> list[Passage]:
    """
    Fetch abstracts for a known list of PMIDs.

    The identifiers are split into batches so that the request URL stays
    within the length that NCBI accepts. Results are cached per batch,
    so a second run over the same identifiers does not touch the network.
    """
    if not pmids:
        return []

    cache = Cache()
    passages: list[Passage] = []
    pause = pubmed_pause()

    for start in range(0, len(pmids), PUBMED_BATCH_SIZE):
        batch = pmids[start:start + PUBMED_BATCH_SIZE]
        batch_key = "pubmed:batch:" + ",".join(sorted(batch))
        cached = cache.get(batch_key)
        if cached is not None:
            for item in cached.get("passages", []):
                passages.append(Passage(**item))
            continue

        batch_passages = _fetch_batch(batch)
        cache.set(batch_key, {
            "passages": [
                {
                    "pmid": p.pmid,
                    "title": p.title,
                    "abstract": p.abstract,
                    "year": p.year,
                }
                for p in batch_passages
            ]
        })
        passages.extend(batch_passages)
        time.sleep(pause)

    return passages


def _pubmed_search(query: str, max_results: int) -> list[str]:
    cache = Cache()
    key = f"pubmed:search:{query}:{max_results}"
    cached = cache.get(key)
    if cached is not None:
        return cached.get("pmids", [])

    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(max_results),
    }

    payload = _request_with_retry(
        _BASE_URLS["pubmed"],
        params=params,
        timeout=FETCH_TIMEOUT,
        expect_json=True,
    )
    if payload is None:
        return []

    pmids = list(payload.get("esearchresult", {}).get("idlist", []))
    cache.set(key, {"pmids": pmids})
    return pmids


def _fetch_batch(pmids: list[str]) -> list[Passage]:
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }

    text = _request_with_retry(
        _BASE_URLS["pubmed_fetch"],
        params=params,
        timeout=FETCH_TIMEOUT * 2,
        expect_json=False,
    )
    if text is None:
        return []

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        logger.warning("PubMed XML parse failed: %s", exc)
        return []

    passages: list[Passage] = []
    for article in root.findall(".//PubmedArticle"):
        passage = _parse_pubmed_article(article)
        if passage is not None:
            passages.append(passage)

    return passages


def _request_with_retry(
    url: str,
    params: dict[str, str],
    timeout: int,
    expect_json: bool,
) -> Any:
    for attempt in range(1, PUBMED_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code in (429, 500, 502, 503, 504):
                wait = PUBMED_BACKOFF_BASE * attempt
                logger.warning(
                    "NCBI returned %d on attempt %d, waiting %.1f seconds",
                    response.status_code,
                    attempt,
                    wait,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("request attempt %d failed: %s", attempt, exc)
            if attempt == PUBMED_ATTEMPTS:
                return None
            time.sleep(PUBMED_BACKOFF_BASE * attempt)
            continue

        if expect_json:
            try:
                return response.json()
            except ValueError as exc:
                logger.warning("response was not JSON: %s", exc)
                return None
        return response.text

    return None


def _parse_pubmed_article(article: ET.Element) -> Passage | None:
    pmid = _text(article, ".//PMID")
    if not pmid:
        return None

    title = _text(article, ".//ArticleTitle") or ""

    abstract_parts: list[str] = []
    for abstract_node in article.findall(".//AbstractText"):
        text = "".join(abstract_node.itertext()).strip()
        label = abstract_node.attrib.get("Label")
        if label and text:
            abstract_parts.append(f"{label}: {text}")
        elif text:
            abstract_parts.append(text)

    abstract = " ".join(abstract_parts).strip() or None

    year = _extract_year(_text(article, ".//PubDate/Year"))

    return Passage(
        pmid=pmid,
        title=title,
        abstract=abstract,
        year=year,
    )


def _text(node: ET.Element, path: str) -> str | None:
    element = node.find(path)
    if element is None:
        return None
    return "".join(element.itertext()).strip() or None


def _extract_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    for token in value.split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return None


def _fetch_one(source: str, hgvs: str, cache: Cache) -> RawEvidence:
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


def _make_entry(source: str, hgvs: str, payload: dict[str, Any]) -> RawEvidence:
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
