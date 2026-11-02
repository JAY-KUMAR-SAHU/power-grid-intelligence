# power-grid-intelligence

A reliable daily state-level dataset of electricity **required, supplied and shortfall** (MU) for
three Indian states, built bronze → silver → gold from two independent report types published by
Grid Controller of India.

| Scope | |
|---|---|
| States | Uttar Pradesh (Northern region), Maharashtra (Western), Karnataka (Southern): one per region |
| Window | 2 – 8 June 2026 (summer peak week), IST operating days |
| Sources | Grid-India NLDC *Daily PSP Report* (XLS) as primary; NRLDC / WRLDC / SRLDC *Daily Operation Report* (PDF) to corroborate and as fallback |
| Stack | Python 3.12, DuckDB, pdfplumber, calamine; plain CLI; pytest |

All 28 downloaded source files are committed under `data/landing/`, so everything below runs
offline.

---

## Quick start

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

pgi run        # ingest -> parse -> DQ -> gold (rerun any time; it is idempotent)
pgi status     # recent runs, gold rows, quarantined files
pgi report     # writes reports/analysis.md (example analysis)
pgi demo       # writes reports/demo_output.md (rerun, late file, correction, failure)
pytest         # 19 tests, ~1 min
```

`python -m pgi ...` works too. The warehouse lives in `./warehouse/` (DuckDB file +
content-addressed bronze copies) and can be deleted at any time; `pgi run` rebuilds it.

Committed outputs: [`reports/analysis.md`](reports/analysis.md) and
[`reports/demo_output.md`](reports/demo_output.md).

---

## 1. Sources and why

| Source | Publisher | Format | Why |
|---|---|---|---|
| `grid_india_psp`: Daily PSP Report | NLDC (national) | XLS + PDF; the **XLS** is used | One national report covering every state with consistent definitions; machine-readable, so one robust parser. Published ~09:30–11:00 IST the next day. |
| `nrldc_psp`, `wrldc_psp`, `srldc_psp`: Daily Operation Report | Regional LDCs | PDF | The regional operator's own report, a different report type and publication channel. It carries more detail, including explicitly reported **Requirement** (NR, WR). Used to corroborate NLDC and to fill in if NLDC is missing or broken. |

**Not used:** CEA monthly Power Supply Position (monthly grain; a natural future reconciliation
target), Vidyut Pravah / MERIT dashboards (no stable archive, so not reproducible).

**Limitations**
- Shortfall is **self-reported** by states (load-shedding details furnished to the RLDC), so it is a
  lower bound. SRLDC's report says so explicitly.
- All are **provisional operational** figures, not final metered energy accounts.
- NLDC compiles its state table from RLDC data, so the two **are not statistically independent**.
  Agreement confirms correct extraction and publication, not ground truth.
- WRLDC and SRLDC listings don't expose publication times. Version ordering falls back to arrival
  order for them.

### Field mapping

| Target (gold) | Grid-India XLS, sheet `MOP_E`, §C | NRLDC PDF §2(A) | WRLDC PDF §2(A) | SRLDC PDF §2(A) |
|---|---|---|---|---|
| `operating_date` | *Date of Reporting* − 1 day (sheet says "Report for previous day") | "Power Supply Position … **For** dd-Mon-yyyy" | same | same |
| `energy_supplied_mu` | Energy Met (MU) | Consumption (Net MU) | Consumption (Net MU) | Demand Met (Net MU) |
| `energy_shortfall_mu` | Energy Shortage (MU) | Shortage | Shortage | Shortage # |
| `energy_required_mu` | *derived*: met + shortage | *derived*; reported Requirement is **checked** | *derived*; reported Requirement (rounded to 0.1) **checked** | *derived* |
| state label | `UP`, `Maharashtra`, `Karnataka` | `UTTARPRADESH` | `MAHARASHTRA` | `KARNATAKA` / `Karnataka` (format changed on 3 June) |

Requirement is derived the same way for every source, so values stay comparable whatever source
was picked. Labels are matched through aliases in `config/pipeline.toml`.

---

## 2. Layers and data model

```
data/landing/<source>/            raw downloads + _manifest.csv (url, published_at, fetched_at)
        │  pgi run
        ▼
BRONZE  warehouse/bronze/<source>/<sha256>.<ext>   immutable, content-addressed copy
        bronze_file                                one row per distinct file: hash, provenance,
                                                   parse status/error, operating date
        ▼
SILVER  silver_state_daily                         one row per (file, state): met, shortage,
                                                   reported requirement, raw label, location in file
        silver_state_daily_current (view)          latest version per (source, state, day)
        ▼
