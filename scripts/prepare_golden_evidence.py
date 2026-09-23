"""
Build the golden evidence files.

The script reads the variants table, ensures the ClinVar bulk tables
are present locally, and produces one evidence file per variant. The
output is written to the evidence directory and reported in the
terminal so that an operator can see which variants were included and
which were left out.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from variant_lens.golden import build_all_records

from download_clinvar_bulk import ensure_file, FILES


logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parent.parent
VARIANTS_CSV = ROOT / "data" / "gold_standard" / "variants.csv"
EVIDENCE_DIR = ROOT / "data" / "gold_standard" / "evidence"
DEFAULT_BULK_DIR = ROOT / "data" / "clinvar"


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
    found = "yes" if record["clinvar_found"] else "no"
    return (
        f"{record['variant_id']}: "
        f"clinvar={found} "
        f"linked={len(record['clinvar_linked_pmids'])} "
        f"reference={len(record['reference_pmids'])} "
        f"candidates={len(record['candidate_pmids'])}"
    )


def ensure_bulk_files(bulk_dir: Path) -> None:
    bulk_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in FILES.items():
        destination = bulk_dir / filename
        ensure_file(url, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare golden evidence files."
    )
    parser.add_argument(
        "--variants",
        type=Path,
        default=VARIANTS_CSV,
        help="Path to the variants CSV.",
    )
    parser.add_argument(
        "--bulk-dir",
        type=Path,
        default=DEFAULT_BULK_DIR,
        help="Directory containing the ClinVar bulk tables.",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=EVIDENCE_DIR,
        help="Directory to write the evidence files.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Assume the bulk files are already present.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()

    if not args.variants.exists():
        raise SystemExit(f"missing variants file: {args.variants}")

    if not args.skip_download:
        ensure_bulk_files(args.bulk_dir)

    variants = load_variants(args.variants)
    print(f"loaded {len(variants)} variants from {args.variants}")

    records = build_all_records(
        variants=variants,
        bulk_dir=args.bulk_dir,
    )

    no_reference: list[str] = []
    not_found: list[str] = []

    for record in records:
        write_record(record, args.evidence_dir)
        print(summarize(record))
        if not record["reference_pmids"]:
            no_reference.append(record["variant_id"])
        if not record["clinvar_found"]:
            not_found.append(record["variant_id"])

    print()
    if not_found:
        print(f"variants not found in ClinVar: {len(not_found)}")
        for variant_id in not_found:
            print(f"  {variant_id}")
    else:
        print("all variants found in ClinVar")

    if no_reference:
        print()
        print(f"variants without a reference set: {len(no_reference)}")
        for variant_id in no_reference:
            print(f"  {variant_id}")


if __name__ == "__main__":
    main()
