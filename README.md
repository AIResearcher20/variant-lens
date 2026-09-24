# VariantLens

A command-line tool for rare Mendelian variant interpretation using
semantic search over biomedical literature.

**Status:** MVP (v0.2.0)
**License:** Apache 2.0
**Author:** Sepideh Moafi

---

## Problem

Interpreting a rare genetic variant requires checking multiple
databases (ClinVar, gnomAD) and searching PubMed for supporting
evidence. The process is time-consuming, and the search is often
keyword-based, missing relevant papers that use different phrasing.

VariantLens combines annotation, retrieval, and reranking in one
pipeline.

---

## What it does

Given a variant (HGVS or chr:pos:ref:alt), VariantLens:

1. Parses the input and normalizes it.
2. Annotates it using MyVariant.info and gnomAD.
3. Filters the variant by allele frequency and ClinVar review status.
4. Retrieves relevant passages from PubMed using BM25, dense, or
   hybrid retrieval.
5. Reranks the passages with a cross-encoder when one is available.
6. Writes a structured JSON report.

The tool runs locally. Only variant identifiers are sent to public
APIs. No raw sequencing data leaves the user's environment.

---

## Scope

**In scope (MVP):**

- Rare Mendelian SNVs and small indels
- HGVS or VCF-style input
- gnomAD allele frequency below 0.001
- ClinVar significance and review status
- PubMed retrieval via BM25, dense, or hybrid
- JSON report

**Out of scope (MVP):**

- Structural variants (SV/CNV)
- Somatic variants
- Clinical decision-making
- Variants of Uncertain Significance

---

## Installation

    pip install git+https://github.com/AIResearcher20/variant-lens.git

For development:

    git clone https://github.com/AIResearcher20/variant-lens.git
    cd variant-lens
    pip install -e ".[dev]"

To enable the cross-encoder reranker:

    pip install -e ".[rerank]"

To enable dense and hybrid retrieval:

    pip install -e ".[retrieve]"

---

## Usage

    variant-lens interpret "BRCA1 c.68_69delAG" --output report.json

The command runs the full pipeline and writes the report to
report.json.

Optional flags:

- `--output`, `-o` — path to the report (default: report.json)
- `--top-k` — number of ranked passages to include (default: 10)
- `--max-passages` — number of PubMed passages to retrieve
  (default: 20)

To print the version:

    variant-lens version

---

## Report format

The JSON report has three top-level keys:

- `variant` — input, normalized HGVS, gene, variant type, parse status
- `evidence` — scope status, allele frequency status, ClinVar fields,
  phenotype
- `passages` — ranked PubMed passages with PMID, title, and rank

Example:

    {
      "variant": {
        "input": "BRCA1 c.68_69delAG",
        "normalized_hgvs": "BRCA1 c.68_69delAG",
        "gene": "BRCA1",
        "variant_type": "indel",
        "is_parseable": true,
        "is_supported": true
      },
      "evidence": {
        "scope_status": "in_scope",
        "af_status": "known",
        "allele_frequency": 0.0001,
        "evidence_state": "complete",
        "clinvar": {
          "significance": "Pathogenic",
          "review_status": "reviewed by expert panel",
          "variation_id": "12345"
        },
        "phenotype": "Hereditary breast and ovarian cancer"
      },
      "passages": [
        {
          "pmid": "12345678",
          "title": "BRCA1 variant in hereditary breast cancer",
          "year": 2020,
          "rank": 1
        }
      ]
    }

---

## Architecture

The pipeline is split into independent modules:

- `parse` — input parsing, no network
- `scope` — allele frequency and scope determination, no network
- `fetch` — API calls with cache and retry, never raises for
  individual source failures
- `annotate` — merges parse, scope, and fetch into a single result
- `retrieve` — BM25, dense, and hybrid retrieval
- `rank` — cross-encoder reranking with fallback
- `report` — JSON report generation
- `cli` — command-line entry point
- `clinvar_bulk` — reader for the ClinVar bulk tables
- `clinvar` — lookup over the bulk data
- `golden` — construction of golden set evidence records

