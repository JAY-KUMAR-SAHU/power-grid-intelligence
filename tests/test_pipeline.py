"""End-to-end behaviour: reruns, corrections, out-of-order versions, failures, gaps, scope changes."""
import csv
import dataclasses
import shutil
from datetime import date

from conftest import query

from pgi.config import ROOT
from pgi.pipeline import run

CORR = ROOT / "data" / "demo" / "correction" / "grid_india_psp" / "05.06.26_NLDC_PSP_REVISED_SYNTHETIC.xlsx"


def gold(wh, state, day):
    return query(wh, """SELECT energy_supplied_mu, energy_shortfall_mu, energy_required_mu, primary_source,
                               quality_status, quality_notes
                        FROM gold_state_daily_energy WHERE state_code=? AND operating_date=?""", [state, day])[0]


def add_file(landing, source, src, published_at="", note=""):
    shutil.copy2(src, landing / source / src.name)
    with open(landing / source / "_manifest.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([src.name, "", published_at, "", note])


def test_initial_load_all_corroborated(ws):
    wh = ws / "warehouse"
    assert query(wh, "SELECT COUNT(*), COUNT(*) FILTER (WHERE quality_status='OK') FROM gold_state_daily_energy")[0] == (21, 21)
    # required is derived as supplied + shortfall
    assert gold(wh, "MH", "2026-06-03")[:3] == (664.5, 0.93, 665.43)


def test_rerun_is_idempotent(ws, cfg):
    wh = ws / "warehouse"
    before = query(wh, "SELECT * EXCLUDE (last_changed_run) FROM gold_state_daily_energy ORDER BY ALL")
    s = run(cfg, ws / "landing", wh)
    assert (s.files_new, s.files_skipped, s.gold_rows_changed) == (0, 28, 0)
    assert query(wh, "SELECT * EXCLUDE (last_changed_run) FROM gold_state_daily_energy ORDER BY ALL") == before
    assert query(wh, "SELECT COUNT(*) FROM silver_state_daily")[0][0] == 42  # 21 primary + 21 RLDC


def test_same_content_under_new_name_is_not_duplicated(ws, cfg):
    src = ws / "landing" / "nrldc_psp" / "daily020626.pdf"
    shutil.copy2(src, src.with_name("daily020626_copy.pdf"))
    s = run(cfg, ws / "landing", ws / "warehouse")
    assert (s.files_new, s.gold_rows_changed) == (0, 0)


def test_correction_supersedes_and_is_audited(ws, cfg):
    wh = ws / "warehouse"
    add_file(ws / "landing", "grid_india_psp", CORR, "2026-06-09T18:00:00+05:30", "SYNTHETIC")
    s = run(cfg, ws / "landing", wh)
    assert s.files_new == 1
    supplied, shortfall, required, src, status, notes = gold(wh, "UP", "2026-06-05")
    assert (supplied, shortfall, required, src) == (590.13, 2.5, 592.63, "grid_india_psp")
    assert status == "WARN" and "revised(v2)" in notes and "sources_disagree" in notes
    hist = query(wh, """SELECT old_supplied_mu, new_supplied_mu FROM gold_state_daily_history
                        WHERE change_type='update' AND state_code='UP' AND operating_date='2026-06-05'""")
    assert hist == [(592.63, 590.13)]
    # both versions kept in silver
    assert query(wh, """SELECT COUNT(*) FROM silver_state_daily
                        WHERE source_id='grid_india_psp' AND state_code='UP' AND operating_date='2026-06-05'""")[0][0] == 2


def test_older_version_arriving_late_does_not_override(ws, cfg):
    wh = ws / "warehouse"
    # same alternative content, but published BEFORE the file already loaded
    add_file(ws / "landing", "grid_india_psp", CORR, "2026-06-06T08:00:00+05:30", "stale copy")
    run(cfg, ws / "landing", wh)
    assert gold(wh, "UP", "2026-06-05")[:2] == (592.63, 0.0)


def test_unparseable_file_is_quarantined_and_gold_falls_back(ws, cfg):
    wh, landing = ws / "warehouse", ws / "landing"
    # fresh warehouse where the only Grid-India file for 7 June is corrupt
    good = landing / "grid_india_psp" / "07.06.26_NLDC_PSP_969.xls"
    good.write_bytes(good.read_bytes()[:4096])
    fresh = ws / "fresh_wh"
    s = run(cfg, landing, fresh)
    assert s.status == "success" and s.files_failed == 1
    supplied, _, _, src, status, notes = gold(fresh, "UP", "2026-06-07")
    assert (supplied, src, status) == (630.48, "nrldc_psp", "WARN")
    assert "fallback_to_nrldc_psp" in notes and "single_source" in notes
    assert query(fresh, "SELECT COUNT(*) FROM dq_latest WHERE check_id='parse_failed'")[0][0] == 1
    assert wh.exists()  # original workspace untouched


def test_missing_data_is_explicit(ws, cfg):
    landing = ws / "landing"
    (landing / "srldc_psp" / "08-06-2026-psp.pdf").unlink()
    (landing / "grid_india_psp" / "08.06.26_NLDC_PSP_354.xls").unlink()
    fresh = ws / "fresh_wh"
    run(cfg, landing, fresh)
    row = gold(fresh, "KA", "2026-06-08")
    assert row[0] is None and row[4] == "MISSING"
    assert query(fresh, "SELECT COUNT(*) FROM gold_state_daily_energy")[0][0] == 21


def test_scope_change_is_audited(ws, cfg):
    wh = ws / "warehouse"
    narrower = dataclasses.replace(cfg, end=date(2026, 6, 7))
    s = run(narrower, ws / "landing", wh)
    assert s.gold_rows == 18 and s.gold_rows_changed == 3
    assert query(wh, "SELECT COUNT(*) FROM gold_state_daily_history WHERE change_type='delete'")[0][0] == 3
