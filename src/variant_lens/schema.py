"""
Data models for VariantLens.

Defines the types used across the pipeline. No logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class VariantType(Enum):
    SNV = "snv"
    INDEL = "indel"
    SV = "sv"
    CNV = "cnv"
    UNKNOWN = "unknown"


class AfStatus(Enum):
    KNOWN = "known"
    NOT_IN_GNOMAD = "not_in_gnomad"
    SOURCE_UNAVAILABLE = "source_unavailable"


class ScopeStatus(Enum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE_COMMON = "common"
    OUT_OF_SCOPE_TYPE = "unsupported"
    UNCERTAIN = "uncertain"


class EvidenceAvailability(Enum):
    FULL = "full"
    PARTIAL = "partial"
    MINIMAL = "minimal"


class EvidenceState(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class RetrievalStrategy(Enum):
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"


class WarningCode(Enum):
    W001 = "W001"
    W002 = "W002"
    W101 = "W101"
    W102 = "W102"
    W103 = "W103"
    W104 = "W104"
    W105 = "W105"
    W201 = "W201"
    W202 = "W202"
    W301 = "W301"


@dataclass(frozen=True)
class Warning:
    code: WarningCode
    message: str
    severity: Literal["info", "warning", "error"]
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class Provenance:
    source: str
    version: str | None
    retrieved_at: str
    url: str | None


@dataclass(frozen=True)
class RawEvidence:
    source: str
    version: str | None
    query: str
    retrieved_at: str
    endpoint: str
    response_hash: str
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class ParsedVariant:
    input_variant: str
    normalized_hgvs: str | None
    gene: str | None
    variant_type: VariantType
    is_parseable: bool
    is_supported: bool
    warnings: list[Warning] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    parsed: ParsedVariant
    scope_status: ScopeStatus
    af_status: AfStatus
    allele_frequency: float | None
    evidence_availability: EvidenceAvailability
    warnings: list[Warning] = field(default_factory=list)
    provenance: dict[str, Provenance] = field(default_factory=dict)


@dataclass(frozen=True)
class AnnotationResult:
    validation: ValidationResult
    evidence_state: EvidenceState
    gene: str | None
    hgvs_c: str | None
    hgvs_p: str | None
    clinvar_significance: str | None
    clinvar_review_status: str | None
    clinvar_variation_id: str | None
    phenotype: str | None
    gnomad_af: float | None
    raw_evidence: list[RawEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class Passage:
    pmid: str
    title: str
    abstract: str | None
    year: int | None
    source: Literal["pubmed"] = "pubmed"


@dataclass(frozen=True)
class RankedPassage:
    passage: Passage
    retrieval_score: float | None
    rerank_score: float | None
    rank: int
