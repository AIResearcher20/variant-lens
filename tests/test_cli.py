"""
Tests for the VariantLens CLI.

Uses typer's CliRunner. Network calls are bypassed by monkeypatching
get_raw_evidence.
"""

from typer.testing import CliRunner

from variant_lens.cli import app
from variant_lens.schema import RawEvidence


runner = CliRunner()


def _fake_evidence(hgvs: str) -> list[RawEvidence]:
    return [
        RawEvidence(
            source="gnomad",
            version=None,
            query=hgvs,
            retrieved_at="2026-01-01T00:00:00Z",
            endpoint="https://example.org/gnomad",
            response_hash="0" * 64,
            payload={"af": 0.0001},
        ),
        RawEvidence(
            source="clinvar",
            version=None,
            query=hgvs,
            retrieved_at="2026-01-01T00:00:00Z",
            endpoint="https://example.org/clinvar",
            response_hash="0" * 64,
            payload={
                "clinvar_significance": "Pathogenic",
                "clinvar_review_status": "criteria provided",
                "clinvar_variation_id": "12345",
                "phenotype": "Hereditary breast cancer",
                "hgvs_c": "c.68_69delAG",
                "hgvs_p": "p.Glu23ValfsTer17",
                "gene": "BRCA1",
            },
        ),
        RawEvidence(
            source="pubmed",
            version=None,
            query=hgvs,
            retrieved_at="2026-01-01T00:00:00Z",
            endpoint="https://example.org/pubmed",
            response_hash="0" * 64,
            payload={"count": 0, "pmids": []},
        ),
    ]


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "variant-lens" in result.stdout


def test_interpret_command_writes_report(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "variant_lens.cli.get_raw_evidence",
        _fake_evidence,
    )

    output = tmp_path / "report.json"
    result = runner.invoke(
        app,
        ["interpret", "BRCA1 c.68_69delAG", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert output.exists()
    content = output.read_text()
    assert "BRCA1" in content
    assert "Pathogenic" in content


def test_interpret_command_handles_unparseable_input(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "variant_lens.cli.get_raw_evidence",
        _fake_evidence,
    )

    output = tmp_path / "report.json"
    result = runner.invoke(
        app,
        ["interpret", "not-a-variant", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert output.exists()
    content = output.read_text()
    assert "not-a-variant" in content
