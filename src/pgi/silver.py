"""Silver: parse pending bronze files into standardised state-day rows.

A file that fails to parse is quarantined (parse_status = 'failed', reason recorded) and the
run continues; gold then falls back to the next source for the affected days.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .parsers import PARSER_VERSION, ParseError, parse_file


@dataclass
class ParseResult:
    parsed: int = 0
    failed: int = 0
    dq: list[dict] = field(default_factory=list)


def parse_pending(con, cfg: Config, run_id: int, warehouse_dir: Path) -> ParseResult:
    res = ParseResult()
    todo = con.execute(
        """SELECT file_id, source_id, bronze_path, original_name FROM bronze_file
           WHERE parse_status = 'pending' OR parser_version IS DISTINCT FROM ?
           ORDER BY ingested_at, file_id""",
        [PARSER_VERSION],
    ).fetchall()
    for file_id, source, bronze_path, name in todo:
        aliases = {s.code: s.aliases[source] for s in cfg.states if source in s.aliases}
        base = {"run_id": run_id, "source_id": source, "file_id": file_id}
        try:
            rep = parse_file(source, warehouse_dir / bronze_path, aliases)
        except ParseError as e:
            con.execute(
                "UPDATE bronze_file SET parse_status='failed', parse_error=?, parser_version=? WHERE file_id=?",
                [str(e), PARSER_VERSION, file_id])
            res.failed += 1
            res.dq.append({**base, "check_id": "parse_failed", "severity": "ERROR", "scope": "file",
                           "detail": f"{name}: {e}"})
            continue

        con.execute("DELETE FROM silver_state_daily WHERE file_id = ?", [file_id])
        for r in rep.rows:
            con.execute(
                "INSERT INTO silver_state_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [file_id, source, r.state_code, rep.operating_date, r.energy_met_mu, r.energy_shortage_mu,
                 r.energy_requirement_mu, r.raw_label, r.location, PARSER_VERSION])
        con.execute(
            """UPDATE bronze_file SET parse_status='parsed', parse_error=NULL, parser_version=?,
                   operating_date=?, reporting_date=? WHERE file_id=?""",
            [PARSER_VERSION, rep.operating_date, rep.reporting_date, file_id])
        res.parsed += 1

        if rep.missing_states:
            res.dq.append({**base, "check_id": "state_missing_in_file", "severity": "WARN", "scope": "file",
                           "operating_date": rep.operating_date,
                           "detail": f"{name}: states not found {rep.missing_states}"})
        if not (cfg.start <= rep.operating_date <= cfg.end):
            res.dq.append({**base, "check_id": "out_of_window", "severity": "INFO", "scope": "file",
                           "operating_date": rep.operating_date,
                           "detail": f"{name}: operating date {rep.operating_date} outside window; kept in silver only"})
        if rep.reporting_date and (rep.reporting_date - rep.operating_date).days not in (0, 1, 2):
            res.dq.append({**base, "check_id": "reporting_lag", "severity": "WARN", "scope": "file",
                           "operating_date": rep.operating_date,
                           "detail": f"{name}: reported {rep.reporting_date} for operating day {rep.operating_date}"})
    return res