GOLD    gold_state_daily_energy                    one row per (state, day) in scope: required,
                                                   supplied, shortfall, %, chosen source + file,
                                                   corroborating value + diff, quality status/notes
        gold_state_daily_history                   every insert/update/delete of a gold row
META    pipeline_run, dq_result, dq_latest (view)
```

- **Grain:** state × IST operating day. **Unit:** MU (GWh). **Keys:** `(state_code, operating_date)`
  in gold; `(file_id, state_code)` in silver; `file_id = sha256(content)` in bronze.
- **Lineage:** every gold row names the exact source file it came from. Silver keeps the location
  inside that file (sheet row / PDF section line).
- **Gaps are explicit:** every in-scope state-day has a gold row. With no usable source it is
  `MISSING` with NULL values, never silently absent.

### Source priority (gold)

1. Candidates for a state-day are the current versions from `[priority] order = ["grid_india_psp", "rldc"]`
   (`rldc` resolves to the state's regional centre).
2. A candidate with an ERROR (e.g. negative values) is skipped.
3. The first usable candidate is primary. The next usable one corroborates.
4. Status: `OK` = primary source, corroborated, within tolerance. `WARN` = single source, fallback
   used, sources disagree, or a row-level check failed. `MISSING` = nothing usable. `quality_notes`
   says why.

NLDC is primary because it's one uniform, machine-readable national report: one parser, and the
same definitions for every state. Making an RLDC primary instead is a one-line config change.

---

## 3. Data quality

| Check | Level | Severity | Action |
|---|---|---|---|
| File unreadable / anchor missing (sheet, section, header keywords) | file | ERROR | quarantine file, run continues, gold falls back |
| Row has unexpected number of columns | file | ERROR | quarantine (stops shifted columns from being read silently) |
| Configured state not found in file | file | WARN | logged |
| Operating date outside window | file | INFO | kept in silver, excluded from gold |
| Reporting date not 0–2 days after operating date | file | WARN | logged |
| Negative met/shortage | row | ERROR | row not used |
| Reported requirement ≠ met + shortage (± 0.15 MU) | row | WARN | flagged in gold notes |
| Primary vs corroborating supplied differs > max(0.5 MU, 0.5 %) or shortfall > 0.5 MU | cross-source | WARN | flagged in gold notes |
| Day-over-day change in supplied > 25 % | row | WARN | flagged |
| No usable source for a state-day | coverage | ERROR | gold row `MISSING` |

Thresholds are in `config/pipeline.toml`. Results are stored per run in `dq_result`
(`dq_latest` = last successful run) and summarised in the analysis report.

Real issues found in the samples:
- **SRLDC changed its PDF layout on 3 June:** different header block, title-case state names, no
  thousands separators, "Total" instead of "Region". The parser finds data by label, so both layouts
  parse, and a test covers each.
- **WRLDC rounds Requirement to 0.1 MU** (e.g. 665.4 vs 664.5 + 0.93 = 665.43). Hence the rounding
  tolerance.
- **Karnataka NLDC vs SRLDC differ by up to 0.03 MU.** That's within tolerance and shown in the
  agreement table.
- **NRLDC's server requires legacy TLS renegotiation**, which Python's `ssl` rejects by default.
  See automation.

---

## 4. Reruns, failures, late files, corrections

| Situation | Behaviour |
|---|---|
| **Rerun** | Files are identified by content hash; known files are skipped. Gold is recomputed from silver and **diffed** against the previous gold, and only real changes go to history. A rerun changes 0 rows and creates no duplicates, including when the same file arrives under a new name. |
| **Failure** | Bronze registration commits first (raw data is never lost). Parsing is per file: a bad file is quarantined with the reason. Silver + DQ + gold are written in **one transaction**: any exception rolls back to the previous gold and marks the run `failed`. The next run picks up where it stopped. |
| **Late file** | Just another new file. Gold is recomputed for all in-scope days, so the affected state-day updates (e.g. WARN `single_source` → OK) and the change is audited. |
| **Correction / revision** | A second file for the same (source, day) is a new version. The **latest publication time** wins, with arrival order as tiebreak or when the time is unknown. An *older* version arriving late therefore doesn't override a newer one. All versions stay in silver; gold notes `revised(vN)`; history records old → new. |
| **Scope change** | Changing window or states in config and rerunning removes out-of-scope gold rows, recorded as `delete` in history. |

`pgi demo` shows all of these in a temporary workspace ([output](reports/demo_output.md)):
initial load with a held-back SRLDC file, a no-op rerun, the late file arriving, a revised NLDC
report, and a truncated re-download being quarantined.

> **The correction in the demo is synthetic.** Grid-India published exactly one version per day
> for June 2026 (checked through the listing API), so `scripts/make_synthetic_correction.py`
> derives `data/demo/correction/.../05.06.26_NLDC_PSP_REVISED_SYNTHETIC.xlsx` from the real
> 5 June report. In it, UP's Energy Met is 592.63 → 590.13 and Shortage 0 → 2.50, as if load
> shedding were reported late. Its manifest row says SYNTHETIC.

---

## 5. Automating acquisition

Samples were fetched with scripted HTTP calls, not by hand in a browser. These are the access routes:

| Source | Listing | Download |
|---|---|---|
| Grid-India | `POST https://webapi.grid-india.in/api/v1/file` body `{"_source":"GRDW","_type":"DAILY_PSP_REPORT","_fileDate":"2026-27","_month":"06"}`. Returns JSON with `FilePath`, `CreatedOn`, `MimeType` | `https://webcdn.grid-india.in/<FilePath>` |
| NRLDC | `GET https://nrldc.in/get-documents-list/111?start=0&length=50&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` (header `X-Requested-With: XMLHttpRequest`). JSON with `file_name`, `created_at` | `https://nrldc.in/download-file?any=Reports%2FDaily%2FDaily%20PSP%20Report%2F<file_name>` (**legacy TLS**: use curl or an SSL context with `OP_LEGACY_SERVER_CONNECT`) |
| WRLDC | HTML directory: `https://reports.wrldc.in/Default.aspx?path=PSP%2f2026%2fJune` | `https://reports.wrldc.in/Download.ashx?file=PSP%2f2026%2fJune%2fWRLDC_PSP_Report_DD-MM-YYYY.pdf` |
| SRLDC | HTML page `https://srldc.in/Daily-Reports` | predictable: `https://srldc.in/var/ftp/reports/psp/YYYY/MonYY/DD-MM-YYYY-psp.pdf` |

