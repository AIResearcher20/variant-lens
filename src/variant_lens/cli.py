"""
Command-line interface for VariantLens.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__
from .annotate import AnnotationError, annotate
from .fetch import get_raw_evidence
from .parse import parse_variant
from .rank import rerank
from .report import generate, to_json
from .retrieve import retrieve
from .schema import RetrievalStrategy


app = typer.Typer(
    name="variant-lens",
    help="Rare Mendelian variant interpretation using semantic search.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the current version."""
    typer.echo(f"variant-lens {__version__}")


@app.command()
def interpret(
    variant: str = typer.Argument(..., help="HGVS or VCF-style variant string."),
    output: Path = typer.Option(
        Path("report.json"),
        "--output",
        "-o",
        help="Path to write the JSON report.",
    ),
    top_k: int = typer.Option(
        10,
        "--top-k",
        help="Number of ranked passages to include.",
    ),
) -> None:
    """
    Interpret a variant and write a JSON report.

    The pipeline runs parse, fetch, annotate, retrieve, rerank, and report.
    Retrieval only runs when the variant is parseable and supported.
    """
    parsed = parse_variant(variant)

    try:
        evidence = get_raw_evidence(variant)
    except Exception as exc:
        typer.echo(f"Fetch failed: {exc}", err=True)
        raise typer.Exit(code=1)

    try:
        annotation = annotate(parsed, evidence)
    except AnnotationError as exc:
        report = _unparseable_report(variant, parsed, str(exc))
        output.write_text(to_json(report))
        typer.echo(f"Report written to {output}")
        return

    passages = retrieve(
        query=_build_query(annotation),
        passages=[],
        strategy=RetrievalStrategy.BM25,
        top_k=50,
    )

    ranked = rerank(_build_query(annotation), passages, top_k=top_k)

    report = generate(annotation, ranked)
    output.write_text(to_json(report))

    typer.echo(f"Report written to {output}")


def _build_query(annotation) -> str:
    """Build a retrieval query from the annotation."""
    parts = [annotation.gene or ""]
    if annotation.hgvs_c:
        parts.append(annotation.hgvs_c)
    if annotation.phenotype:
        parts.append(annotation.phenotype)
    return " ".join(p for p in parts if p).strip()


def _unparseable_report(variant: str, parsed, reason: str) -> dict:
    """Build a minimal report when annotation is not possible."""
    return {
        "variant": {
            "input": variant,
            "is_parseable": parsed.is_parseable,
            "is_supported": parsed.is_supported,
            "variant_type": parsed.variant_type.value,
        },
        "error": reason,
        "evidence": {},
        "passages": [],
    }


if __name__ == "__main__":
    app()
