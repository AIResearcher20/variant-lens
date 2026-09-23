
# VariantLens

A command-line tool for rare Mendelian variant interpretation using semantic search over biomedical literature.

**Status:** MVP (v0.1.0)
**License:** Apache 2.0
**Author:** Sepideh Moafi 

---

## Problem

Interpreting a rare genetic variant requires checking multiple databases (ClinVar, gnomAD) and searching PubMed for supporting evidence. This is time-consuming, and the search is often keyword-based, missing relevant papers that use different phrasing.

VariantLens addresses this by combining annotation, retrieval, and reranking in one pipeline.

---

## What it does

Given a variant (HGVS or chr:pos:ref:alt), VariantLens:

1. Parses the input and normalizes it.
2. Annotates it using MyVariant.info and gnomAD.
3. Filters the variant by allele frequency and ClinVar review status.
4. Retrieves relevant passages from PubMed using BM25.
5. Reranks the passages with a cross-encoder when one is available.
6. Writes a structured JSON report.

The tool runs locally. Only variant identifiers are sent to public APIs. No raw sequencing data leaves the user's environment.

---

## Scope

**In scope (MVP):**

- Rare Mendelian SNVs and small indels
- HGVS or VCF-style input
- gnomAD allele frequency below 0.001
- ClinVar significance and review status
- PubMed retrieval via BM25
- JSON report

**Out of scope (MVP):**

- Structural variants (SV/CNV)
- Somatic variants
- Clinical decision-making
- Variants of Uncertain Significance

---

## Installation

```bash
pip install git+https://github.com/AIResearcher20/variant-lens.git
```

For development:

```bash
git clone https://github.com/AIResearcher20/variant-lens.git
cd variant-lens
pip install -e ".[dev]"
```

To enable the cross-encoder reranker:

```bash
pip install -e ".[rerank]"
```

---

Usage

```bash
variant-lens interpret "BRCA1 c.68_69delAG" --output report.json
```

The command runs the full pipeline and writes the report to report.json.

Optional flags:

· --output, -o — path to the report (default: report.json)
· --top-k — number of ranked passages to include (default: 10)

To print the version:

```bash
variant-lens version
```

---

Report format

The JSON report has three top-level keys:

· variant — input, normalized HGVS, gene, variant type, parse status
· evidence — scope status, allele frequency status, ClinVar fields, phenotype
· passages — ranked PubMed passages with PMID, title, and rank

Example:

```json
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
```

---

Architecture

The pipeline is split into independent modules:

· parse — input parsing, no network
· scope — allele frequency and scope determination, no network
· fetch — API calls with cache and retry, never raises for individual source failures
· annotate — merges parse, scope, and fetch into a single result
· retrieve — BM25 (dense and hybrid planned for Phase 2)
· rank — cross-encoder reranking with fallback
· report — JSON report generation
· cli — command-line entry point

Design details are in docs/architecture.md. Interface contracts are in docs/interface_contract.md.

---

Evaluation

The repository includes a golden set and a benchmark script. See docs/evaluation.md for the design and data/gold_standard/ for the current variants.

To run the benchmark:

```bash
python scripts/benchmark.py --golden-set data/gold_standard/
```

The MVP benchmark runs BM25 only. Dense and hybrid strategies are planned for Phase 2, along with BioGPT-ClinVar as an alternative reranker.

---

Limitations

· The task is limited to rare Mendelian SNVs and small indels.
· Variants with uncertain or conflicting annotations are excluded.
· Only BM25 retrieval is implemented in the MVP.
· The cross-encoder reranker is optional and may not be available in restricted environments.
· The tool is intended for research use. It is not validated for clinical decision-making.
· PubMed coverage varies by gene, variant, and publication date.

---

Development

The repository includes:

· pytest test suite
· GitHub Actions CI (Python 3.10, 3.11, 3.12)
· Docker image

To run tests locally:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

To build the Docker image:

```bash
docker build -t variant-lens:dev .
```

---

Citation

If you use this tool in research, please cite it as below.

```bibtex
@software{Karimi2026variantlens,
  title={VariantLens: A Command-Line Tool for Rare Mendelian Variant Interpretation},
  author={Karimi, Vania},
  year={2026},
  url={https://github.com/AIResearcher20/variant-lens},
  license={Apache-2.0}
}
```

---

License

Apache 2.0. See LICENSE for details.

```
