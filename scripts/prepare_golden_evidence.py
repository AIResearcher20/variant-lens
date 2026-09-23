"""
Build the golden evidence files.

This script reads the variants table, calls the golden builder for each
row, and writes the results to the evidence directory. Variants that end
up with an empty reference set or an incomplete ClinVar lookup are
reported at the end so that the choice of what to do with them can be
made deliberately.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from variant_lens.golden import build_evidence_record


ROOT = Path(__file__).resolve().parent.parent
VARIANTS_CSV = ROOT / "data" / "gold_standard" / "variants.csv"
EVIDENCE_DIR = ROOT / "data" / "gold_standard" / "evidence"


def load_variants(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_record(record: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    out = directory / f"{record['variant_id']}.json"
    out.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out


def summarize(record: dict) -> str:
    status = "complete" if record["clinvar_complete"] else "incomplete"
    return (
        f"{record['variant_id']}: "
        f"clinvar={len(record['clinvar_linked_pmids'])} "
        f"reference={len(record['reference_pmids'])} "
        f"candidates={len(record['candidate_pmids'])} "
        f"status={status}"
    )


def main() -> None:
    if not VARIANTS_CSV.exists():
        raise SystemExit(f"missing {VARIANTS_CSV}")

    variants = load_variants(VARIANTS_CSV)
    print(f"loaded {len(variants)} variants from {VARIANTS_CSV}")

    no_reference: list[str] = []
    incomplete: list[str] = []

    for row in variants:
        record = build_evidence_record(
            variant_id=row["variant_id"],
            gene=row["gene"],
            hgvs=row["hgvs"],
            phenotype=row.get("phenotype", ""),
        )
        write_record(record, EVIDENCE_DIR)
        print(summarize(record))
        if not record["reference_pmids"]:
            no_reference.append(row["variant_id"])
        if not record["clinvar_complete"]:
            incomplete.append(row["variant_id"])

    print()
    if no_reference:
        print(f"variants without a reference set: {len(no_reference)}")
        for variant_id in no_reference:
            print(f"  {variant_id}")
    else:
        print("all variants have a non-empty reference set")

    if incomplete:
        print()
        print(f"variants with an incomplete ClinVar lookup: {len(incomplete)}")
        for variant_id in incomplete:
            print(f"  {variant_id}")


if __name__ == "__main__":
    main()
