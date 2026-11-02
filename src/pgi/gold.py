"""Gold: one trusted row per (state, day) chosen by source priority, with quality flags.

Rules
- Candidates for a state-day are the current silver versions of its sources, in priority order.
- A candidate with an ERROR (negative values) is unusable; the next source is used instead.
- supplied = Energy Met, shortfall = Energy Shortage of the primary source,
  required = supplied + shortfall (derived the same way for every source).
- A second usable source corroborates; disagreement beyond tolerance is a WARN.
- Every in-scope state-day gets a row; with no usable source it is MISSING (values NULL).
- Gold is recomputed from silver each run and diffed against the previous gold; only
  changed rows are written to history, so a rerun with no new input changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config

COMPARE = ("energy_supplied_mu", "energy_shortfall_mu", "energy_required_mu", "primary_file",
           "corroborating_supplied_mu", "quality_status", "quality_notes", "is_revised")


@dataclass
class GoldResult:
    rows: int = 0
    changed: int = 0
    dq: list[dict] = field(default_factory=list)


def _r(x):
    return None if x is None else round(x, 3)


def build_gold(con, cfg: Config, run_id: int) -> GoldResult:
    res = GoldResult()
    cur = con.execute(
        """SELECT source_id, state_code, operating_date, file_id, original_name, energy_met_mu,
                  energy_shortage_mu, energy_requirement_reported_mu, n_versions
           FROM silver_state_daily_current""").fetchall()
    silver = {(s, st, d): dict(file_id=f, name=n, met=m, short=sh, req=rq, n_versions=nv)
              for s, st, d, f, n, m, sh, rq, nv in cur}

    new_rows = []
    for state in cfg.states:
        prev_supplied = None
        for day in cfg.days:
            notes, usable = [], []
            for src in cfg.sources_for(state):
                c = silver.get((src, state.code, day))
                if c is None:
                    continue
                base = {"run_id": run_id, "source_id": src, "file_id": c["file_id"],
                        "state_code": state.code, "operating_date": day}
                if c["met"] < 0 or c["short"] < 0:
                    res.dq.append({**base, "check_id": "negative_value", "severity": "ERROR", "scope": "row",
                                   "detail": f"met={c['met']} shortage={c['short']}; row not used"})
                    continue
                if c["req"] is not None and abs(c["req"] - (c["met"] + c["short"])) > cfg.dq.identity_tolerance_mu:
                    res.dq.append({**base, "check_id": "requirement_identity", "severity": "WARN", "scope": "row",
                                   "detail": f"reported requirement {c['req']} != met {c['met']} + shortage {c['short']}"})
                    notes.append(f"requirement_identity({src})")
                usable.append((src, c))

            row = {"state_code": state.code, "state_name": state.name, "region": state.region,
                   "operating_date": day, "n_sources": len(usable)}
            if not usable:
                res.dq.append({"run_id": run_id, "check_id": "no_usable_source", "severity": "ERROR",
                               "scope": "coverage", "state_code": state.code, "operating_date": day,
                               "detail": f"no usable data from {cfg.sources_for(state)}"})
                row.update(energy_required_mu=None, energy_supplied_mu=None, energy_shortfall_mu=None,
                           shortfall_pct=None, primary_source=None, primary_file=None,
                           corroborating_source=None, corroborating_supplied_mu=None, supplied_diff_mu=None,
                           is_revised=False, quality_status="MISSING", quality_notes="no_usable_source")
                new_rows.append(row)
                prev_supplied = None
                continue

            p_src, p = usable[0]
            if p_src != cfg.sources_for(state)[0]:
                notes.append(f"fallback_to_{p_src}")
            supplied, shortfall = p["met"], p["short"]
            required = supplied + shortfall
            row.update(energy_required_mu=_r(required), energy_supplied_mu=_r(supplied),
                       energy_shortfall_mu=_r(shortfall),
                       shortfall_pct=_r(100 * shortfall / required) if required else None,
                       primary_source=p_src, primary_file=p["name"], is_revised=p["n_versions"] > 1)
            if row["is_revised"]:
                notes.append(f"revised(v{p['n_versions']})")

            if len(usable) > 1:
                c_src, c = usable[1]
                diff = supplied - c["met"]
                tol = max(cfg.dq.cross_source_abs_mu, cfg.dq.cross_source_pct / 100 * supplied)
                row.update(corroborating_source=c_src, corroborating_supplied_mu=c["met"],
                           supplied_diff_mu=_r(diff))
                if abs(diff) > tol or abs(shortfall - c["short"]) > cfg.dq.cross_source_abs_mu:
                    notes.append(f"sources_disagree({p_src} vs {c_src}: supplied {diff:+.2f} MU, "
                                 f"shortfall {shortfall - c['short']:+.2f} MU)")
                    res.dq.append({"run_id": run_id, "check_id": "cross_source_disagree", "severity": "WARN",
                                   "scope": "cross_source", "source_id": f"{p_src}|{c_src}",
                                   "state_code": state.code, "operating_date": day,
                                   "detail": f"supplied {supplied} vs {c['met']} (tol {tol:.2f}); "
                                             f"shortfall {shortfall} vs {c['short']}"})
            else:
                row.update(corroborating_source=None, corroborating_supplied_mu=None, supplied_diff_mu=None)
                notes.append("single_source")

            if prev_supplied and abs(supplied - prev_supplied) / prev_supplied * 100 > cfg.dq.day_over_day_pct:
                notes.append("day_over_day_jump")
                res.dq.append({"run_id": run_id, "check_id": "day_over_day_jump", "severity": "WARN",
                               "scope": "row", "source_id": p_src, "state_code": state.code,
                               "operating_date": day, "detail": f"{prev_supplied} -> {supplied} MU"})
            prev_supplied = supplied

            warn = [n for n in notes if not n.startswith("revised")]
            row["quality_status"] = "WARN" if warn else "OK"
            row["quality_notes"] = "; ".join(notes) or None
            new_rows.append(row)

    old = {(r[0], r[1]): r[2:] for r in con.execute(
        f"SELECT state_code, operating_date, last_changed_run, {', '.join(COMPARE)} FROM gold_state_daily_energy"
    ).fetchall()}

    for row in new_rows:
        key = (row["state_code"], row["operating_date"])
        prev = old.get(key)
        new_cmp = tuple(row[c] for c in COMPARE)
        if prev is not None and tuple(prev[1:]) == new_cmp:
            row["last_changed_run"] = prev[0]
            continue
        row["last_changed_run"] = run_id
        res.changed += 1
        o = dict(zip(COMPARE, prev[1:])) if prev else {}
        con.execute(
            "INSERT INTO gold_state_daily_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, "update" if prev else "insert", row["state_code"], row["operating_date"],
             o.get("energy_supplied_mu"), row["energy_supplied_mu"],
             o.get("energy_shortfall_mu"), row["energy_shortfall_mu"],
             o.get("quality_status"), row["quality_status"],
             o.get("primary_file"), row["primary_file"],
             o.get("quality_notes"), row["quality_notes"]])

    # Rows that left the scope (window or state list changed) are removed, and that is audited too.
    for key in sorted(set(old) - {(r["state_code"], r["operating_date"]) for r in new_rows}):
        o = dict(zip(COMPARE, old[key][1:]))
        res.changed += 1
        con.execute(
            "INSERT INTO gold_state_daily_history VALUES (?, 'delete', ?, ?, ?, NULL, ?, NULL, ?, NULL, ?, NULL, ?, NULL)",
            [run_id, key[0], key[1], o["energy_supplied_mu"], o["energy_shortfall_mu"], o["quality_status"],
             o["primary_file"], o["quality_notes"]])

    cols = ["state_code", "state_name", "region", "operating_date", "energy_required_mu", "energy_supplied_mu",
            "energy_shortfall_mu", "shortfall_pct", "primary_source", "primary_file", "corroborating_source",
            "corroborating_supplied_mu", "supplied_diff_mu", "n_sources", "is_revised", "quality_status",
            "quality_notes", "last_changed_run"]
    con.execute("DELETE FROM gold_state_daily_energy")
    con.executemany(f"INSERT INTO gold_state_daily_energy ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [[r[c] for c in cols] for r in new_rows])
    res.rows = len(new_rows)
    return res