Design details are in `docs/architecture.md`. Interface contracts are
in `docs/interface_contract.md`.

---

## Retrieval strategies

Three strategies are available:

- **BM25** — keyword search over titles and abstracts. Always
  available.
- **Dense** — PubMedBERT embeddings and cosine similarity. Requires
  `[retrieve]`.
- **Hybrid** — Reciprocal Rank Fusion of BM25 and dense. Requires
  `[retrieve]`. Falls back to BM25 when dense is unavailable.

The default strategy in the CLI is BM25.

---

## Evaluation

The repository includes a golden set and a benchmark script. See
`docs/evaluation.md` for the design and `data/gold_standard/` for the
current variants.

The golden set covers eight rare Mendelian variants from ClinVar,
selected by allele frequency below 0.001 in gnomAD and a review status
of at least two stars. Reference publications are drawn from the
citations that ClinVar links to each variant. The evaluation corpus
adds PubMed search results that act as distractors.

Two variants in the source table could not be matched against ClinVar
and are excluded from the benchmark: `hbb_c20a_t` and `g6pd_c563c_t`.

The benchmark compares BM25, dense, and hybrid retrieval on four
metrics: Recall@5, Recall@10, Mean Reciprocal Rank, and nDCG@10.

### Results

The benchmark was run on the current golden set: eight eligible
variants, corpus size of 963 passages, top-k of 50.

| Strategy | Recall@5 | Recall@10 | MRR   | nDCG@10 |
|----------|----------|-----------|-------|---------|
| BM25     | 0.150    | 0.162     | 0.445 | 0.193   |
| Dense    | 0.170    | 0.234     | 0.442 | 0.357   |
| Hybrid   | 0.169    | 0.187     | 0.449 | 0.247   |

Dense retrieval with PubMedBERT improves nDCG@10 by roughly 1.85 times
over BM25, and improves Recall@10 by about 44 percent. Hybrid
retrieval, which combines both strategies through Reciprocal Rank
Fusion, sits between the two. Its recall values are close to BM25
rather than to dense, which suggests that the equal weighting in RRF
gives too much influence to BM25 on this corpus.

The absolute recall values are modest. Two factors explain this. The
reference sets are large: BRCA1 alone has 65 reference PMIDs, so even
a strong ranking can only place a fraction of them in the top five.
The vocabulary gap between HGVS notation and biomedical literature
also remains wide. The alias list reduces this gap but does not
eliminate it.

Results are stored in `evaluation_results.json` and regenerated
automatically on every change to the retrieval code or the golden set.

---

## Design Decisions

Several decisions shaped the current architecture. Each is recorded
here with the reasoning behind it, because the same alternatives may
come up again if the pipeline is extended.

### 1. ClinVar data comes from bulk tables, not from the API

The first implementation queried ClinVar through NCBI E-utilities. Two
problems appeared in practice. The elink endpoint returned HTTP 429
under ordinary load, even at the documented rate of three requests per
second. The efetch endpoint returned HTTP 414 when a variant had more
than a few dozen linked publications, because the identifier list made
the request URL too long.

The bulk tables published by NCBI avoid both problems. A single
download provides the entire catalogue. The download is cached, the
files are read in streaming fashion, and no network calls are made
during evidence construction. The current run takes a few seconds
instead of several minutes.

### 2. HGVS matching is tolerant

ClinVar does not always write the variant identifier in the same form
as the source table. The BRCA1 deletion recorded as `c.68_69delAG` in
the source table appears in the current ClinVar export as `c.68_69del`,
because HGVS no longer requires the deleted nucleotides to be spelled
out. Exact matching would miss the record.

Two keys are produced for every variant: the exact HGVS string and a
shortened form with trailing nucleotide letters removed. Lookup tries
both. This change alone increased the number of matched variants from
five to eight.

### 3. Aliases handle the vocabulary gap

