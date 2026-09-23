# Golden Set

This directory contains the curated variants used to evaluate VariantLens.

## Files

- `variants.csv` — one row per variant
- `evidence/<variant_id>.json` — manually selected PubMed passages per variant

## Scope

Each variant must satisfy:

- SNV or small indel
- Genome build GRCh38
- gnomAD allele frequency below 0.001
- ClinVar review status of at least two stars
- Clinical significance of Pathogenic, Likely Pathogenic, Benign, or Likely Benign
- At least five relevant PubMed passages

Variants of Uncertain Significance are not included.

## Structure of variants.csv

variant_id, gene, hgvs, chr, pos, ref, alt, af_gnomad, clinvar_significance, clinvar_review, phenotype
## Structure of evidence/<variant_id>.json

```json
{
  "variant_id": "...",
  "query": "...",
  "relevant_pmids": ["...", "..."],
  "notes": "..."
}
