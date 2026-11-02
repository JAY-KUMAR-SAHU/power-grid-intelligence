"""One pipeline run: ingest (bronze) -> parse (silver) -> DQ + gold, recorded in pipeline_run.

Failure handling
- Bronze registration is committed on its own: raw files are safe even if later steps fail.
- Parse failures are per file: the file is quarantined and the run continues.
- Silver, DQ results and gold are written in one transaction. Any exception rolls it back,
  leaving the previous gold intact, and marks the run failed. Rerunning is always safe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .bronze import ingest
from .config import Config
from .gold import build_gold
from .silver import parse_pending
from .warehouse import connect

DQ_COLS = ("run_id", "check_id", "severity", "scope", "source_id", "file_id", "state_code", "operating_date", "detail")


@dataclass
class RunSummary:
    run_id: int
    status: str
    files_new: int
    files_skipped: int
    files_failed: int
    gold_rows: int
    gold_rows_changed: int
    message: str = ""

    def __str__(self) -> str:
        return (f"run {self.run_id}: {self.status} | files new={self.files_new} skipped={self.files_skipped} "
                f"failed={self.files_failed} | gold rows={self.gold_rows} changed={self.gold_rows_changed}"
                + (f" | {self.message}" if self.message else ""))


def run(cfg: Config, landing: Path, warehouse_dir: Path) -> RunSummary:
    con = connect(warehouse_dir)
    run_id = None
    try:
        run_id = con.execute("SELECT nextval('run_seq')").fetchone()[0]
        con.execute("INSERT INTO pipeline_run (run_id, started_at, status) VALUES (?, ?, 'running')",
                    [run_id, datetime.now()])

        ing = ingest(con, landing, warehouse_dir / "bronze", run_id)

        con.execute("BEGIN TRANSACTION")
        try:
            parsed = parse_pending(con, cfg, run_id, warehouse_dir)
            gold = build_gold(con, cfg, run_id)
            dq = parsed.dq + gold.dq
            if dq:
                con.executemany(f"INSERT INTO dq_result ({', '.join(DQ_COLS)}) VALUES ({', '.join('?' * len(DQ_COLS))})",
                                [[d.get(c) for c in DQ_COLS] for d in dq])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

        summary = RunSummary(run_id, "success", ing.new, ing.skipped, parsed.failed, gold.rows, gold.changed)
        con.execute(
            """UPDATE pipeline_run SET finished_at=?, status='success', files_new=?, files_skipped=?,
                   files_failed=?, gold_rows_changed=? WHERE run_id=?""",
            [datetime.now(), ing.new, ing.skipped, parsed.failed, gold.changed, run_id])
        return summary
    except Exception as e:
        if run_id is not None:
            con.execute("UPDATE pipeline_run SET finished_at=?, status='failed', message=? WHERE run_id=?",
                    [datetime.now(), f"{type(e).__name__}: {e}", run_id])
        raise
    finally:
        con.close()
