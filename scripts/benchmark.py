"""
Benchmark runner for VariantLens.

Compares BM25, dense, and hybrid retrieval against the golden set. The
evaluation uses reference PMIDs drawn from ClinVar citations as the
relevance label. The candidate corpus is the union of every candidate
PMID across all variants, which includes distractors that are not
relevant to any query. This separation is what makes the metrics
meaningful: without distractors, every strategy would retrieve the
same small set of documents and Recall would be trivially perfect.

Dense retrieval falls back to an empty result when its backend is not
installed. Hybrid then falls back to BM25. This behaviour is expected
in restricted environments and is reported explicitly in the output.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from variant_lens.retrieve import retrieve
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
        default=50,
        help="Number of retrieved passages used for metric computation.",
    )
    return parser.parse_args()


def load_variants(golden_dir: Path) -> list[dict[str, str]]:
    csv_path = golden_dir / "variants.csv"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_evidence(golden_dir: Path, variant_id: str) -> dict[str, Any] | None:
    path = golden_dir / "evidence" / f"{variant_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def eligible_variants(
    golden_dir: Path,
    variants: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    Return the evidence records that can be used in evaluation.

    A variant is eligible when it was found in ClinVar and has at least
    one reference PMID. Variants without a reference set cannot
    contribute to Recall, MRR, or nDCG and would distort the averages.
    """
    eligible: list[dict[str, Any]] = []
    for row in variants:
        record = load_evidence(golden_dir, row["variant_id"])
        if record is None:
            continue
        if not record.get("clinvar_found"):
            continue
        if not record.get("reference_pmids"):
            continue
        eligible.append(record)
    return eligible


def build_corpus(records: list[dict[str, Any]]) -> list[Passage]:
    """
    Build the evaluation corpus.

    The corpus is the union of all candidate PMIDs across the eligible
    variants. Each entry carries the title and abstract that were
    collected when the evidence files were produced. Identifiers that
    appear in more than one variant's candidate list are kept only once.
    """
    passages: list[Passage] = []
    seen: set[str] = set()

    for record in records:
        candidate_pmids = record.get("candidate_pmids", [])
        titles = record.get("titles", {})
        abstracts = record.get("abstracts", {})
        years = record.get("years", {})

        for pmid in candidate_pmids:
            if not pmid or pmid in seen:
                continue
            seen.add(pmid)
            passages.append(
                Passage(
                    pmid=pmid,
                    title=titles.get(pmid, ""),
                    abstract=abstracts.get(pmid),
                    year=years.get(pmid),
                )
            )

    return passages


def build_per_variant(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Summarise each eligible variant for reporting purposes.

    The result records the size of the reference set, the number of
    candidate publications, and the size of the intersection. These
    numbers feed the reference-size plot and make it possible to see
    which variants dominate the corpus.
    """
    summary: list[dict[str, Any]] = []
    for record in records:
        reference = record.get("reference_pmids", [])
        candidates = record.get("candidate_pmids", [])
        summary.append({
            "variant_id": record["variant_id"],
            "gene": record.get("gene", ""),
            "reference_count": len(reference),
            "candidate_count": len(candidates),
            "reference_in_corpus": len(set(reference) & set(candidates)),
        })
    return summary


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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def run_strategy(
    strategy: RetrievalStrategy,
    records: list[dict[str, Any]],
    corpus: list[Passage],
    top_k: int,
) -> dict[str, Any]:
    """
    Run a single retrieval strategy against the eligible records.

    Returns a summary dict with mean metrics and per-query results.
    """
    results = {
        "recall@5": [],
        "recall@10": [],
        "mrr": [],
        "ndcg@10": [],
    }
    per_query: list[dict[str, Any]] = []

    for record in records:
        variant_id = record["variant_id"]
        query = record.get("query", "")
        relevant = set(record.get("reference_pmids", []))

        retrieved_passages = retrieve(
            query=query,
            passages=corpus,
            strategy=strategy,
            top_k=top_k,
        )
        retrieved_pmids = [p.pmid for p in retrieved_passages]

        r5 = recall_at_k(retrieved_pmids, relevant, 5)
        r10 = recall_at_k(retrieved_pmids, relevant, 10)
        rr = reciprocal_rank(retrieved_pmids, relevant)
        ndcg = ndcg_at_k(retrieved_pmids, relevant, 10)

        results["recall@5"].append(r5)
        results["recall@10"].append(r10)
        results["mrr"].append(rr)
        results["ndcg@10"].append(ndcg)

        per_query.append({
            "variant_id": variant_id,
            "query": query,
            "retrieved_count": len(retrieved_pmids),
            "relevant_count": len(relevant),
            "recall@5": r5,
            "recall@10": r10,
            "mrr": rr,
            "ndcg@10": ndcg,
        })

    return {
        "summary": {k: _mean(v) for k, v in results.items()},
        "per_query": per_query,
    }


def main() -> None:
    args = parse_args()

    variants = load_variants(args.golden_set)
    records = eligible_variants(args.golden_set, variants)
    corpus = build_corpus(records)

    print(f"eligible variants: {len(records)}")
    print(f"corpus size: {len(corpus)}")

    strategies = [
        RetrievalStrategy.BM25,
        RetrievalStrategy.DENSE,
        RetrievalStrategy.HYBRID,
    ]

    report: dict[str, Any] = {
        "metadata": {
            "golden_set_size": len(variants),
            "eligible_size": len(records),
            "corpus_size": len(corpus),
            "top_k": args.top_k,
        },
        "per_variant": build_per_variant(records),
        "strategies": {},
    }

    for strategy in strategies:
        print(f"running {strategy.value}")
        report["strategies"][strategy.value] = run_strategy(
            strategy,
            records,
            corpus,
            args.top_k,
        )

    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"results written to {args.output}")


if __name__ == "__main__":
    main()
