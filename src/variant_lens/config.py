"""
Default configuration for VariantLens.

Values are grouped into categories: paths and caching, fetch behaviour,
retrieval parameters, and logging. Environment variables override the
defaults so that deployments and tests can adjust behaviour without
editing this file.

Standard endpoint URLs and ClinVar file names are not listed here.
They describe external contracts, not tunable behaviour, and are kept
next to the modules that use them.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    value = os.environ.get(key)
    return float(value) if value is not None else default


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    return int(value) if value is not None else default


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _env_path(key: str, default: Path) -> Path:
    value = os.environ.get(key)
    return Path(value) if value is not None else default


AF_THRESHOLD: float = _env_float("VARIANT_LENS_AF_THRESHOLD", 0.001)

_default_cache_dir = Path.home() / ".cache" / "variant-lens"
CACHE_DIR: Path = _env_path("VARIANT_LENS_CACHE_DIR", _default_cache_dir)

CACHE_TTL_GNOMAD: int = _env_int("VARIANT_LENS_CACHE_TTL_GNOMAD", 7 * 24 * 3600)
CACHE_TTL_CLINVAR: int = _env_int("VARIANT_LENS_CACHE_TTL_CLINVAR", 24 * 3600)
CACHE_TTL_PUBMED: int = _env_int("VARIANT_LENS_CACHE_TTL_PUBMED", 7 * 24 * 3600)

RETRIEVAL_STRATEGY: str = _env_str("VARIANT_LENS_RETRIEVAL_STRATEGY", "hybrid")
TOP_K: int = _env_int("VARIANT_LENS_TOP_K", 50)
RERANK_TOP_K: int = _env_int("VARIANT_LENS_RERANK_TOP_K", 10)
RERANK_CONFIDENCE_THRESHOLD: float = _env_float(
    "VARIANT_LENS_RERANK_CONFIDENCE_THRESHOLD", 0.5
)

STRICT_FETCH: bool = _env_bool("VARIANT_LENS_STRICT_FETCH", False)
FETCH_RETRIES: int = _env_int("VARIANT_LENS_FETCH_RETRIES", 3)
FETCH_TIMEOUT: int = _env_int("VARIANT_LENS_FETCH_TIMEOUT", 10)

LOG_LEVEL: str = _env_str("VARIANT_LENS_LOG_LEVEL", "INFO")

NCBI_TOOL: str = _env_str("NCBI_TOOL", "variant-lens")
NCBI_EMAIL: str = _env_str("NCBI_EMAIL", "")
NCBI_API_KEY: str = _env_str("NCBI_API_KEY", "")

PUBMED_PAUSE_WITHOUT_KEY: float = _env_float(
    "VARIANT_LENS_PUBMED_PAUSE_WITHOUT_KEY", 1.0
)
PUBMED_PAUSE_WITH_KEY: float = _env_float(
    "VARIANT_LENS_PUBMED_PAUSE_WITH_KEY", 0.3
)

PUBMED_BATCH_SIZE: int = _env_int("VARIANT_LENS_PUBMED_BATCH_SIZE", 50)
PUBMED_ATTEMPTS: int = _env_int("VARIANT_LENS_PUBMED_ATTEMPTS", 4)
PUBMED_BACKOFF_BASE: float = _env_float(
    "VARIANT_LENS_PUBMED_BACKOFF_BASE", 5.0
)

DEFAULT_PUBMED_CANDIDATES: int = _env_int(
    "VARIANT_LENS_PUBMED_CANDIDATES", 50
)


def pubmed_pause() -> float:
    """
    Return the sleep interval between PubMed requests.

    With an NCBI API key the documented rate limit rises from three to
    ten requests per second. The interval is shortened but remains well
    below the limit so that transient throttling stays rare.
    """
    return PUBMED_PAUSE_WITH_KEY if NCBI_API_KEY else PUBMED_PAUSE_WITHOUT_KEY
