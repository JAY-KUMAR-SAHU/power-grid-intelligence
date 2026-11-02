"""Example analysis over gold, written as Markdown. Every number comes with its quality context."""
from __future__ import annotations

from pathlib import Path

LIMITATIONS = """\
- **Shortfall is self-reported.** Energy Shortage comes from load-shedding details that states
  furnish to the RLDCs (SRLDC's report says so explicitly). Unreported or unscheduled load
  shedding is not captured, so shortfall is a lower bound.
- **Requirement is derived**, as supplied + shortfall, for every source. It inherits the
  under-reporting of shortfall and is not an independent demand estimate.
- **Values are measured at the state periphery**: state control-area generation plus net drawal
  from the inter-state grid. They include losses inside the state's own network, so they are
  larger than energy actually billed to consumers.
- **Daily reports are provisional operational data.** Final, metered figures come later
  (e.g. CEA monthly Power Supply Position). No revised daily report was found for this window;
  the correction in the demo is synthetic and labelled as such.
- **Corroboration is not independence.** NLDC compiles its state table from RLDC data, so
  agreement between them confirms correct extraction and publication, not ground truth.
"""


def md_table(headers: list[str], rows: list[tuple]) -> str:
    def f(v):
        if v is None:
            return "–"
        if isinstance(v, float):
            return f"{v:,.2f}"
        return str(v)
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(f(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def build_report(con) -> str:
    parts = ["# Example analysis: daily energy required, supplied and shortfall", ""]

    run = con.execute("SELECT run_id, finished_at FROM pipeline_run WHERE status='success' ORDER BY run_id DESC LIMIT 1").fetchone()
    window = con.execute("SELECT MIN(operating_date), MAX(operating_date) FROM gold_state_daily_energy").fetchone()
    parts.append(f"Built from gold after run {run[0]} ({run[1]:%Y-%m-%d %H:%M}). "
                 f"Window {window[0]} to {window[1]}. Units: MU (million kWh). Dates are IST operating days.\n")

    status = con.execute("""SELECT quality_status, COUNT(*) FROM gold_state_daily_energy GROUP BY 1 ORDER BY 1""").fetchall()
    parts.append("**Coverage:** " + ", ".join(f"{s}: {n}" for s, n in status) + " state-days.\n")

    parts.append("## 1. Weekly summary by state\n")
    rows = con.execute("""
        SELECT state_name, region,
               SUM(energy_required_mu), SUM(energy_supplied_mu), SUM(energy_shortfall_mu),
               100 * SUM(energy_shortfall_mu) / NULLIF(SUM(energy_required_mu), 0),
               AVG(energy_supplied_mu),
               COUNT(*) FILTER (WHERE energy_shortfall_mu > 0),
               COUNT(*) FILTER (WHERE quality_status = 'OK') || '/' || COUNT(*)
        FROM gold_state_daily_energy GROUP BY 1, 2 ORDER BY 4 DESC""").fetchall()
    parts.append(md_table(["State", "Region", "Required", "Supplied", "Shortfall", "Shortfall %",
                           "Avg daily supplied", "Days with shortfall", "Days OK"], rows))
    parts.append("")

    parts.append("## 2. Daily values\n")
    rows = con.execute("""
        SELECT operating_date, state_code, energy_required_mu, energy_supplied_mu, energy_shortfall_mu,
               shortfall_pct, primary_source, corroborating_source, supplied_diff_mu, quality_status, quality_notes
        FROM gold_state_daily_energy ORDER BY state_code, operating_date""").fetchall()
    parts.append(md_table(["Date", "State", "Required", "Supplied", "Shortfall", "Shortfall %", "Primary",
                           "Corroborated by", "Diff (MU)", "Quality", "Notes"], rows))
    parts.append("")

    parts.append("## 3. Observations\n")
    peak = con.execute("""SELECT state_name, operating_date, energy_shortfall_mu, shortfall_pct
                          FROM gold_state_daily_energy WHERE energy_shortfall_mu > 0
                          ORDER BY energy_shortfall_mu DESC LIMIT 1""").fetchone()
    if peak:
        parts.append(f"- Largest shortfall: **{peak[0]} on {peak[1]}**, {peak[2]:.2f} MU ({peak[3]:.3f}% of requirement).")
    else:
        parts.append("- No state reported any energy shortfall in the window.")
    swing = con.execute("""SELECT state_name, MIN(energy_supplied_mu), MAX(energy_supplied_mu),
                                  100 * (MAX(energy_supplied_mu) - MIN(energy_supplied_mu)) / MIN(energy_supplied_mu),
                                  arg_min(operating_date, energy_supplied_mu)
                           FROM gold_state_daily_energy GROUP BY 1 ORDER BY 4 DESC""").fetchall()
    for s, lo, hi, pct, low_day in swing:
        parts.append(f"- {s}: daily supplied ranged {lo:.1f}–{hi:.1f} MU ({pct:.1f}% swing); "
                     f"lowest on {low_day} ({low_day:%A}).")
    agree = con.execute("""SELECT state_code, corroborating_source, COUNT(supplied_diff_mu),
                                  MAX(ABS(supplied_diff_mu)), AVG(ABS(supplied_diff_mu))
                           FROM gold_state_daily_energy WHERE supplied_diff_mu IS NOT NULL
                           GROUP BY 1, 2 ORDER BY 1""").fetchall()
    parts.append("\n**Cross-source agreement (primary vs corroborating, energy supplied):**\n")
    parts.append(md_table(["State", "Corroborating source", "Days compared", "Max abs diff (MU)", "Mean abs diff (MU)"], agree))
    parts.append("")

    parts.append("## 4. Data-quality findings (latest run)\n")
    dq = con.execute("""SELECT severity, check_id, COALESCE(state_code, '–'), operating_date, detail
                        FROM dq_latest WHERE severity IN ('ERROR', 'WARN')
                        ORDER BY severity, check_id, state_code, operating_date""").fetchall()
    parts.append(md_table(["Severity", "Check", "State", "Date", "Detail"], dq) if dq else "No WARN or ERROR findings.")
    parts.append("")

    hist = con.execute("""SELECT run_id, change_type, state_code, operating_date, old_supplied_mu, new_supplied_mu,
                                 old_shortfall_mu, new_shortfall_mu, old_status, new_status
                          FROM gold_state_daily_history WHERE change_type <> 'insert'
                          ORDER BY run_id, state_code, operating_date""").fetchall()
    if hist:
        parts.append("## 5. Revisions applied to gold\n")
        parts.append(md_table(["Run", "Change", "State", "Date", "Old supplied", "New supplied",
                               "Old shortfall", "New shortfall", "Old status", "New status"], hist))
        parts.append("")

    parts.append("## Limitations\n")
    parts.append(LIMITATIONS)
    return "\n".join(parts)


def write_report(con, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(con), encoding="utf-8")
    return path
