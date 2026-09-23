"""
Reader for the ClinVar bulk tables.

ClinVar publishes its complete catalogue as tab-separated files on the
NCBI FTP site. Two files matter for building the golden set.

The first is variant_summary, which lists every variant along with its
gene symbol, HGVS name, clinical significance, and genomic position.

The second is var_citations, which links each variation identifier to
the PubMed articles that the ClinVar record cites.

This module reads both files and returns compact dictionaries that the
rest of the pipeline can query in constant time. It does not perform
any network calls. Downloading is handled elsewhere.

HGVS matching is deliberately tolerant. ClinVar and external sources
often write the same variant in slightly different ways. For example,
older exports of the deletion c.68_69delAG now appear as c.68_69del,
and both forms refer to the same record. The parser produces several
keys for each variant so that any of these forms resolves.
"""

from __future__ import annotations

import csv
import gzip
import logging
import re
from pathlib import Path
from typing import Any, Iterable, Iterator


logger = logging.getLogger(__name__)


HGVS_PATTERN = re.compile(r"(c\.[0-9A-Za-z_>*+\-]+)")


def _open_maybe_gzip(path: Path) -> Iterator[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line
    else:
        with path.open("rt", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line


def extract_hgvs(name: str) -> str | None:
    """
    Pull the HGVS coding sequence from a variant name.

    The name field in variant_summary looks like
    'NM_007294.4(BRCA1):c.68_69del (p.Glu23fs)'. Only the c. part is
    needed for matching against the variants table.
    """
    if not name:
        return None
    match = HGVS_PATTERN.search(name)
    if match:
        return match.group(1)
    return None


def strip_deleted_bases(hgvs: str) -> str:
    """
    Remove nucleotide letters that follow del, ins, or dup.

    HGVS used to write c.68_69delAG to list the bases that were
    removed. Current ClinVar records use c.68_69del instead. Both
    describe the same variant. The shorter form is produced here so
    that matching across sources succeeds.
    """
    result = hgvs
    for suffix in ("del", "ins", "dup"):
        pattern = rf"({suffix})[ACGTNacgtn]+$"
        result = re.sub(pattern, r"\1", result)
    return result


def position_token(hgvs: str) -> str | None:
    """
    Extract the numeric position or range from an HGVS string.

    For c.68_69delAG this returns '68_69'. For c.20A>T it returns
    '20A>T'. This key is used as a fallback when the exact HGVS does
    not match, which happens when one source writes the variant in a
    shortened or expanded form.
    """
    if not hgvs:
        return None
    body = hgvs
    for prefix in ("c.", "g.", "m.", "n.", "p."):
        if body.startswith(prefix):
            body = body[len(prefix):]
            break
    return body or None


def parse_variant_summary(
    path: Path,
    wanted: dict[str, set[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Read variant_summary and return entries keyed by VariationID.

    The file is large, on the order of a few million rows. Passing the
    wanted argument restricts the output to the variants of interest.
    It expects a mapping from gene symbol to a set of HGVS strings. A
    row is kept when the gene matches and the HGVS matches either the
    exact string or its shortened form.

    When wanted is None, every row is kept. That mode is only useful
    for small test fixtures.
    """
    rows: dict[str, dict[str, Any]] = {}
    reader = csv.DictReader(_open_maybe_gzip(path), delimiter="\t")

    kept = 0
    seen = 0

    expanded_wanted: dict[str, set[str]] = {}
    if wanted is not None:
        for gene, hgvs_set in wanted.items():
            forms: set[str] = set()
            for hgvs in hgvs_set:
                forms.add(hgvs)
                forms.add(strip_deleted_bases(hgvs))
            expanded_wanted[gene] = forms

    for row in reader:
        seen += 1
        gene = (row.get("GeneSymbol") or "").strip()
        name = (row.get("Name") or "").strip()
        variation_id = (row.get("VariationID") or "").strip()

        if not variation_id:
            continue

        if expanded_wanted is not None:
            if gene not in expanded_wanted:
                continue
            hgvs = extract_hgvs(name)
            if hgvs is None:
                continue
            hgvs_short = strip_deleted_bases(hgvs)
            if hgvs not in expanded_wanted[gene] and hgvs_short not in expanded_wanted[gene]:
                continue

        rows[variation_id] = {
            "variation_id": variation_id,
            "gene": gene,
            "name": name,
            "hgvs_c": extract_hgvs(name),
            "clinical_significance": (row.get("ClinicalSignificance") or "").strip(),
            "review_status": (row.get("ReviewStatus") or "").strip(),
            "phenotypes": (row.get("PhenotypeList") or "").strip(),
            "chromosome": (row.get("Chromosome") or "").strip(),
            "position_vcf": row.get("PositionVCF"),
            "ref_vcf": (row.get("ReferenceAlleleVCF") or "").strip(),
            "alt_vcf": (row.get("AlternateAlleleVCF") or "").strip(),
        }
        kept += 1

    logger.info("variant_summary: %d rows seen, %d kept", seen, kept)
    return rows


def parse_citations(
    path: Path,
    wanted_variation_ids: set[str] | None = None,
) -> dict[str, list[str]]:
    """
    Read var_citations and return PMIDs keyed by VariationID.

    A single variation can appear on multiple lines, one per linked
    article. The result collects them into a list and removes
    duplicates.

    The column that carries the PubMed identifier has changed name
    over time. Older exports used PubMedID, newer ones use citation_id.
    Both are accepted.
    """
    citations: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    reader = csv.DictReader(_open_maybe_gzip(path), delimiter="\t")

    total = 0
    kept = 0

    for row in reader:
        total += 1
        variation_id = (row.get("VariationID") or "").strip()
        pmid = (
            row.get("citation_id")
            or row.get("PubMedID")
            or row.get("pmid")
            or ""
        ).strip()

        if not variation_id or not pmid:
            continue

        if wanted_variation_ids is not None and variation_id not in wanted_variation_ids:
            continue

        if variation_id not in seen:
            seen[variation_id] = set()
            citations[variation_id] = []

        if pmid in seen[variation_id]:
            continue

        seen[variation_id].add(pmid)
        citations[variation_id].append(pmid)
        kept += 1

    logger.info("var_citations: %d rows seen, %d kept", total, kept)
    return citations


def build_wanted_index(
    variants: Iterable[dict[str, str]],
) -> dict[str, set[str]]:
    """
    Group the variants table by gene for quick lookup.

    The result is a mapping from gene symbol to a set of HGVS strings.
    It is passed to parse_variant_summary so that the large summary
    file can be filtered while it is being read, instead of being
    loaded into memory in full.
    """
    index: dict[str, set[str]] = {}
    for row in variants:
        gene = (row.get("gene") or "").strip()
        hgvs = (row.get("hgvs") or "").strip()
        if not gene or not hgvs:
            continue
        index.setdefault(gene, set()).add(hgvs)
    return index
