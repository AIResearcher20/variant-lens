
# VariantLens

A command-line tool for rare Mendelian variant interpretation using semantic search over biomedical literature.

**Status:** In development (MVP, v0.1.0)
**License:** Apache 2.0
**Author:** Sepideh Moafi 

---

## Overview

VariantLens takes a variant (HGVS or chr:pos:ref:alt), annotates it using MyVariant.info and gnomAD, retrieves relevant passages from PubMed, reranks them with a cross-encoder, and produces a structured report (JSON + HTML).

The tool is designed to run locally so that no raw sequencing data leaves the user's environment. Only variant identifiers are sent to public APIs.

---

## Status

This repository is in early development. Current state:

- Interface contract: [docs/interface_contract.md](docs/interface_contract.md)
- Architecture: in progress
- Implementation: not started

---

## Scope (MVP)

**In scope:**
- Rare Mendelian SNVs and small indels
- HGVS or VCF-style input
- gnomAD AF < 0.001
- ClinVar clinical significance
- PubMed literature retrieval
- JSON + HTML report

**Out of scope (MVP):**
- Structural variants (SV/CNV)
- Somatic variants
- Clinical decision-making

---

## License

Apache 2.0
