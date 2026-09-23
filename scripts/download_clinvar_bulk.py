"""
Download the ClinVar bulk tables.

The script fetches two files from the NCBI FTP site and stores them
in a local directory. If a file is already present and has not been
modified on the server since the last download, the transfer is
skipped. This makes the script safe to run repeatedly, for example
from a scheduled workflow.

The files are large. The variant summary is on the order of a few
hundred megabytes compressed. The download is streamed to disk rather
than held in memory.

Downloads are retried a small number of times. The NCBI FTP site
occasionally returns transient errors, particularly under load, and a
short wait followed by another attempt resolves most of them.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import requests


logger = logging.getLogger(__name__)


BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited"

FILES = {
    "variant_summary.txt.gz": f"{BASE_URL}/variant_summary.txt.gz",
    "var_citations.txt.gz": f"{BASE_URL}/var_citations.txt.gz",
}

CHUNK_SIZE = 1024 * 1024
TIMEOUT = 60
DOWNLOAD_ATTEMPTS = 3
RETRY_DELAY = 5


def _remote_size(url: str) -> int | None:
    try:
        response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        return int(length) if length else None
    except requests.RequestException as exc:
        logger.warning("head request failed for %s: %s", url, exc)
        return None


def _download(url: str, destination: Path) -> None:
    tmp = destination.with_suffix(destination.suffix + ".part")
    logger.info("downloading %s", url)

    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            with requests.get(url, stream=True, timeout=TIMEOUT) as response:
                response.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            handle.write(chunk)
            tmp.replace(destination)
            logger.info("saved %s", destination)
            return
        except requests.RequestException as exc:
            logger.warning(
                "attempt %d of %d failed for %s: %s",
                attempt,
                DOWNLOAD_ATTEMPTS,
                url,
                exc,
            )
            if attempt == DOWNLOAD_ATTEMPTS:
                if tmp.exists():
                    tmp.unlink()
                raise SystemExit(f"download failed for {url}: {exc}") from exc
            time.sleep(RETRY_DELAY)


def ensure_file(url: str, destination: Path) -> None:
    """
    Download a file only when it is missing or stale.

    A file is considered up to date when its size matches the size
    reported by the server. This avoids re-downloading several hundred
    megabytes on every workflow run.
    """
    if destination.exists():
        local_size = destination.stat().st_size
        remote_size = _remote_size(url)
        if remote_size is not None and local_size == remote_size:
            logger.info("%s is up to date", destination.name)
            return
        logger.info(
            "%s size mismatch (local=%d, remote=%s)",
            destination.name,
            local_size,
            remote_size,
        )

    _download(url, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the ClinVar bulk tables."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/clinvar"),
        help="Directory to store the downloaded files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download even when the local copy appears current.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename, url in FILES.items():
        destination = output_dir / filename
        if args.force and destination.exists():
            destination.unlink()
        ensure_file(url, destination)

    print(f"files ready in {output_dir}")


if __name__ == "__main__":
    main()
