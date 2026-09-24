# Evaluation

Version: 0.3.0
Status: Draft

This document describes the evaluation design for VariantLens. It
defines the golden set, the baselines, the metrics, and the reporting
format. The implementation of the evaluation runner is described in
`architecture.md`.

---

## 1. Purpose

Evaluation in VariantLens serves two purposes.

First, it establishes whether the system performs better than simpler
retrieval strategies. A hybrid pipeline with a reranker is more complex
than a keyword search. The evaluation must show that the added
complexity is justified.

Second, it provides a reproducible reference point. Any change to the
retrieval strategy, the embedding model, or the reranker must be
evaluated against the same golden set and the same metrics. Without
this, changes cannot be compared.

The evaluation measures retrieval quality against an externally sourced
reference set. It is not intended to measure clinical validity.

---

## 2. Golden Set

### 2.1 Composition

The golden set is a collection of rare Mendelian variants with a
reference set of relevant publications for each variant.

MVP target: 10 variants. Phase 2 target: 50 variants.

Each variant entry contains:

- A variant identifier
- Gene symbol
- HGVS coding sequence notation
- Clinical significance from ClinVar
- ClinVar review status
- gnomAD allele frequency
- Phenotype from ClinVar, when available
- A list of aliases used in the literature
- A reference set of PubMed identifiers drawn from ClinVar citations

### 2.2 Selection Criteria

| Criterion | Requirement |
|---|---|
| Variant type | SNV or small indel |
| Genome build | GRCh38 |
| gnomAD AF | below 0.001 |
| ClinVar review status | at least two stars |
| Clinical significance | Pathogenic, Likely Pathogenic, Benign, or Likely Benign |
| Gene diversity | no more than two variants from the same gene |

Variants of Uncertain Significance are not included.

### 2.3 Source of relevance labels

The relevance labels come from publications that ClinVar links to each
variant. These citations are submitted by the groups that file the
variant records, and NCBI states that only a small subset of them has
been independently curated. For this reason they are treated as an
externally sourced reference set, not as ground truth.

Variants that cannot be matched against ClinVar, or that end up with an
empty reference set after matching, are excluded from the benchmark. The
exclusion is reported at the end of every benchmark run.

### 2.4 Current composition

The MVP golden set was drawn from a source table of ten variants. Eight
of them were matched successfully against ClinVar and have non-empty
reference sets. Two variants are excluded:

- `hbb_c20a_t` — no matching record found in the ClinVar bulk tables
- `g6pd_c563c_t` — no matching record found in the ClinVar bulk tables

The breakdown by clinical significance for the eight eligible variants
is as follows.

| Label | Count |
|---|---|
| Pathogenic | 5 |
| Likely Pathogenic | 0 |
| Benign | 2 |
| Risk factor | 1 |
| Likely Benign | 0 |

