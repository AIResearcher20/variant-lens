Architecture

Version: 0.1.0 (MVP)
Status: Draft
Date: 2026

This document describes the implementation architecture of VariantLens. It complements the Interface Contract, which specifies behavior and interfaces. This document specifies structure, data flow, and technical decisions.

---

1. Design Principles

1. Local-first. No raw sequencing data leaves the user's environment.
2. Modular. Each component is independently testable.
3. Reproducible. Every run produces a structured artifact.
4. Comparable. Baselines are part of the pipeline, not an afterthought.

---

2. Repository Structure

```
variant-lens/
├── README.md
├── LICENSE
├── NOTICE
├── CITATION.cff
├── pyproject.toml
├── Dockerfile
├── .dockerignore
├── .gitignore
├── docs/
│   ├── interface_contract.md
│   ├── architecture.md
│   └── evaluation.md
├── src/
│   └── variant_lens/
│       ├── __init__.py
│       ├── schema.py
│       ├── warnings.py
│       ├── parse.py
│       ├── scope.py
│       ├── fetch.py
│       ├── cache.py
│       ├── annotate.py
│       ├── retrieve/
│       │   ├── __init__.py
│       │   ├── bm25.py
│       │   ├── dense.py
│       │   └── hybrid.py
│       ├── rank.py
│       ├── report.py
│       └── cli.py
├── data/
│   └── gold_standard/
│       ├── README.md
│       ├── variants.csv
│       └── evidence/
├── scripts/
│   └── benchmark.py
└── tests/
    ├── __init__.py
    ├── test_parse.py
    ├── test_scope.py
    ├── test_fetch.py
    ├── test_retrieve.py
    ├── test_rank.py
    └── test_report.py
```

Two decisions worth noting.

eval/ is not inside the package. Evaluation is a script that uses the package, not part of it. This keeps the package lean and keeps evaluation dependencies out of the production install.

Tests are written before implementation. Each test file corresponds to a module in the Interface Contract and is written against the contract, not the code.

---

3. Data Flow

```
User input (HGVS or chr:pos:ref:alt)
    │
    ▼
parse.parse_variant
    │  ParsedVariant
    ▼
fetch.get_raw_evidence
    │  list[RawEvidence]
    ▼
scope.determine_scope
    │  ScopeStatus, AfStatus
    ▼
annotate.annotate
    │  AnnotationResult
    ▼
retrieve.retrieve
    │  list[Passage]
    ▼
rank.rerank
    │  list[RankedPassage]
    ▼
report.generate
    │
    ▼
Output (JSON + HTML)
```

Each stage receives the output of the previous stage and produces a single typed artifact. No stage calls another stage directly. The CLI orchestrates them.

---

4. Module Responsibilities

parse.py

Pure function. No I/O. Takes a string, returns a ParsedVariant. Handles HGVS and VCF-style coordinates. Emits W001 on parse failure and W105 on unsupported type.

Test file: tests/test_parse.py, network-free.

scope.py

Takes a ParsedVariant and a list of RawEvidence. Returns ScopeStatus and AfStatus. No network access. The logic here is where the three-state AfStatus is computed.

Test file: tests/test_scope.py, network-free.

fetch.py

Contacts MyVariant.info, gnomAD, and PubMed. Checks the cache first. On timeout, retries three times with exponential backoff. Never raises for individual source failures. Raises FetchError only when the fetch layer itself cannot operate, for example when the cache directory cannot be created.

Test file: tests/test_fetch.py, uses mocks.

cache.py

SQLite-backed cache. Key format {source}:{identifier}:{version}. TTL per source, defined in config. Thread-safe via file locking.

annotate.py

Merges the output of parse, scope, and fetch into an AnnotationResult. Does not contact external APIs. Raises AnnotationError if the input is not parseable or not supported.

retrieve/

Three strategies: BM25, dense, hybrid.

· bm25.py uses rank_bm25. No model.
· dense.py uses PubMedBERT embeddings and ChromaDB. ChromaDB is chosen over FAISS because the expected scale, a few thousand passages, does not justify FAISS index management overhead. The retrieval interface abstracts the backend, so FAISS can be added later if scale demands it.
· hybrid.py combines both via reciprocal rank fusion.

rank.py

Cross-encoder reranking. In the MVP, this uses a cross-encoder model. In Phase 2, BioGPT-ClinVar replaces it as a cross-encoder. The interface does not change between MVP and Phase 2.

