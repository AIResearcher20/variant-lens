"""
ClinVar lookups against the local bulk tables.

This module is the interface between the golden set builder and the
ClinVar bulk data. It does not perform any network calls. The bulk
files are expected to have been downloaded beforehand into a known
directory.

The design separates two concerns. The heavy lifting of reading and
indexing the ClinVar tables is handled by clinvar_bulk. This module
adds the lookup semantics that the golden set needs: given a gene and
an HGVS string, return the variation identifier; given a variation
identifier, return the linked PubMed identifiers.

Caching is handled at the level of the caller. The bulk tables are
loaded once per process and passed around as plain dictionaries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .clinvar_bulk import (
    build_wanted_index,
    parse_citations,
    parse_variant_summary,
    strip_deleted_bases,
)


logger = logging.getLogger(__name__)


VARIANT_SUMMARY_FILENAME = "variant_summary.txt.gz"
VAR_CITATIONS_FILENAME = "var_citations.txt"


class ClinVarBulk:
    """
    In-memory view of the ClinVar bulk data for a set of variants.

    The constructor loads the two tables and keeps only the entries
    that are relevant to the variants passed in. Everything else is
    discarded as it is read, so memory use stays small even though the
    underlying files are large.
    """

    def __init__(
        self,
        bulk_dir: Path,
        variants: list[dict[str, str]],
    ) -> None:
        self.bulk_dir = Path(bulk_dir)
        self.variants = variants
        self.summary: dict[str, dict[str, Any]] = {}
        self.citations: dict[str, list[str]] = {}
        self._index: dict[tuple[str, str], str] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return

        summary_path = self.bulk_dir / VARIANT_SUMMARY_FILENAME
        citations_path = self.bulk_dir / VAR_CITATIONS_FILENAME

        if not summary_path.exists():
            raise FileNotFoundError(f"missing {summary_path}")
        if not citations_path.exists():
            raise FileNotFoundError(f"missing {citations_path}")

        wanted = build_wanted_index(self.variants)
        self.summary = parse_variant_summary(summary_path, wanted=wanted)

        wanted_ids = set(self.summary.keys())
        self.citations = parse_citations(
            citations_path,
            wanted_variation_ids=wanted_ids,
        )

        for variation_id, entry in self.summary.items():
            gene = entry.get("gene") or ""
            hgvs = entry.get("hgvs_c") or ""
            if not gene or not hgvs:
                continue
            self._index[(gene, hgvs)] = variation_id
            self._index[(gene, strip_deleted_bases(hgvs))] = variation_id

        self._loaded = True

        logger.info(
            "ClinVar bulk loaded: %d variants, %d with citations",
            len(self.summary),
            len(self.citations),
        )

    def find_variation_id(self, gene: str, hgvs: str) -> str | None:
        """
        Return the VariationID for a gene and HGVS pair.

        Two forms are tried: the exact HGVS string and the form with
        trailing nucleotide letters removed. This covers the case where
        the caller writes c.68_69delAG and ClinVar stores c.68_69del.
        """
        if not self._loaded:
            self.load()

        direct = self._index.get((gene, hgvs))
        if direct is not None:
            return direct

        return self._index.get((gene, strip_deleted_bases(hgvs)))

    def get_linked_pmids(self, variation_id: str) -> list[str]:
        if not self._loaded:
            self.load()
        return list(self.citations.get(variation_id, []))

    def lookup(self, gene: str, hgvs: str) -> dict[str, Any]:
        """
        Return a compact record for a variant.

        The result contains the VariationID, the linked PMIDs, and a
        few fields from the summary table that are useful for logging
        and for the evidence file. An empty result is returned when the
        variant is not present in the bulk tables.
        """
        variation_id = self.find_variation_id(gene, hgvs)
        if variation_id is None:
            return {
                "variation_id": None,
                "pmids": [],
                "summary": {},
            }

        entry = self.summary.get(variation_id, {})
        return {
            "variation_id": variation_id,
            "pmids": self.get_linked_pmids(variation_id),
            "summary": {
                "name": entry.get("name", ""),
                "clinical_significance": entry.get("clinical_significance", ""),
                "review_status": entry.get("review_status", ""),
                "phenotypes": entry.get("phenotypes", ""),
                "chromosome": entry.get("chromosome", ""),
                "position_vcf": entry.get("position_vcf"),
                "ref_vcf": entry.get("ref_vcf", ""),
                "alt_vcf": entry.get("alt_vcf", ""),
            },
        }
