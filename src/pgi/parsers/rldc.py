"""Regional Load Despatch Centre daily operation reports (PDF): NRLDC, WRLDC, SRLDC.

All three carry section "2(A) State's Load Details (At State Periphery) in MU" with one row
per state. The trailing columns differ by region, so each source declares which header
keywords must be present and what its trailing numbers mean. Text is extracted with
pdfplumber; rows are matched by state label.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from . import ParsedReport, ParsedRow, ParseError, norm_label, to_float

# n_values: numeric cells expected per state row in section 2(A)
# tail: meaning of the trailing cells, last cell last
LAYOUTS = {
    "nrldc_psp": {
        "header_keywords": ["REQUIREMENT", "SHORTAGE", "CONSUMPTION"],
        "n_values": 13,
        "tail": ["requirement", "shortage", "met"],
    },
    "wrldc_psp": {
        "header_keywords": ["REQUIREMENT", "SHORTAGE", "CONSUMP"],
        "n_values": 14,
        "tail": ["availability", "requirement", "shortage", "met"],
    },
    "srldc_psp": {
        "header_keywords": ["AVAILABILITY", "DEMANDMET", "SHORTAGE"],
        "n_values": 12,
        "tail": ["availability", "met", "shortage"],
    },
}

NUM = re.compile(r"^-?[\d,]*\.?\d+$|^-$")
DATE_FOR = re.compile(r"FOR(\d{2}-[A-Z]{3}-\d{4})")
DATE_REP = re.compile(r"DATEOFREPORTING:?(\d{2}-[A-Z]{3}-\d{4})")


def _d(s: str):
    return datetime.strptime(s.title(), "%d-%b-%Y").date()


def parse_rldc(source: str, path: Path, aliases: dict[str, list[str]]) -> ParsedReport:
    layout = LAYOUTS[source]
    try:
        with pdfplumber.open(path) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
    except Exception as e:
        raise ParseError(f"cannot open PDF: {e}") from e

    flat = re.sub(r"\s+", "", text).upper()
    m = DATE_FOR.search(flat)
    if not m:
        raise ParseError("operating date ('Power Supply Position ... For <date>') not found")
    operating = _d(m.group(1))
    rep = DATE_REP.search(flat)
    reporting = _d(rep.group(1)) if rep else None

    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.replace(" ", "").startswith("2(A)"))
        end = next(i for i in range(start + 1, len(lines)) if lines[i].replace(" ", "").startswith("2(B)"))
    except StopIteration:
        raise ParseError("section 2(A) not found")
    section = lines[start:end]

    header = re.sub(r"\s+", "", " ".join(section[:12])).upper()
    missing_kw = [k for k in layout["header_keywords"] if k not in header]
    if missing_kw:
        raise ParseError(f"section 2(A) header changed, missing {missing_kw}")

    wanted = {norm_label(a): code for code, labels in aliases.items() for a in labels}
    rows, seen = [], set()
    for offset, ln in enumerate(section):
        tokens = ln.split()
        i = 0
        while i < len(tokens) and not NUM.match(tokens[i]):
            i += 1
        label, values = " ".join(tokens[:i]), tokens[i:]
        code = wanted.get(norm_label(label))
        if not code or code in seen:
            continue
        if len(values) != layout["n_values"] or not all(NUM.match(v) for v in values):
            raise ParseError(
                f"row for {label!r} has {len(values)} values, expected {layout['n_values']}: {ln!r}")
        tail = dict(zip(layout["tail"], (to_float(v) for v in values[-len(layout["tail"]):])))
        seen.add(code)
        rows.append(ParsedRow(
            state_code=code,
            raw_label=label,
            energy_met_mu=tail["met"],
            energy_shortage_mu=tail["shortage"],
            energy_requirement_mu=tail.get("requirement"),
            location=f"section 2(A) line {start + offset + 1}",
        ))
    missing = sorted(set(aliases) - seen)
    return ParsedReport(operating, reporting, rows, missing)
