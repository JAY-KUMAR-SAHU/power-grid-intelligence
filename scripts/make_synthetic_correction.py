"""Create the SYNTHETIC revised Grid-India report used by the correction demo.

No revised daily PSP report was published for 2-8 June 2026, so this script simulates one:
it copies sheet MOP_E of the real 05.06.26 report and changes Uttar Pradesh's row as if
load shedding of 2.50 MU had been reported late (Energy Met 592.63 -> 590.13,
Energy Shortage 0 -> 2.50; requirement unchanged). Everything else is copied as-is.

Run:  python scripts/make_synthetic_correction.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "landing" / "grid_india_psp" / "05.06.26_NLDC_PSP_700.xls"
OUT_DIR = ROOT / "data" / "demo" / "correction" / "grid_india_psp"
OUT = OUT_DIR / "05.06.26_NLDC_PSP_REVISED_SYNTHETIC.xlsx"

df = pd.read_excel(SRC, sheet_name="MOP_E", header=None, engine="calamine")
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "MOP_E"
changed = 0
for r, row in enumerate(df.itertuples(index=False), start=1):
    vals = [None if pd.isna(v) else v for v in row]
    if len(vals) > 1 and vals[1] == "UP":
        assert vals[4] == 592.63 and vals[8] == 0, f"unexpected source values {vals}"
        vals[4], vals[8] = 590.13, 2.5
        changed += 1
    for c, v in enumerate(vals, start=1):
        ws.cell(row=r, column=c, value=v)
assert changed == 1
OUT_DIR.mkdir(parents=True, exist_ok=True)
wb.save(OUT)

with open(OUT_DIR / "_manifest.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["file_name", "url", "published_at", "fetched_at", "note"])
    w.writerow([OUT.name, "", "2026-06-09T18:00:00+05:30", "",
                "SYNTHETIC revision for demo; derived from 05.06.26_NLDC_PSP_700.xls (UP met 592.63->590.13, shortage 0->2.50)"])
print(f"wrote {OUT.relative_to(ROOT)}")
