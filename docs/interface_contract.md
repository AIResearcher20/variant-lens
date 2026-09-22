
---

VariantLens — Interface Contract

Version: 0.1.0 (MVP)
Status: Final draft
Date: [date]

---

1. Purpose

This document specifies the scope, expected behavior, and module interfaces of VariantLens. It serves as the reference for what the tool accepts, what it produces, and how its components interact. Changes to this contract require a version bump and an entry in CHANGELOG.md.

---

2. Scope Contract

2.1 In Scope (MVP)

VariantLens accepts and processes the following inputs:

· Variant types: SNVs and small indels (up to 50 bp)
· Genome build: GRCh38 (GRCh37 support is planned for Phase 2)
· Input format: HGVS nomenclature (e.g., BRCA1 c.68_69delAG) or VCF-style coordinates (chr17:43124028:CT:C)
· Allele frequency: gnomAD AF below 0.001
· Clinical significance: Pathogenic, Likely Pathogenic, Benign, and Likely Benign. Variants of Uncertain Significance (VUS) are processed and labeled; VariantLens does not attempt reclassification.

2.2 Out of Scope (MVP)

VariantLens does not support the following in the MVP:

· Structural variants (SV) and copy-number variants (CNV)
· Somatic variants (tumor-only or tumor-normal)
· Pharmacogenomic interpretation
· De novo variant interpretation without ClinVar context
· Clinical decision-making or diagnostic use
· Variants on non-primary chromosomes (alt contigs, decoys)

2.3 Behavioral and Reproducibility Guarantees

For supported inputs, VariantLens provides the following guarantees:

Guarantee Condition
Deterministic parsing Same input yields the same normalized HGVS
Explicit warnings Every degraded path emits a coded warning
Provenance Every fetched field traces to a source and timestamp
Reproducibility Same input, software version, model version, configuration, and cache state yield the same output
Graceful degradation Recoverable failures do not halt the pipeline; see §3.5

Reproducibility has two distinct forms, treated separately throughout this contract:

· Operational reproducibility. Achieved when the same software version, configuration, and cache state are reused. This is the default guarantee of the pipeline.
· Historical reproducibility. Achieved only when raw API responses, software version, configuration, and model versions are snapshotted and stored. This requires the --snapshot flag and is not guaranteed without it.

2.4 Non-Guarantees

VariantLens does not guarantee:

· Clinical validity of interpretations. Clinical interpretation is not validated for diagnostic or clinical decision-making.
· Performance on variants outside the benchmark distribution. See docs/evaluation.md.
· Completeness of literature retrieval. PubMed coverage varies by gene, variant, and publication date.
· Stability of external APIs. MyVariant.info, gnomAD, and PubMed may change independently of this tool.

---

3. Interface Contract

3.1 Pipeline Overview

```
User input (HGVS or chr:pos:ref:alt)
    │
    ▼
parse_variant          → ParsedVariant
    │
    ▼
fetch.get_raw_evidence → list[RawEvidence]
    │
    ▼
determine_scope        → ScopeStatus, AfStatus
    │
    ▼
annotate               → AnnotationResult
    │
    ▼
retrieve               → list[Passage]
    │
    ▼
rank                   → list[RankedPassage]
    │
    ▼
report                 → Report (JSON + HTML)
```

Parsing and scope determination are separated. parse_variant operates on the input string alone and is deterministic. determine_scope receives the parsed variant and the fetched evidence, and derives the scope from allele frequency and evidence availability. This separation allows most validation tests to run without network access.

3.2 Data Types

ParsedVariant

```python
@dataclass(frozen=True)
class ParsedVariant:
    input_variant: str
    normalized_hgvs: str | None
    gene: str | None
    variant_type: VariantType
    is_parseable: bool
    is_supported: bool
    warnings: list[Warning]
```

is_parseable and is_supported are independent. A CNV with valid syntax is parseable but not supported. A malformed HGVS string is neither.

VariantType (Enum)

