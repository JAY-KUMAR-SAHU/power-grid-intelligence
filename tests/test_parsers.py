"""Parser tests against the committed real samples. Expected values were read off the source reports."""
from datetime import date

import pytest

from pgi.config import ROOT
from pgi.parsers import ParseError, parse_file

L = ROOT / "data" / "landing"
ALL = {"UP": ["UP"], "MH": ["MAHARASHTRA"], "KA": ["KARNATAKA"]}


def vals(rep):
    return {r.state_code: (r.energy_met_mu, r.energy_shortage_mu, r.energy_requirement_mu) for r in rep.rows}


def test_grid_india_state_table():
    rep = parse_file("grid_india_psp", L / "grid_india_psp" / "02.06.26_NLDC_PSP_169.xls", ALL)
    assert rep.operating_date == date(2026, 6, 2)      # "Report for previous day", reported 03-Jun
    assert rep.reporting_date == date(2026, 6, 3)
    assert vals(rep) == {"UP": (560.98, 0.0, None), "MH": (646.8, 0.14, None), "KA": (279.67, 0.0, None)}
    assert rep.missing_states == []


def test_nrldc_reports_requirement():
    rep = parse_file("nrldc_psp", L / "nrldc_psp" / "daily020626.pdf", {"UP": ["UTTARPRADESH"]})
    assert rep.operating_date == date(2026, 6, 2)
    assert vals(rep) == {"UP": (560.98, 0.0, 560.98)}


def test_wrldc_rounded_requirement():
    rep = parse_file("wrldc_psp", L / "wrldc_psp" / "WRLDC_PSP_Report_03-06-2026.pdf", {"MH": ["MAHARASHTRA"]})
    assert rep.operating_date == date(2026, 6, 3)
    assert vals(rep) == {"MH": (664.5, 0.93, 665.4)}


@pytest.mark.parametrize("name,met", [("02-06-2026-psp.pdf", 279.67),   # old layout
                                      ("03-06-2026-psp.pdf", 274.44)])  # new layout from 3 June
def test_srldc_both_layouts(name, met):
    rep = parse_file("srldc_psp", L / "srldc_psp" / name, {"KA": ["KARNATAKA"]})
    assert vals(rep)["KA"] == (met, 0.0, None)


@pytest.mark.parametrize("source", ["grid_india_psp", "nrldc_psp", "wrldc_psp", "srldc_psp"])
def test_every_sample_parses_to_its_own_day(source):
    files = sorted(p for p in (L / source).iterdir() if not p.name.startswith("_"))
    assert len(files) == 7
    days = [parse_file(source, f, ALL).operating_date for f in files]
    assert days == [date(2026, 6, d) for d in range(2, 9)]


def test_unknown_state_is_reported_missing_not_guessed():
    rep = parse_file("grid_india_psp", L / "grid_india_psp" / "02.06.26_NLDC_PSP_169.xls", {"XX": ["ATLANTIS"]})
    assert rep.rows == [] and rep.missing_states == ["XX"]


def test_corrupt_file_raises(tmp_path):
    bad = tmp_path / "bad.xls"
    bad.write_bytes((L / "grid_india_psp" / "02.06.26_NLDC_PSP_169.xls").read_bytes()[:2048])
    with pytest.raises(ParseError):
        parse_file("grid_india_psp", bad, ALL)
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"%PDF-1.5 not really")
    with pytest.raises(ParseError):
        parse_file("nrldc_psp", pdf, ALL)