### 2.5 Storage

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
clinvar_significance, clinvar_review, phenotype, aliases
```

The `aliases` column lists alternative names that appear in the
literature for the same variant, separated by `|`. This handles the
vocabulary gap between HGVS notation and clinical writing. For example,
the variant `c.1521_1523delCTT` in CFTR is almost always called F508del
in the literature, and the variant at APOE is called e4 or APOE4.

Each `<variant_id>.json` file contains the assembled evidence record:

```json
{
  "variant_id": "...",
  "gene": "...",
  "hgvs": "...",
  "query": "...",
  "aliases": ["..."],
  "clinvar_variation_id": "...",
  "clinvar_linked_pmids": ["..."],
  "clinvar_found": true,
  "reference_pmids": ["..."],
  "candidate_pmids": ["..."],
  "titles": {"<pmid>": "..."},
  "abstracts": {"<pmid>": "..."},
  "years": {"<pmid>": 2020}
}
```

### 2.6 Construction pipeline

The evidence files are built in two steps.

First, the ClinVar bulk tables are downloaded from the NCBI FTP site:

```
variant_summary.txt.gz
var_citations.txt
```

These files are read in a streaming fashion. Only the variants listed in
`variants.csv` are kept, which keeps memory use bounded even though the
summary file contains several million rows.

Second, PubMed is queried to add distractor passages. For each variant,
a search based on gene, HGVS, and phenotype returns a wider set of
articles. These are added to the candidate list but are not treated as
relevant unless the variant-specific filter matches them.

The distinction matters. The ClinVar-linked publications provide the
reference set against which Recall, MRR, and nDCG are computed. The
PubMed results provide distractors that make the retrieval task
non-trivial.

---

## 3. Baselines

Three retrieval strategies are evaluated.

### 3.1 BM25

Keyword search over passage titles and abstracts. No embeddings, no
reranking. This represents the simplest reasonable approach.

Implementation: rank_bm25 with default parameters.

### 3.2 Dense

Dense retrieval using PubMedBERT embeddings and cosine similarity. No
reranking. This isolates the contribution of the embedding model.

Implementation: sentence-transformers with
`pritamdeka/S-PubMedBert-MS-MARCO`. The corpus is kept in memory.

Corpus embeddings are cached at module level so that several queries
share the same vectors. Without this, each query would re-encode the
entire corpus, which is the dominant cost in the current pipeline.

When sentence-transformers is not installed, dense retrieval returns an
empty list.

### 3.3 Hybrid

Combines BM25 and dense retrieval via Reciprocal Rank Fusion.

The RRF score for a passage is the sum of `1 / (k + rank)` over all
lists in which the passage appears. The default k is 60.

When dense retrieval is unavailable, hybrid falls back to BM25.

---

## 4. Metrics

Four metrics are computed for each strategy.

### 4.1 Recall@K

The fraction of reference passages that appear in the top K retrieved
passages.

```
Recall@K = |reference ∩ retrieved@K| / |reference|
```

Computed for K = 5 and K = 10.

### 4.2 Mean Reciprocal Rank

The mean of the reciprocal of the rank of the first reference passage.

```
MRR = (1/|Q|) Σ (1 / rank_i)
```

where rank_i is the rank of the first reference passage for query i.

### 4.3 Normalized Discounted Cumulative Gain

A ranking-aware metric that gives more weight to reference passages at
higher ranks.

```
DCG@K = Σ (2^rel_i - 1) / log2(i + 1)
nDCG@K = DCG@K / IDCG@K
```

with binary relevance: rel_i = 1 if the passage is in the reference
set, 0 otherwise. IDCG is the ideal DCG.

### 4.4 Query-level results

Per-query results are recorded alongside the aggregate metrics. This
makes it possible to identify queries where a strategy underperforms.

---

## 5. Evaluation Protocol

### 5.1 Query construction

For each variant, the query is the concatenation of gene, HGVS, and
phenotype:

```
query = gene + " " + hgvs + " " + phenotype
```

If the phenotype field is empty, the query falls back to gene and HGVS.

### 5.2 Retrieval

For each strategy, the top 50 passages are retrieved. This value is
controlled by the `--top-k` argument and defaults to 50 in the
benchmark runner.

For BM25 and dense, retrieval is the final step. For hybrid, the top-k
lists from BM25 and dense are fused via RRF.

### 5.3 Relevance judgment

A passage is considered relevant if its PMID appears in the
`reference_pmids` list of the variant being evaluated. This is a binary
judgment. Graded relevance is not used in the MVP.

### 5.4 Reporting

Results are written to `evaluation_results.json`:

```json
{
  "metadata": {
    "golden_set_size": 10,
    "eligible_size": 8,
    "corpus_size": 963,
    "top_k": 50
  },
  "strategies": {
    "bm25": {
      "summary": {
        "recall@5": 0.150,
        "recall@10": 0.162,
        "mrr": 0.445,
        "ndcg@10": 0.193
      },
      "per_query": [...]
    },
    "dense": { ... },
    "hybrid": { ... }
  }
}
```

### 5.5 Results

The benchmark was run on the current golden set. The corpus size is 963
passages across eight eligible variants.

| Strategy | Recall@5 | Recall@10 | MRR   | nDCG@10 |
|----------|----------|-----------|-------|---------|
| BM25     | 0.150    | 0.162     | 0.445 | 0.193   |
| Dense    | 0.170    | 0.234     | 0.442 | 0.357   |
| Hybrid   | 0.169    | 0.187     | 0.449 | 0.247   |

Dense retrieval with PubMedBERT improves nDCG@10 by roughly 1.85 times
over BM25, and improves Recall@10 by about 44 percent. Hybrid retrieval
sits between the two. Its recall values are close to BM25 rather than
to dense, which suggests that the equal weighting in RRF gives too much
influence to BM25 on this corpus.

The absolute recall values are modest. Two factors explain this. The
reference sets are large: BRCA1 alone has 65 reference PMIDs, so even a
strong ranking can only place a fraction of them in the top five. The
vocabulary gap between HGVS notation and biomedical literature also
remains wide. The alias list reduces this gap but does not eliminate it.

---

## 6. Running the benchmark

The benchmark is run via:

```bash
python scripts/benchmark.py --golden-set data/gold_standard/
```

To regenerate the evidence files before running the benchmark:

```bash
python scripts/download_clinvar_bulk.py
python scripts/prepare_golden_evidence.py
```

The first run populates the cache. Subsequent runs use cached responses.
The environment variable `VARIANT_LENS_CACHE_DIR` can be set to use a
non-default cache location.

The benchmark workflow runs automatically on every change to the
retrieval code or to the golden set evidence files.

---

## 7. Known Limitations

Several limitations apply to the current evaluation.

The golden set is small. Eight eligible variants are not enough to draw
general conclusions.

Reference labels come from ClinVar citations, which are submitted by
different groups and vary in how directly they address the variant. They
are treated as an externally sourced reference set, not as ground truth.

Relevance judgments are binary. In reality, some passages are more
useful than others.

The evaluation measures retrieval quality, not interpretation quality.

Hybrid retrieval underperforms dense on this corpus. The likely cause
is the equal weighting scheme in RRF. An asymmetric weighting, or a
learned fusion, would probably improve the result but is outside the
current scope.

---

## 8. Phase 2 Additions

The following items are planned for Phase 2.

- Expansion of the golden set to 50 variants.
- Addition of bioRxiv and medRxiv as retrieval sources.
- Comparison against an alternative reranker.
- Graded relevance judgments on a three-level scale.
- Asymmetric weighting for Reciprocal Rank Fusion.

These additions are not part of the MVP.

---

## 9. References

- Interface Contract: `docs/interface_contract.md`
- Architecture: `docs/architecture.md`
- rank_bm25: https://github.com/dorianbrown/rank_bm25
- PubMedBERT: https://huggingface.co/pritamdeka/S-PubMedBert-MS-MARCO
- ClinVar FTP: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/
- nDCG: Järvelin, K., & Kekäläinen, J. (2002). Cumulated gain-based
  evaluation of IR techniques.
