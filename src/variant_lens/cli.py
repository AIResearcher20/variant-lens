"""
Command-line interface for VariantLens.
"""

from __future__ import annotations

import typer


app = typer.Typer(
    name="variant-lens",
    help="Rare Mendelian variant interpretation using semantic search.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the current version."""
    from . import __version__

    typer.echo(f"variant-lens {__version__}")


if __name__ == "__main__":
    app()