```python
class VariantType(Enum):
    SNV = "snv"
    INDEL = "indel"
    SV = "sv"
    CNV = "cnv"
    UNKNOWN = "unknown"
```

AfStatus (Enum)

```python
class AfStatus(Enum):
    KNOWN = "known"
    NOT_IN_GNOMAD = "not_in_gnomad"
    SOURCE_UNAVAILABLE = "source_unavailable"
```

The three values correspond to three distinct epistemic states:

Value Meaning Consequence in scope
KNOWN Allele frequency is present in gnomAD IN_SCOPE or OUT_OF_SCOPE_COMMON, depending on the value
NOT_IN_GNOMAD No gnomAD record exists for this variant IN_SCOPE; absence of record is treated as evidence of rarity
SOURCE_UNAVAILABLE gnomAD was not reachable, or returned no usable response UNCERTAIN; absence of evidence is not evidence of absence

The distinction between NOT_IN_GNOMAD and SOURCE_UNAVAILABLE matters. The first states that we know the variant is not present in a reference database. The second states that we do not know what the frequency is.

ScopeStatus (Enum)

```python
class ScopeStatus(Enum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE_COMMON = "common"
    OUT_OF_SCOPE_TYPE = "unsupported"
    UNCERTAIN = "uncertain"
```

Value Condition
IN_SCOPE Parseable, supported, and either AfStatus.KNOWN with AF below 0.001, or AfStatus.NOT_IN_GNOMAD
OUT_OF_SCOPE_COMMON AfStatus.KNOWN with AF at or above 0.001
OUT_OF_SCOPE_TYPE Parseable but not supported (SV, CNV, or unknown type)
UNCERTAIN AfStatus.SOURCE_UNAVAILABLE, or input that could not be parsed

EvidenceAvailability (Enum)

```python
class EvidenceAvailability(Enum):
    FULL = "full"
    PARTIAL = "partial"
    MINIMAL = "minimal"
```

This enum describes the availability of evidence from a domain perspective: whether allele frequency, ClinVar annotation, and phenotype are present. It is distinct from EvidenceState, which describes the outcome of fetch operations.

Value Condition
FULL AF, ClinVar, and phenotype are all available
PARTIAL One or two of the above are available
MINIMAL Parseable only; no downstream evidence

EvidenceState (Enum)

```python
class EvidenceState(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
```

This enum describes the outcome of the fetch layer: whether external sources responded.

Value Condition
COMPLETE All sources responded, and each returned data
PARTIAL At least one source responded, but at least one source returned no data or failed
UNAVAILABLE No source responded, and no cached data was available

EvidenceAvailability and EvidenceState describe different aspects of the same run. A run may have EvidenceState.COMPLETE (all sources responded) but EvidenceAvailability.MINIMAL (no field of interest was populated). The two are kept separate so that reports can state both facts without ambiguity.

Warning

```python
@dataclass(frozen=True)
class Warning:
    code: WarningCode
    message: str
    severity: Literal["info", "warning", "error"]
    context: dict[str, Any] | None = None
```

severity="error" denotes a pipeline-state error that affects downstream processing. It does not imply that a Python exception was raised. The validate module never raises for malformed input; it returns a ParsedVariant carrying the appropriate warning.

WarningCode (Enum)

Code Severity Trigger
W001 error HGVS parsing failed
W002 warning HGVS ambiguous (multiple normalizations)
W101 warning No gnomAD record
W102 warning No ClinVar record
W103 info No phenotype in ClinVar
W104 warning AF at or above threshold
W105 error Unsupported variant type (SV, CNV)
W201 info Few PubMed results (fewer than 5)
W202 warning Low rerank confidence (threshold defined in configuration)
W301 info VUS classification

Provenance

```python
@dataclass(frozen=True)
class Provenance:
    source: str
    version: str | None
    retrieved_at: str
    url: str | None
```

Provenance is used for high-level fields. For raw API responses, RawEvidence carries additional fields described below.

RawEvidence

