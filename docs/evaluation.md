# Evaluation

Version: 0.2.0
Status: Draft


This document describes the evaluation design for VariantLens. It defines
the golden set, the baselines, the metrics, and the reporting format. It
does not describe the implementation of the evaluation runner; that is
covered in `architecture.md`, section 4.

---

## 1. Purpose

Evaluation in VariantLens serves two purposes.

First, it establishes whether the system performs better than simpler
retrieval strategies. A hybrid retrieval pipeline with a reranker is more
complex than a keyword search. The evaluation must show that the added
complexity is justified.

Second, it provides a reproducible reference point. Any change to the
retrieval strategy, the embedding model, or the reranker must be evaluated
against the same golden set and the same metrics. Without this, changes
cannot be compared.

The evaluation is not intended to measure clinical validity. It measures
retrieval quality against a hand-curated set of variant–passage pairs.

---

## 2. Golden Set

### 2.1 Composition

The golden set is a collection of rare Mendelian variants with manually
selected evidence passages.

MVP target: 10 variants. Phase 2 target: 50 variants.

Each entry contains:

- A variant identifier (HGVS or chr:pos:ref:alt)
- Gene symbol
- Clinical significance from ClinVar
- ClinVar review status (at least two stars)
- gnomAD allele frequency (below 0.001)
- Phenotype from ClinVar, when available
- Five to ten PubMed passages selected as relevant

The passages are selected by reading the abstracts and confirming that the
passage directly addresses the variant, the gene, or the phenotype in a
way that would be useful for interpretation. Passages that merely mention
the gene name are not selected.

### 2.2 Selection Criteria

| Criterion | Requirement |
|---|---|
| Variant type | SNV or small indel |
| Genome build | GRCh38 |
| gnomAD AF | below 0.001 |
| ClinVar review status | at least two stars |
| Clinical significance | Pathogenic, Likely Pathogenic, Benign, or Likely Benign |
| PubMed coverage | at least five relevant passages |
| Gene diversity | no more than two variants from the same gene |

The gene diversity constraint is intended to prevent the golden set from
being dominated by a single well-studied gene.

### 2.3 Distribution

The golden set is balanced across clinical significance.

| Label | Count (MVP) | Count (Phase 2) |
|---|---|---|
| Pathogenic or Likely Pathogenic | 5 | 25 |
| Benign or Likely Benign | 5 | 25 |

Variants of Uncertain Significance are not included.

### 2.4 Storage

The golden set is stored in `data/gold_standard/`.
