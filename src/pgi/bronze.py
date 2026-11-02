"""Bronze: register raw files from the landing zone, content-addressed and immutable.

Landing layout: <landing>/<source_id>/<file>, plus an optional _manifest.csv per source with
url, published_at, fetched_at and note for each file (download provenance).
Re-ingesting a file with the same content is a no-op, so reruns never duplicate data.
"""
from __future__ import annotations

import csv
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import SOURCES

DATA_SUFFIXES = {".xls", ".xlsx", ".pdf"}


@dataclass
class IngestResult:
    new: int = 0
    skipped: int = 0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_manifest(source_dir: Path) -> dict[str, dict]:
    m = source_dir / "_manifest.csv"
    if not m.exists():
        return {}
    with open(m, newline="", encoding="utf-8") as f:
        return {row["file_name"]: row for row in csv.DictReader(f)}


def ingest(con, landing: Path, bronze_dir: Path, run_id: int) -> IngestResult:
    res = IngestResult()
    for source in SOURCES:
        src_dir = landing / source
        if not src_dir.is_dir():
            continue
        meta = _read_manifest(src_dir)
        for path in sorted(src_dir.iterdir()):
            if path.suffix.lower() not in DATA_SUFFIXES:
                continue
            file_id = sha256(path)
            if con.execute("SELECT 1 FROM bronze_file WHERE file_id = ?", [file_id]).fetchone():
                res.skipped += 1
                continue
            dest = bronze_dir / source / f"{file_id}{path.suffix.lower()}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(path, dest)
            m = meta.get(path.name, {})
            con.execute(
                """INSERT INTO bronze_file (file_id, source_id, original_name, bronze_path, size_bytes, url,
                       published_at, note, first_seen_run, ingested_at, parse_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                [file_id, source, path.name, dest.relative_to(bronze_dir.parent).as_posix(), path.stat().st_size, m.get("url") or None,
                 m.get("published_at") or None, m.get("note") or None, run_id, datetime.now()],
            )
            res.new += 1
    return res