```python
@dataclass(frozen=True)
class RawEvidence:
    source: str
    version: str | None
    query: str
    retrieved_at: str
    endpoint: str
    response_hash: str
    payload: dict[str, Any] | None
```

response_hash is a hash of the canonicalized API response. It exists for historical reproducibility: if the response is later re-fetched and the hash differs, the discrepancy is detectable.

ValidationResult

```python
@dataclass(frozen=True)
class ValidationResult:
    parsed: ParsedVariant
    scope_status: ScopeStatus
    af_status: AfStatus
    allele_frequency: float | None
    evidence_availability: EvidenceAvailability
    warnings: list[Warning]
    provenance: dict[str, Provenance]
```

This object is constructed after both parse_variant and determine_scope have run. It serves as the single record of the validation phase.

AnnotationResult

```python
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
    raw_evidence: list[RawEvidence]
```

Passage

```python
@dataclass(frozen=True)
class Passage:
    pmid: str
    title: str
    abstract: str | None
    year: int | None
    source: Literal["pubmed"] = "pubmed"
```

abstract and year are nullable because PubMed records are not guaranteed to contain either. When abstract is missing, the passage is retained for title-based matching, and a warning is recorded at the retrieval layer.

source is restricted to "pubmed" in the MVP. bioRxiv is deferred to Phase 2.

RankedPassage

```python
@dataclass(frozen=True)
class RankedPassage:
    passage: Passage
    retrieval_score: float | None
    rerank_score: float | None
    rank: int
```

retrieval_score and rerank_score are not directly comparable. Each score is defined only within the strategy or model that produced it. Cross-strategy comparisons require normalization, which is performed in the evaluation module, not here.

3.3 Module Contracts

parse.parse_variant(input: str) -> ParsedVariant

· Operates on the input string alone. No network access.
· Always returns a ParsedVariant, including for unparseable input.
· Never raises for malformed input. Uses warning W001 for parse failures and W105 for unsupported types.
· Deterministic: same input yields the same output.

scope.determine_scope(parsed: ParsedVariant, evidence: list[RawEvidence]) -> tuple[ScopeStatus, AfStatus]

· Receives the parsed variant and the fetched evidence. No direct network access.
· Derives AfStatus from the presence and success of gnomAD evidence.
· Derives ScopeStatus from AfStatus, parsed.is_supported, and parsed.is_parseable.
· Deterministic with respect to its inputs.

fetch.get_raw_evidence(hgvs: str) -> list[RawEvidence]

· Checks the local cache before issuing API calls.
· On timeout: retries three times with exponential backoff. If a cached response exists, the cached response is used, and its provenance is marked as stale. If no cached response exists, the source is skipped and a warning is recorded.
· Never raises for individual source failures. Returns an empty RawEvidence entry with payload=None for sources that did not respond.
· Raises FetchError only when the fetch layer itself is unusable, such as when the cache cannot be initialized. This is distinct from a source being unavailable.

annotate.annotate(parsed: ParsedVariant, evidence: list[RawEvidence]) -> AnnotationResult

· Requires a ParsedVariant with is_parseable=True and is_supported=True.
· Raises AnnotationError when is_parseable=False or is_supported=False. Downstream modules are not invoked in this case.
· Does not contact external APIs directly. Relies on the fetch layer.
· Sets EvidenceState based on the returned RawEvidence entries.

retrieve.retrieve(annotation: AnnotationResult, strategy: RetrievalStrategy) -> list[Passage]

```python
class RetrievalStrategy(Enum):
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID = "hybrid"
```

· Returns an empty list when no results are found, not None.
· Emits W201 when fewer than 5 results are returned.
· Passages with missing abstracts are retained and flagged in the passage metadata.

rank.rerank(query: str, passages: list[Passage]) -> list[RankedPassage]

· Stable ordering. Ties are broken by PMID.
· Emits W202 when the top-1 rerank score is below a configurable threshold. The default threshold is defined in config.py and revised after evaluation.
· Latency target: under 500 ms for 50 passages on CPU.

