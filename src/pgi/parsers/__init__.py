"""Source parsers. Each turns one raw file into a ParsedReport for the configured states.

Parsers locate data by labels (section titles, column headers, state names), never by
fixed cell positions, and raise ParseError when an anchor is missing so that format
drift is quarantined instead of silently producing wrong numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PARSER_VERSION = "1.0.0"


class ParseError(Exception):
    """Raised when a file cannot be parsed reliably (missing anchor, wrong shape)."""


@dataclass
class ParsedRow:
    state_code: str
    raw_label: str
    energy_met_mu: float
    energy_shortage_mu: float
    energy_requirement_mu: float | None  # only when the source reports it explicitly
    location: str                        # where in the file the row came from


@dataclass
class ParsedReport:
    operating_date: date
    reporting_date: date | None
    rows: list[ParsedRow]
    missing_states: list[str] = field(default_factory=list)


def parse_file(source: str, path: Path, aliases: dict[str, list[str]]) -> ParsedReport:
    """Dispatch to the parser for `source`. `aliases` maps state_code -> labels used by that source."""
    if source == "grid_india_psp":
        from .grid_india import parse
    elif source in ("nrldc_psp", "wrldc_psp", "srldc_psp"):
        from .rldc import parse_rldc

        def parse(p, a):
            return parse_rldc(source, p, a)
    else:
        raise ParseError(f"no parser for source {source!r}")
    return parse(path, aliases)


def norm_label(s: str) -> str:
    """Normalise a state label for matching: uppercase, no whitespace or punctuation."""
    return "".join(ch for ch in str(s).upper() if ch.isalnum() or ch in "&()")


def to_float(s) -> float:
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", "")
    if s in ("", "-", "--"):
        return 0.0
    return float(s)