Even with tolerant matching, the reference set for several variants was
empty or nearly empty. The reason was not the retrieval algorithm but
the vocabulary. Papers about the CFTR variant `c.1521_1523delCTT`
almost never write the HGVS form. They write F508del. Papers about the
APOE variant `c.388T>C` write e4. Papers about CYP2C19 `c.681G>A`
write CYP2C19*2.

A column of aliases was added to the variants table. The alias list is
combined with the HGVS tokens when deciding whether a passage is
relevant. With this change the total reference set grew from roughly
30 publications to 325.

### 4. PubMed fetch is batched and cached

The fetch layer initially sent one request per query, with a fixed
sleep between requests. Under the NCBI rate limit without an API key,
this was unstable for large corpora and slow for repeated runs.

Two changes were made. First, requests are batched. Identifiers are
grouped into batches of fifty and sent in a single request, which keeps
the URL below the length that NCBI accepts. Second, every response is
cached. A repeated run over the same identifiers does not touch the
network.

The batch size, pause, retry count, and backoff base are all defined in
`config.py` and can be adjusted without editing the fetch module.

### 5. Corpus embeddings are cached at module level

Dense retrieval encodes the corpus once and then queries it for every
variant. The first implementation re-encoded the corpus on every call.
With eight queries over a corpus of 963 passages, this meant the
embedding step ran eight times on identical input.

The corpus vectors are now stored at module level and reused. The cache
key combines the corpus length with hashes of the first and last
passage. This is enough to detect a change of corpus without storing
the full text. The benchmark run time dropped by roughly seven times.

### 6. Relevance is treated as a reference set, not ground truth

ClinVar citation links are submitted by the groups that file the
variant records. NCBI states that only a small fraction of these
citations has been independently curated. For this reason the
evaluation does not treat ClinVar-linked publications as an absolute
truth about relevance.

The field names in the JSON reflect this distinction.
`reference_pmids` holds the ClinVar links, and `candidate_pmids` holds
the union of those links with PubMed distractors. The documentation
uses the same vocabulary.

### 7. Hybrid retrieval is reported honestly

RRF with equal weighting gives the same influence to BM25 and to dense
retrieval. On the current corpus, dense clearly outperforms BM25 on
every metric except MRR. The hybrid result sits between them, close to
BM25, which is not what a hybrid system is supposed to deliver.

Rather than tune the weights to make hybrid look better, the result is
reported as measured and the cause is noted in the limitations. An
asymmetric weighting scheme is listed as a Phase 2 addition. The
benchmark reports what the pipeline does, not what was hoped for.

---

## Limitations

- The task is limited to rare Mendelian SNVs and small indels.
- Variants with uncertain or conflicting annotations are excluded.
- The golden set is small. Eight variants are not enough to draw
  general conclusions.
- Reference relevance labels come from ClinVar citations, which vary
  in specificity across submitters.
- The cross-encoder reranker is optional and may not be available in
  restricted environments.
- Dense retrieval requires sentence-transformers, which is not
  installed by default.
- The tool is intended for research use. It is not validated for
  clinical decision-making.
- PubMed coverage varies by gene, variant, and publication date.

---

## Development

The repository includes:

- pytest test suite
- GitHub Actions CI on Python 3.10, 3.11, and 3.12
- Docker image

To run tests locally:

    pip install -e ".[dev]"
    pytest tests/ -v

To build the Docker image:

    docker build -t variant-lens:dev .

To regenerate the golden evidence files:

    python scripts/download_clinvar_bulk.py
    python scripts/prepare_golden_evidence.py

To run the benchmark:

    python scripts/benchmark.py --golden-set data/gold_standard/

---

## Citation

If you use this tool in research, please cite it as below.

    @software{Moafi2026variantlens,
      title={VariantLens: A Command-Line Tool for Rare Mendelian Variant Interpretation},
      author={Sepideh Moafi},
      year={2026},
      url={https://github.com/AIResearcher20/variant-lens},
      license={Apache-2.0}
    }

---

## License

Apache 2.0. See LICENSE for details.