Production design (Airflow, or any scheduler):
- One `fetch_<source>` task per source writes into `data/landing/<source>/` and appends to
  `_manifest.csv` (url, published time, fetch time). Retries use exponential backoff, and every
  request has a timeout.
- Daily at ~12:00 IST (reports appear 07:30–11:00 IST), then `pgi run`.
- **Re-poll the last N days** (e.g. 10) on every run and download any listing entry whose
  name/size/time changed. That's how late files and revisions get captured. Dedup by content hash
  makes re-downloading harmless.
- Alert when a state-day is still `MISSING` after an SLA (e.g. 14:00 IST), when a file is
  quarantined, or when sources disagree.

---

## 6. Assumptions and trade-offs

- **Requirement = supplied + shortfall** for every source, for comparability. The RLDC-reported
  requirement is used as a check, not as the value.
- **NLDC primary, RLDC corroborate and fall back.** This favours uniformity; corroboration catches
  extraction errors on either side.
- **Gold is fully recomputed then diffed.** At 21 rows that's simpler and safer than incremental
  merges. At scale it would recompute only the (state, day) keys touched by new silver rows and
  `MERGE` them.
- **Deterministic PDF text parsing** (pdfplumber + label anchors + column-count guards) rather
  than LLM extraction: cheap, reproducible and testable. Drift fails loudly instead of guessing. An
  LLM extractor with a structured-output schema would be a reasonable fallback for quarantined
  files, checked against the corroborating source.
- **DuckDB single file:** zero-ops locally. The same SQL ports to a lakehouse (Parquet/Delta)
  with the same layers.
- Timestamps are stored in IST (`Asia/Kolkata`). Operating days are Indian grid days.

## 7. Not done / known gaps

- No real revised daily report exists in the window, so the correction is synthetic (see above).
- Fetchers are documented, not implemented as code. The pipeline runs from committed samples.
- WRLDC/SRLDC publication times are unknown (`published_at` empty), so arrival order decides their
  versions.
- No reconciliation against CEA monthly Power Supply Position.
- Optional Q&A agent: deferred until after the core. `gold_state_daily_energy` + `dq_latest` are
  the intended tool surface.
- DQ thresholds are judgement calls, not tuned on history.

## Project layout

```
config/pipeline.toml          scope, source priority, DQ thresholds
data/landing/                 committed raw samples + download manifests (28 files)
data/demo/correction/         SYNTHETIC revised report used by the demo
scripts/                      make_synthetic_correction.py
src/pgi/
  parsers/grid_india.py       NLDC XLS parser
  parsers/rldc.py             NRLDC/WRLDC/SRLDC PDF parser (per-region column layouts)
  bronze.py silver.py gold.py pipeline.py warehouse.py
  report.py demo.py cli.py
tests/                        parser tests on real samples; end-to-end behaviour tests
reports/                      generated analysis and demo transcript
```
