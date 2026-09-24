# Design Notes

This document describes the design principles behind VariantLens and
the reasoning behind key implementation decisions. It complements
`architecture.md` and `evaluation.md` and is intended for readers who
need to understand the structure and design constraints of the code
before extending it.

It is not a usage guide. Instructions for using VariantLens are
provided in the main README.

---

## 1. Interface design

The pipeline is organised as a set of independent modules with small,
explicit interfaces. Each module has a defined responsibility and
communicates with the rest of the pipeline through a limited data
contract.

- `parse` accepts a variant string and returns a structured
  representation.
- `scope` accepts a parsed variant and returns scope and
  allele-frequency information.
- `fetch` handles external data sources and returns raw evidence.
- `annotate` combines the outputs of the preceding components into a
  unified result.
- `retrieve` accepts a query and a collection of passages and returns
  them in ranked order.
- `report` serialises the final result as JSON.
- `cli` provides the entry point and coordinates the pipeline
  components.

In addition to these pipeline modules, the package contains modules
dedicated to evaluation data (`clinvar`, `clinvar_bulk`, `golden`) and
to shared concerns (`schema`, `config`, `cache`, `warnings`).

Each module has a corresponding test file. Network-dependent
operations are isolated behind mocks, so the suite runs without
internet access and finishes in a few seconds.

This separation keeps external dependencies, data processing,
retrieval, and presentation distinct. Individual components are
easier to test and modify as a result.

---

## 2. Data layer for evaluation

The evaluation data layer combines two complementary sources.

The first is ClinVar. The bulk tables published by NCBI are processed
in a streaming manner, and only records matching the variants in the
source table are retained. This avoids loading the complete summary
table into memory, despite its several-million-row scale.

The second source is PubMed. For each variant, queries based on gene,
HGVS notation, and phenotype retrieve a broader set of publications.
These publications form part of the candidate corpus but are not
considered relevant unless they satisfy the variant-specific matching
criteria.

The two sources serve different roles. ClinVar provides the reference
set against which retrieval metrics are calculated. PubMed supplies
additional publications that introduce non-relevant results into the
retrieval task.

---

## 3. Matching variant identifiers

The same variant may be represented differently across biomedical
data sources. ClinVar may use a shortened representation for a
deletion, while a project's internal table may retain a more explicit
HGVS form. Publications may also use historical or commonly recognised
variant names that differ substantially from HGVS notation.

Variant matching is handled through two complementary mechanisms.

The first is tolerant HGVS matching. For each variant, the pipeline
generates two lookup keys: the exact HGVS representation and a
shortened form. This accommodates differences in representation
between sources while retaining an explicit matching rule.

The second mechanism is the alias field in the variants table.
Commonly used variant names can be recorded as aliases and are
considered alongside HGVS tokens when determining whether a
publication is relevant to a given variant.

Both mechanisms are intentionally conservative. The pipeline does not
attempt to infer the identity of an ambiguous variant automatically.
Ambiguous cases are recorded and reported rather than resolved
through an unsupported assumption.

---

## 4. Network behaviour

External data access is required for parts of the pipeline, but
network-dependent operations are isolated and controlled.

- All external requests pass through a dedicated fetch layer.
- Responses are cached locally, so repeated execution of the same
  query reuses previously retrieved data without another network
  request.
- PubMed requests are batched and paced below the documented request
  limit.
- A failure affecting an individual source does not terminate the
  entire pipeline. The failure is recorded and included in the
  reported output.

This design separates network behaviour from the rest of the
processing pipeline. Failures in external services are handled
without obscuring the status of the remaining computation.

---

## 5. Determinism

The benchmark is designed to produce the same results when run with
the same inputs and configuration. This relies on three design
choices.

- Evaluation inputs are stored as versioned files rather than
  obtained exclusively through live queries.
- The retrieval algorithms used by the benchmark are deterministic.
- Corpus embeddings are computed once and reused across queries
  within a benchmark run.

Deterministic evaluation matters because the benchmark compares
retrieval strategies. Changes in the result should reflect changes in
the method or the input configuration rather than variation between
runs.

---

## 6. Reporting

Benchmark output follows a fixed JSON structure.

- `metadata` records the size of the golden set, the number of
  eligible variants, the corpus size, and the retrieval depth.
- `per_variant` records the size of the reference set and candidate
  list for each variant.
- `strategies` contains summary metrics and per-query results for each
  retrieval strategy.

Benchmark results are stored in the repository and regenerated
automatically when the retrieval code or golden set changes. Each
result is tied to the exact version of the code and data that
produced it.

---

## 7. Scope and limitations

VariantLens is a research software tool. It is not validated for
clinical use and does not perform clinical classification or provide
clinical decision support. The evaluation measures retrieval
performance against an externally sourced reference set. It does not
establish the correctness of a clinical interpretation.

The current golden set is limited in size, and its relevance labels
are binary. These constraints limit the scope of the current
evaluation and are documented as areas for future development.

---

## 8. Extending the pipeline

The pipeline is designed so that common extensions remain local to
the components they affect.

Adding a new annotation source requires three changes. The source is
registered in the fetch layer together with its endpoint and
parameter builder. Its fields are incorporated into the annotation
result. If it provides linked publications, those publications are
passed to the evidence builder.

Adding a new retrieval strategy requires two changes. A new member is
added to the strategy enumeration, and a function implementing the
same interface as the existing strategies is provided. The benchmark
discovers the strategy automatically.

Adding a new variant to the golden set requires a single data change:
a new row in the variants table. The existing evidence-building
process handles the remaining steps.

In each case, the required changes remain local to the relevant
components. Unrelated parts of the pipeline do not need to be
modified.

---

## 9. What is intentionally not included

Several capabilities were considered but deliberately excluded from
the current version.

- Automatic resolution of ambiguous variant identifiers.
- Graded relevance judgments, which would require additional manual
  curation.
- Integration with clinical decision-support systems.
- Support for structural variants or copy-number variants.

These exclusions are documented to make the current design boundary
explicit. They distinguish deliberate scope decisions from
functionality that has not yet been implemented.
