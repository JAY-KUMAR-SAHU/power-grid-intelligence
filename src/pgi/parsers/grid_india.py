"""Grid-India (NLDC) Daily Power Supply Position report, Excel version.

Sheet MOP_E, section "C. Power Supply Position in States": one row per state with
Energy Met (MU) and Energy Shortage (MU). Requirement is not reported.
The report is published the morning after the operating day ("Report for previous day").
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from . import ParsedReport, ParsedRow, ParseError, norm_label, to_float

SHEET = "MOP_E"
SECTION = "C. POWER SUPPLY POSITION IN STATES"
NEXT_SECTION = "D. TRANSNATIONAL"


def _cell(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


def _parse_date(v):
    if isinstance(v, datetime):
        return v.date()
    return datetime.strptime(_cell(v), "%d-%b-%Y").date()


def parse(path: Path, aliases: dict[str, list[str]]) -> ParsedReport:
    try:
        df = pd.read_excel(path, sheet_name=SHEET, header=None, engine="calamine")
    except Exception as e:  # missing sheet, corrupt workbook
        raise ParseError(f"cannot read sheet {SHEET}: {e}") from e
    grid = [[_cell(v) for v in row] for row in df.itertuples(index=False)]

    # Reporting date: the cell after "Date of Reporting:".
    reporting = None
    for r, row in enumerate(grid[:10]):
        for c, v in enumerate(row):
            if v.startswith("Date of Reporting"):
                nxt = next((x for x in row[c + 1:] if x), None)
                if nxt:
                    reporting = _parse_date(df.iat[r, row.index(nxt, c + 1)])
    if reporting is None:
        raise ParseError("'Date of Reporting' not found")
    if not any("previous day" in v.lower() for row in grid[:10] for v in row):
        raise ParseError("'Report for previous day' marker not found; date semantics unknown")
    operating = reporting - timedelta(days=1)

    # Section C bounds and the two header rows below its title.
    try:
        start = next(r for r, row in enumerate(grid) if row[0].upper().startswith(SECTION))
    except StopIteration:
        raise ParseError(f"section {SECTION!r} not found")
    end = next((r for r in range(start + 1, len(grid)) if grid[r][0].upper().startswith(NEXT_SECTION)), len(grid))
    h1, h2 = grid[start + 1], grid[start + 2]
    headers = [f"{a} {b}".strip().lower() for a, b in zip(h1, h2)]
    try:
        met_col = next(i for i, h in enumerate(headers) if h.startswith("energy met"))
        short_col = next(i for i, h in enumerate(headers) if h.startswith("energy") and "shortage (mu)" in h)
        state_col = next(i for i, h in enumerate(headers) if "states" in h)
    except StopIteration:
        raise ParseError(f"state table headers changed: {headers}")

    wanted = {norm_label(a): code for code, labels in aliases.items() for a in labels}
    rows, seen = [], set()
    for r in range(start + 3, end):
        label = grid[r][state_col]
        code = wanted.get(norm_label(label))
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append(ParsedRow(
            state_code=code,
            raw_label=label,
            energy_met_mu=to_float(grid[r][met_col]),
            energy_shortage_mu=to_float(grid[r][short_col]),
            energy_requirement_mu=None,
            location=f"{SHEET}!R{r + 1}",
        ))
    missing = sorted(set(aliases) - seen)
    return ParsedReport(operating, reporting, rows, missing)
