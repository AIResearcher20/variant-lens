Evaluation

Version: 0.1.0 (MVP)
Status: Draft

This document describes the evaluation design for VariantLens. It defines the golden set, the baselines, the metrics, and the reporting format. It does not describe the implementation of the evaluation runner; that is covered in architecture.md, §4 (scripts/benchmark.py).

---

1. Purpose

Evaluation in VariantLens serves two purposes.

First, it establishes whether the system performs better than simpler retrieval strategies. A hybrid retrieval pipeline with a reranker is more complex than a keyword search. The evaluation must show that the added complexity is justified.

Second, it provides a reproducible reference point. Any change to the retrieval strategy, the embedding model, or the reranker must be evaluated against the same golden set and the same metrics. Without this, changes cannot be compared.

The evaluation is not intended to measure clinical validity. It measures retrieval quality against a hand-curated set of variant–passage pairs.

---

2. Golden Set

2.1 Composition

The golden set is a collection of rare Mendelian variants with manually selected evidence passages.

MVP target: 10 variants. Phase 2 target: 50 variants.

Each entry contains:

· A variant identifier (HGVS or chr:pos:ref:alt)
· Gene symbol
· Clinical significance from ClinVar (Pathogenic, Likely Pathogenic, Benign, Likely Benign)
· ClinVar review status (must be ≥ 2 stars)
· gnomAD allele frequency (must be < 0.001)
· Phenotype from ClinVar, when available
· 5 to 10 PubMed passages selected as relevant

The passages are selected by reading the abstracts and confirming that the passage directly addresses the variant, the gene, or the phenotype in a way that would be useful for interpretation. Passages that merely mention the gene name are not selected.

2.2 Selection Criteria

Criterion Requirement
Variant type SNV or small indel
Genome build GRCh38
gnomAD AF < 0.001
ClinVar review status ≥ 2 stars
Clinical significance Pathogenic, Likely Pathogenic, Benign, or Likely Benign
PubMed coverage At least 5 relevant passages must exist
Gene diversity No more than 2 variants from the same gene

The gene diversity constraint is intended to prevent the golden set from being dominated by a single well-studied gene, which would make the evaluation unrepresentative.

2.3 Distribution

The golden set is balanced across clinical significance.

Label Count (MVP) Count (Phase 2)
Pathogenic or Likely Pathogenic 5 25
Benign or Likely Benign 5 25

Variants of Uncertain Significance are not included in the golden set. Including VUS would introduce label ambiguity that the evaluation cannot resolve.

2.4 Storage

The golden set is stored in data/gold_standard/.

```
data/gold_standard/
├── README.md
├── variants.csv
└── evidence/
    ├── <variant_id>.json
    └── ...
```

variants.csv contains one row per variant. Columns:

```
variant_id, gene, hgvs, chr, pos, ref, alt, af_gnomad,
clinvar_significance, clinvar_review, phenotype
```

Each <variant_id>.json file contains the manually selected passages:

```json
{
  "variant_id": "...",
  "query": "...",
  "relevant_pmids": ["...", "..."],
  "notes": "..."
}
```

The notes field is for recording why a passage was selected. This is useful for reviewing the golden set later.

---

3. Baselines

Three baselines are evaluated alongside VariantLens.

3.1 BM25

Keyword search over PubMed titles and abstracts. No embeddings, no reranking. This represents the simplest reasonable approach.

Implementation: rank_bm25, default parameters.

3.2 Dense-only

Dense retrieval using PubMedBERT embeddings, no reranking. This isolates the contribution of the embedding model.

Implementation: sentence-transformers, model pritamdeka/S-PubMedBert-MS-MARCO or equivalent. ChromaDB as the vector store.

3.3 VariantLens (Hybrid + Reranker)

The full system: BM25 and dense retrieval combined via reciprocal rank fusion, followed by cross-encoder reranking.

This is the system under evaluation.

---

4. Metrics

Four metrics are computed for each strategy.

4.1 Recall@K

The fraction of relevant passages that appear in the top K retrieved passages.

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

A ranking-aware metric that gives more weight to relevant passages at higher ranks.

```
DCG@K = Σ (2^rel_i - 1) / log2(i + 1)
nDCG@K = DCG@K / IDCG@K
```