report.generate(annotation: AnnotationResult, ranked_passages: list[RankedPassage]) -> Report

· Succeeds when the input types are valid.
· If annotation.validation.parsed.is_parseable is False, the report contains the parse result and empty evidence sections.
· Output formats: JSON (canonical) and HTML (derived from JSON).
· JSON schema is defined in docs/schema/report.schema.json.

3.4 Cache Layer Contract

```python
class Cache:
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value: dict, ttl: int) -> None: ...
    def invalidate(self, key: str) -> None: ...
    def clear(self) -> None: ...
```

· Backend: SQLite (default), filesystem (fallback).
· Location: ~/.cache/variant-lens/ (respects XDG_CACHE_HOME).
· Key format: {source}:{identifier}:{version}.
· TTL: per source, defined in config.py. Default: 7 days for gnomAD, 1 day for ClinVar.
· Thread safety: file locking for concurrent access.

Cached responses are the mechanism through which operational reproducibility is achieved. When a cache entry expires and is refreshed, the output may differ from a previous run. This is expected, and is the reason historical reproducibility requires the --snapshot flag.

3.5 Error Handling Policy

Failures are divided into two categories.

Recoverable failures. These do not halt the pipeline. They emit coded warnings, and downstream modules continue with reduced evidence.

Situation Behavior
No gnomAD record W101; AfStatus.NOT_IN_GNOMAD; ScopeStatus.IN_SCOPE
gnomAD source unavailable W101; AfStatus.SOURCE_UNAVAILABLE; ScopeStatus.UNCERTAIN
No ClinVar record W102; continue; clinical significance remains None
No phenotype in ClinVar W103; continue; query falls back to HGVS-only
API timeout with cached response Use cached response; mark provenance as stale
API timeout without cached response Retry three times; on continued failure, skip source and warn
Empty retrieval W201; report with empty evidence section
Rerank model failure Fall back to retrieval scores; W202
Fewer than 5 retrieval results W201; continue

Fatal input validation failures. These stop downstream processing. The report is still generated and contains the validation failure.

Situation Behavior
Malformed HGVS W001; is_parseable=False; downstream skipped
Unsupported variant type W105; is_parseable=True, is_supported=False; downstream skipped
Ambiguous HGVS W002; pipeline continues with the primary normalization

Recoverable failures preserve the pipeline and reduce the evidence surface. Fatal input failures prevent annotation entirely. Both are reported.

When strict_fetch=True is set in configuration, a source that is unavailable causes a FetchError to be raised instead of being recorded as AfStatus.SOURCE_UNAVAILABLE. This flag exists for callers who require fail-fast behavior. The default is False.

3.6 Snapshot Mode

When invoked with --snapshot, the pipeline records the following items alongside the report:

· Raw API responses (RawEvidence.payload for each source)
· response_hash for each response
· Software version (variant_lens.__version__)
· Effective configuration
· Retrieval and reranking configuration
· Model names and versions, where applicable

These items are written to a snapshot/ directory next to the report. Snapshot mode is implemented in the MVP. Its automated tests are deferred to Phase 2 to avoid overloading the MVP CI pipeline.

---

4. Versioning

· Contract version: 0.1.0 (MVP)
· Breaking changes: require a major version bump
· New warnings: minor version bump
· Documentation updates: patch version bump

---

5. Open Questions

The following items remain undecided and will be resolved before Phase 2.

1. Negative caching. Whether to cache negative results such as "not present in gnomAD." A short TTL of one day is the working assumption.
2. Batched reranking. Whether rank should support batched inference. This becomes relevant once BioGPT-ClinVar is integrated.
3. Rerank confidence threshold. The default value for W202 will be determined empirically after the first benchmark run.

---

6. References

· ACMG/AMP guidelines for variant classification. Referenced as background for ClinVar clinical significance terminology only. VariantLens does not perform ACMG/AMP classification.
· HGVS nomenclature, version 21.0.
· MyVariant.info API documentation.
· gnomAD v4 documentation.

---