report.py

Generates JSON (canonical) and HTML (from JSON). HTML uses Jinja2. JSON schema lives in docs/schema/report.schema.json.

cli.py

Typer-based CLI. The single entry point. Orchestrates the pipeline. This is the only place where stages are wired together.

---

5. Technical Decisions

5.1 ChromaDB over FAISS

The expected scale in the MVP is a few thousand passages. ChromaDB provides persistence, metadata filtering, and a simpler API. FAISS offers better raw speed at larger scale, but that speed is not needed here. The retrieval interface is written so that the backend can be swapped without changing the calling code.

5.2 Cross-encoder in MVP, BioGPT-ClinVar in Phase 2

BioGPT-ClinVar is a generative model, not a reranker. Using it as a cross-encoder requires either a classification head or a perplexity-based scoring scheme. Both are feasible but neither is trivial. The MVP uses a standard cross-encoder to keep the scope bounded. Phase 2 replaces it with BioGPT-ClinVar once the evaluation harness exists to compare them.

This decision matters for the narrative. If BioGPT-ClinVar is used in the MVP and does not outperform a standard cross-encoder, the story weakens. Doing the comparison in Phase 2, with a baseline to compare against, is the safer path.

5.3 PubMed as the only retrieval source in MVP

bioRxiv and medRxiv are deferred to Phase 2. PubMed has a stable API, predictable rate limits, and sufficient coverage for the MVP's scope.

5.4 Snapshot as a flag in MVP, tested in Phase 2

The --snapshot flag is implemented in the MVP. It writes raw API responses, hashes, effective configuration, and model versions to a snapshot/ directory next to the report. Its automated tests are deferred to Phase 2 to avoid overloading the MVP CI pipeline.

5.5 Tests before implementation

Tests for parse.py and scope.py are written before those modules are implemented. Both modules are pure and network-free, which makes this straightforward. Tests for fetch.py use mocks. Tests for retrieve.py and rank.py use small fixtures.

---

6. Configuration

A single config.py module holds defaults. Environment variables override the defaults. No YAML config file in the MVP. This is deferred until the tool has enough options to justify it.

Configuration items include:

· AF_THRESHOLD, default 0.001
· CACHE_DIR, default ~/.cache/variant-lens/
· CACHE_TTL_GNOMAD, default 7 days
· CACHE_TTL_CLINVAR, default 1 day
· RETRIEVAL_STRATEGY, default hybrid
· TOP_K, default 50
· RERANK_TOP_K, default 10
· RERANK_CONFIDENCE_THRESHOLD, default determined empirically in Phase 2
· STRICT_FETCH, default False

---

7. Logging

Standard Python logging. No third-party logging library. Log level is set via VARIANT_LENS_LOG_LEVEL. Default level: INFO.

Logs go to stderr. Reports go to the output path.

---

8. Packaging

pyproject.toml defines the package. pip install -e . for development. pip install git+https://github.com/AIResearcher20/variant-lens.git for users before PyPI release.

A Dockerfile is provided in the repository root. The image installs the package and its dependencies, and exposes the variant-lens CLI as the entry point.

Optional dependencies:

· [dev] for development: pytest, ruff, mypy
· [eval] for evaluation: to be defined in Phase 2

---

9. CI

GitHub Actions runs on push and pull request:

· Lint with ruff
· Type check with mypy
· Test with pytest
· Build the package
· Build the Docker image

CI is defined in .github/workflows/ci.yml. It does not run network-dependent tests.

---

10. What Is Not in the MVP

The following are explicitly excluded from the MVP and reserved for later phases.

· SV/CNV support
· Multilingual prompts
· GPU acceleration
· Batched reranking
· bioRxiv and medRxiv retrieval
· Web UI
· PyPI release

---

11. Open Questions

1. Whether the retrieval interface should expose the backend explicitly, so that --backend faiss works, or keep it internal. Current leaning: keep it internal until there is a second backend.
2. Whether negative caching, for example "not present in gnomAD", should be enabled by default. Current leaning: yes, with a 1-day TTL.
3. Whether rank.py should support batched inference in the MVP. Current leaning: no. Single-pass is fast enough at this scale.

---

12. References

· Interface Contract: docs/interface_contract.md
· Evaluation design: docs/evaluation.md (to be written)
· HGVS nomenclature: version 21.0
· MyVariant.info API documentation
· gnomAD v4 documentation
