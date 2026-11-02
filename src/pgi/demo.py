"""Reproducible demo of reruns, a late file, a correction and a failed download.

Runs in a fresh temporary workspace (copy of the landing zone + empty warehouse), so it never
touches ./warehouse. Writes a Markdown transcript of every step.
"""
from __future__ import annotations

import csv
import shutil
import tempfile
from pathlib import Path

from .config import ROOT, Config
from .pipeline import run
from .report import md_table
from .warehouse import connect

LATE_FILE = ("srldc_psp", "06-06-2026-psp.pdf")
CORRECTION_DIR = ROOT / "data" / "demo" / "correction"
CORRUPT = ("grid_india_psp", "07.06.26_NLDC_PSP_REDOWNLOAD.xls")


def _add_to_landing(ws_landing: Path, source: str, src_file: Path, manifest_row: dict | None = None) -> None:
    dest = ws_landing / source
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, dest / src_file.name)
    if manifest_row:
        m = dest / "_manifest.csv"
        new = not m.exists()
        with open(m, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file_name", "url", "published_at", "fetched_at", "note"])
            if new:
                w.writeheader()
            w.writerow(manifest_row)


def _q(warehouse: Path, sql: str, params=None):
    con = connect(warehouse)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def _gold_rows(warehouse: Path, state: str, day: str) -> str:
    rows = _q(warehouse, """SELECT state_code, operating_date, energy_required_mu, energy_supplied_mu, energy_shortfall_mu,
                                   primary_file, corroborating_source, quality_status, quality_notes
                            FROM gold_state_daily_energy WHERE state_code = ? AND operating_date = ?""", [state, day])
    return md_table(["State", "Date", "Required", "Supplied", "Shortfall", "Primary file", "Corroborated by",
                     "Quality", "Notes"], rows)


def _integrity(warehouse: Path) -> str:
    total, distinct = _q(warehouse, """SELECT COUNT(*), COUNT(DISTINCT (state_code, operating_date))
                                       FROM gold_state_daily_energy""")[0]
    silver_dupes = _q(warehouse, """SELECT COUNT(*) FROM (SELECT file_id, state_code FROM silver_state_daily
                                    GROUP BY 1, 2 HAVING COUNT(*) > 1)""")[0][0]
    bronze = _q(warehouse, "SELECT COUNT(*) FROM bronze_file")[0][0]
    return (f"Integrity: gold rows={total}, distinct state-days={distinct}, duplicate silver keys={silver_dupes}, "
            f"bronze files={bronze}")


def run_demo(cfg: Config, landing: Path, out: Path) -> str:
    ws = Path(tempfile.mkdtemp(prefix="pgi_demo_"))
    ws_landing, ws_wh = ws / "landing", ws / "warehouse"
    shutil.copytree(landing, ws_landing)
    late_path = ws_landing / LATE_FILE[0] / LATE_FILE[1]
    held_back = ws / "held_back" / LATE_FILE[1]
    held_back.parent.mkdir()
    shutil.move(late_path, held_back)

    log = ["# Pipeline demo: rerun, late file, correction, failed download", "",
           f"Workspace: `{ws}` (temporary copy of `data/landing`, fresh warehouse).", ""]

    def step(title: str, explain: str, *extra) -> None:
        """Run the pipeline, then render `extra` snapshots (callables, evaluated after the run)."""
        s = run(cfg, ws_landing, ws_wh)
        log.extend([f"## {title}", "", explain, "", f"`{s}`", "", _integrity(ws_wh), ""])
        for e in extra:
            log.extend([e(), ""])

    step("Step 1: initial load (SRLDC report for 6 June not yet available)",
         f"`{LATE_FILE[1]}` is held back to simulate a late file. Karnataka on 6 June has only the "
         "Grid-India value, so it is flagged `single_source`.",
         lambda: _gold_rows(ws_wh, "KA", "2026-06-06"))

    step("Step 2: rerun with no new input",
         "Every file is recognised by its content hash and skipped. Gold is recomputed and diffed: "
         "nothing changes, no duplicates are created.")

    shutil.move(held_back, late_path)
    step("Step 3: the late SRLDC file arrives",
         "Only the new file is ingested. Karnataka 6 June is now corroborated and moves from WARN to OK; "
         "the change is recorded in history.",
         lambda: _gold_rows(ws_wh, "KA", "2026-06-06"))

    corr = CORRECTION_DIR / "grid_india_psp"
    meta = next(csv.DictReader(open(corr / "_manifest.csv", encoding="utf-8")))
    _add_to_landing(ws_landing, "grid_india_psp", corr / meta["file_name"], meta)
    step("Step 4: a revised Grid-India report for 5 June is published (SYNTHETIC)",
         "The revision has a later publication time, so it supersedes the original for every state in it. "
         "Uttar Pradesh changes (supplied 592.63 -> 590.13 MU, shortfall 0 -> 2.50 MU); Maharashtra and "
         "Karnataka values are identical, so only their `revised` note changes. Because NRLDC did not revise "
         "its report, UP now disagrees with its corroborating source and is flagged for review. "
         "Both versions remain in silver.",
         lambda: _gold_rows(ws_wh, "UP", "2026-06-05"),
         lambda: md_table(["Source", "File", "Published", "Supplied", "Shortfall"], _q(ws_wh, """
             SELECT s.source_id, b.original_name, strftime(b.published_at, '%Y-%m-%d %H:%M'), s.energy_met_mu, s.energy_shortage_mu
             FROM silver_state_daily s JOIN bronze_file b USING (file_id)
             WHERE s.state_code = 'UP' AND s.operating_date = '2026-06-05' ORDER BY b.published_at""")))

    bad = ws / CORRUPT[1]
    bad.write_bytes((landing / "grid_india_psp" / "07.06.26_NLDC_PSP_969.xls").read_bytes()[:4096])
    _add_to_landing(ws_landing, CORRUPT[0], bad)
    step("Step 5: a truncated re-download lands (failure)",
         "The file cannot be parsed, so it is quarantined with the reason and the run still succeeds. "
         "Gold keeps the last good values.",
         lambda: md_table(["Source", "File", "Status", "Error"], _q(ws_wh, """
             SELECT source_id, original_name, parse_status, parse_error FROM bronze_file
             WHERE parse_status = 'failed'""")))

    step("Step 6: final rerun", "Steady state: nothing new, nothing changes.")

    hist = _q(ws_wh, """SELECT run_id, change_type, state_code, operating_date, old_supplied_mu, new_supplied_mu,
                               old_shortfall_mu, new_shortfall_mu, old_status, new_status, new_notes
                        FROM gold_state_daily_history WHERE change_type <> 'insert' ORDER BY run_id, state_code""")
    log += ["## Gold change history (updates only)", "",
            md_table(["Run", "Change", "State", "Date", "Old supplied", "New supplied", "Old shortfall",
                      "New shortfall", "Old status", "New status", "New notes"], hist), ""]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(log), encoding="utf-8")
    return f"wrote {out}\n\n" + "\n".join(log)
