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

```

data/gold_standard/
├── README.md
├── variants.csv
└── evidence/
├── <variant_id>.json
└── ...

```

`variants.csv` contains one row per variant:

```

variant_id, gene, hgvs, chr, pos, ref, alt, af_gnomad,
clinvar_significance, clinvar_review, phenotype

```

Each `<variant_id>.json` file contains the manually selected passages:

```json
{
  "variant_id": "...",
  "query": "...",
  "relevant_pmids": ["...", "..."],
  "notes": "..."
}
```

The notes field records why a passage was selected.

---

3. Baselines

Three retrieval strategies are evaluated.

3.1 BM25

Keyword search over passage titles and abstracts. No embeddings, no
reranking. This represents the simplest reasonable approach.

Implementation: rank_bm25, default parameters.

3.2 Dense

Dense retrieval using PubMedBERT embeddings and cosine similarity. No
reranking. This isolates the contribution of the embedding model.

Implementation: sentence-transformers with pritamdeka/S-PubMedBert-MS-MARCO.
The corpus is kept in memory; no external vector store is required for the
current scale.

When sentence-transformers is not installed, dense retrieval returns an
empty list. This is the expected behaviour in CI.

3.3 Hybrid

Combines BM25 and dense retrieval via Reciprocal Rank Fusion (RRF).

The RRF score for a passage is the sum of 1/(k + rank) over all lists it
appears in. The default k is 60.

When dense retrieval is unavailable, hybrid falls back to BM25.

---

4. Metrics

Four metrics are computed for each strategy.

4.1 Recall@K

The fraction of relevant passages that appear in the top K retrieved
passages.

```
Recall@K = |relevant ∩ retrieved@K| / |relevant|
```

Computed for K = 5 and K = 10.

4.2 Mean Reciprocal Rank (MRR)

The mean of the reciprocal of the rank of the first relevant passage.

```
MRR = (1/|Q|) Σ (1 / rank_i)
```

where rank_i is the rank of the first relevant passage for query i.

4.3 Normalized Discounted Cumulative Gain (nDCG@10)

A ranking-aware metric that gives more weight to relevant passages at
higher ranks.

```
DCG@K = Σ (2^rel_i - 1) / log2(i + 1)
nDCG@K = DCG@K / IDCG@K
```

with binary relevance: rel_i = 1 if the passage is in the golden set, 0
otherwise. IDCG is the ideal DCG.

4.4 Query-level Results

Per-query results are recorded alongside aggregate metrics. This makes it
possible to identify queries where a strategy underperforms.

---

5. Evaluation Protocol

5.1 Query Construction

For each variant, the query is read from the evidence file:

```
query = gene + " " + hgvs + " " + phenotype
```

If phenotype is not available, the query falls back to gene and hgvs.

5.2 Retrieval

For each strategy, the top 50 passages are retrieved. This is the TOP_K
default in config.py.

For BM25 and dense, retrieval is the final step.

For hybrid, the top-k lists from BM25 and dense are fused via RRF.

5.3 Relevance Judgment

A passage is considered relevant if its PMID appears in the golden set's
relevant_pmids list. This is a binary judgment. Graded relevance is not
used in the MVP.

5.4 Reporting

Results are written to evaluation_results.json:

```json
{
  "metadata": {
    "golden_set_size": 10,
    "top_k": 50
  },
  "strategies": {
    "bm25": {
      "summary": {
        "recall@5": 0.0,
        "recall@10": 0.0,
        "mrr": 0.0,
        "ndcg@10": 0.0
      },
      "per_query": [...]
    },
    "dense": { ... },
    "hybrid": { ... }
  }
}
```

A summary table is also prepared for the README after the first benchmark
run.

---

6. Running the Benchmark

The benchmark is run via:

```bash
python scripts/benchmark.py --golden-set data/gold_standard/
```

The first run populates the cache. Subsequent runs use cached responses.

The environment variable VARIANT_LENS_CACHE_DIR can be set to use a
non-default cache location.

---

7. Known Limitations

Several limitations apply to the MVP evaluation.

The golden set is small. Ten variants are not enough to draw general
conclusions.

Relevance judgments are binary. In reality, some passages are more useful
than others.

The golden set is manually curated. Different curators might select
different passages.

The evaluation measures retrieval quality, not interpretation quality.

The benchmark corpus uses placeholder passages in the MVP. Real PubMed
text is introduced in Phase 2.

---

8. Phase 2 Additions

The following items are planned for Phase 2.

· Expansion of the golden set to 50 variants.
· Replacement of placeholder passages with real PubMed text.
· Addition of bioRxiv and medRxiv as retrieval sources.
· Comparison against BioGPT-ClinVar as an alternative reranker.
· Graded relevance judgments, using a three-level scale.

These additions are not part of the MVP.

---

9. References

· Interface Contract: docs/interface_contract.md
· Architecture: docs/architecture.md
· rank_bm25: https://github.com/dorianbrown/rank_bm25
· PubMedBERT: https://huggingface.co/pritamdeka/S-PubMedBert-MS-MARCO
· nDCG: Järvelin, K., & Kekäläinen, J. (2002). Cumulated gain-based
  evaluation of IR techniques.

```
