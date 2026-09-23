"""
Benchmark runner.

Compares BM25, dense, and hybrid retrieval against the golden set.
Dense and hybrid strategies are stubs in the MVP; only BM25 runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from variant_lens.retrieve.bm25 import bm25_retrieve
from variant_lens.schema import Passage, RetrievalStrategy


DEFAULT_GOLDEN_DIR = Path("data/gold_standard")
DEFAULT_OUTPUT = Path("evaluation_results.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the VariantLens benchmark.")
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=DEFAULT_GOLDEN_DIR,
        help="Path to the golden set directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write the JSON results.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of retrieved passages used for metric computation.",
    )
    return parser.parse_args()


def load_variants(golden_dir: Path) -> list[dict[str, str]]:
    csv_path = golden_dir / "variants.csv"
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_evidence(golden_dir: Path, variant_id: str) -> dict[str, Any]:
    evidence_path = golden_dir / "evidence" / f"{variant_id}.json"
    if not evidence_path.exists():
        return {"variant_id": variant_id, "relevant_pmids": []}
    with evidence_path.open() as f:
        return json.load(f)


def build_corpus(golden_dir: Path) -> list[Passage]:
    """
    Build a corpus from all evidence JSON files.

    The corpus is the union of all PMIDs referenced in the golden set.
    In the MVP, passages are placeholders with only a PMID and title.
    """
    passages: list[Passage] = []
    seen: set[str] = set()

    evidence_dir = golden_dir / "evidence"
    if not evidence_dir.exists():
        return passages

    for evidence_file in evidence_dir.glob("*.json"):
        with evidence_file.open() as f:
            data = json.load(f)
        for pmid in data.get("relevant_pmids", []):
            if pmid in seen:
                continue
            seen.add(pmid)
            passages.append(
                Passage(
                    pmid=pmid,
                    title=f"PMID {pmid}",
                    abstract=None,
                    year=None,
                )
            )

    return passages


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = set(retrieved[:k])
    return len(top & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for i, pmid in enumerate(retrieved, start=1):
        if pmid in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    dcg = 0.0
    for i, pmid in enumerate(retrieved[:k], start=1):
        if pmid in relevant:
            dcg += 1.0 / math.log2(i + 1)

    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))

    return dcg / idcg if idcg > 0 else 0.0


def run_bm25(
    variants: list[dict[str, str]],
    golden_dir: Path,
    top_k: int,
) -> dict[str, Any]:
    corpus = build_corpus(golden_dir)

    results = {
        "recall@5": [],
        "recall@10": [],
        "mrr": [],
        "ndcg@10": [],
    }
    per_query: list[dict[str, Any]] = []

    for variant in variants:
        variant_id = variant["variant_id"]
        evidence = load_evidence(golden_dir, variant_id)
        relevant = set(evidence.get("relevant_pmids", []))
        query = evidence.get("query") or variant.get("hgvs", "")

        retrieved_passages = bm25_retrieve(query, corpus, top_k=top_k)
        retrieved_pmids = [p.pmid for p in retrieved_passages]

        r5 = recall_at_k(retrieved_pmids, relevant, 5)
        r10 = recall_at_k(retrieved_pmids, relevant, 10)
        rr = reciprocal_rank(retrieved_pmids, relevant)
        ndcg = ndcg_at_k(retrieved_pmids, relevant, 10)

        results["recall@5"].append(r5)
        results["recall@10"].append(r10)
        results["mrr"].append(rr)
        results["ndcg@10"].append(ndcg)

        per_query.append(
            {
                "variant_id": variant_id,
                "query": query,
                "retrieved_pmids": retrieved_pmids,
                "relevant_pmids": sorted(relevant),
                "recall@5": r5,
                "recall@10": r10,
                "mrr": rr,
                "ndcg@10": ndcg,
            }
        )

    return {
        "summary": {k: _mean(v) for k, v in results.items()},
        "per_query": per_query,
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    args = parse_args()

    variants = load_variants(args.golden_set)
    bm25_results = run_bm25(variants, args.golden_set, args.top_k)

    report = {
        "metadata": {
            "golden_set_size": len(variants),
            "top_k": args.top_k,
        },
        "strategies": {
            RetrievalStrategy.BM25.value: bm25_results,
        },
    }

    args.output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
