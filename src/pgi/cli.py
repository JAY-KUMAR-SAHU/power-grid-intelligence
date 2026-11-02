"""Command line: `pgi run | status | report | demo`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, ROOT, load_config
from .pipeline import run
from .report import md_table, write_report
from .warehouse import connect

DEFAULT_LANDING = ROOT / "data" / "landing"
DEFAULT_WAREHOUSE = ROOT / "warehouse"


def _status(warehouse: Path) -> str:
    con = connect(warehouse)
    try:
        runs = con.execute("""SELECT run_id, status, files_new, files_skipped, files_failed, gold_rows_changed,
                                     COALESCE(message, '') FROM pipeline_run ORDER BY run_id DESC LIMIT 10""").fetchall()
        gold = con.execute("""SELECT state_code, operating_date, energy_required_mu, energy_supplied_mu,
                                     energy_shortfall_mu, quality_status, quality_notes
                              FROM gold_state_daily_energy ORDER BY state_code, operating_date""").fetchall()
        failed = con.execute("""SELECT source_id, original_name, parse_error FROM bronze_file
                                WHERE parse_status = 'failed'""").fetchall()
    finally:
        con.close()
    out = ["## Runs (latest 10)", md_table(["Run", "Status", "New", "Skipped", "Failed", "Gold changed", "Message"], runs),
           "", "## Gold", md_table(["State", "Date", "Required", "Supplied", "Shortfall", "Quality", "Notes"], gold)]
    if failed:
        out += ["", "## Quarantined files", md_table(["Source", "File", "Error"], failed)]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pgi", description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--landing", type=Path, default=DEFAULT_LANDING)
    ap.add_argument("--warehouse", type=Path, default=DEFAULT_WAREHOUSE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="ingest landing files and rebuild silver/gold (idempotent)")
    sub.add_parser("status", help="show recent runs, gold rows and quarantined files")
    rp = sub.add_parser("report", help="write the example analysis as Markdown")
    rp.add_argument("--out", type=Path, default=ROOT / "reports" / "analysis.md")
    dp = sub.add_parser("demo", help="scripted demo: first load, rerun, late file, correction")
    dp.add_argument("--out", type=Path, default=ROOT / "reports" / "demo_output.md")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config(args.config)

    if args.cmd == "run":
        print(run(cfg, args.landing, args.warehouse))
    elif args.cmd == "status":
        print(_status(args.warehouse))
    elif args.cmd == "report":
        con = connect(args.warehouse)
        try:
            print(f"wrote {write_report(con, args.out)}")
        finally:
            con.close()
    elif args.cmd == "demo":
        from .demo import run_demo
        print(run_demo(cfg, args.landing, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