with binary relevance: rel_i = 1 if the passage is in the golden set, 0 otherwise. IDCG is the ideal DCG, computed as if all relevant passages were ranked first.

4.4 Query-level Results

In addition to aggregate metrics, per-query results are recorded. This makes it possible to identify queries where the system underperforms and to inspect the retrieved passages manually.

---

5. Evaluation Protocol

5.1 Query Construction

For each variant in the golden set, a query is constructed as follows.

```
query = gene + " " + hgvs + " " + phenotype
```

Example:

```
BRCA1 c.68_69delAG hereditary breast and ovarian cancer
```

If phenotype is not available from ClinVar, the query falls back to:

```
query = gene + " " + hgvs
```

This fallback is recorded in the evaluation output.

5.2 Retrieval

For each strategy, the top 50 passages are retrieved. This is the TOP_K default in config.py.

For BM25 and dense-only, retrieval is the final step.

For hybrid + reranker, the top 50 from each strategy are merged via reciprocal rank fusion, and the cross-encoder reranks the merged list. The top 10 after reranking are used for the reported metrics.

5.3 Relevance Judgment

A passage is considered relevant if its PMID appears in the golden set's relevant_pmids list. This is a binary judgment. Graded relevance is not used in the MVP.

5.4 Reporting

Results are written to evaluation_results.json in the following format:

```json
{
  "metadata": {
    "golden_set_size": 10,
    "top_k": 50,
    "rerank_top_k": 10,
    "date": "...",
    "software_version": "..."
  },
  "strategies": {
    "bm25": {
      "recall@5": 0.0,
      "recall@10": 0.0,
      "mrr": 0.0,
      "ndcg@10": 0.0
    },
    "dense": { ... },
    "hybrid_rerank": { ... }
  },
  "per_query": [
    {
      "variant_id": "...",
      "query": "...",
      "strategy": "bm25",
      "retrieved_pmids": ["..."],
      "relevant_pmids": ["..."],
      "recall@5": 0.0,
      "mrr": 0.0
    },
    ...
  ]
}
```

A summary table is also generated for the README:

Strategy Recall@5 Recall@10 MRR nDCG@10
BM25 ... ... ... ...
Dense-only ... ... ... ...
Hybrid + Reranker ... ... ... ...

The numbers are filled after the first benchmark run.

---

6. Running the Benchmark

The benchmark is run via:

```bash
python scripts/benchmark.py --golden-set data/gold_standard/
```

The script does not require network access if the cache is populated. The first run will populate the cache; subsequent runs use cached responses.

Environment variable VARIANT_LENS_CACHE_DIR can be set to use a non-default cache location. This is useful for CI, where the cache is not persistent.

---

7. Known Limitations

Several limitations apply to the MVP evaluation.

The golden set is small. Ten variants are not enough to draw general conclusions. The numbers reported in the MVP are indicative, not definitive.

Relevance judgments are binary. In reality, some passages are more useful than others. Graded relevance would give a more nuanced picture.

The golden set is manually curated. Different curators might select different passages. This introduces a degree of subjectivity that the evaluation cannot eliminate.

The evaluation measures retrieval quality, not interpretation quality. A passage may be relevant to the variant without supporting any particular clinical conclusion.

The evaluation does not test robustness to API failures. Those are covered by unit tests, not by the benchmark.

---

8. Phase 2 Additions

The following items are planned for Phase 2.

· Expansion of the golden set to 50 variants.
· Addition of bioRxiv and medRxiv as retrieval sources.
· Comparison against BioGPT-ClinVar as an alternative reranker.
· Graded relevance judgments, using a three-level scale.
· Cross-validation of retrieval results across multiple PubMed snapshots.

These additions are not part of the MVP and are listed here for planning only.

---

9. References

· Interface Contract: docs/interface_contract.md
· Architecture: docs/architecture.md
· rank_bm25: https://github.com/dorianbrown/rank_bm25
· ChromaDB: https://docs.trychroma.com
· PubMedBERT: https://huggingface.co/microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract
· nDCG: Järvelin, K., & Kekäläinen, J. (2002). Cumulated gain-based evaluation of IR techniques.

---

چرا؟
