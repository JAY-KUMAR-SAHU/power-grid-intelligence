"""Load config/pipeline.toml into typed objects."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "pipeline.toml"

SOURCES = ("grid_india_psp", "nrldc_psp", "wrldc_psp", "srldc_psp")


@dataclass(frozen=True)
class State:
    code: str
    name: str
    region: str
    aliases: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class DQConfig:
    cross_source_abs_mu: float
    cross_source_pct: float
    identity_tolerance_mu: float
    day_over_day_pct: float


@dataclass(frozen=True)
class Config:
    start: date
    end: date
    priority: list[str]
    regions: dict[str, str]
    states: list[State]
    dq: DQConfig

    @property
    def days(self) -> list[date]:
        n = (self.end - self.start).days + 1
        return [self.start + timedelta(days=i) for i in range(n)]

    def state(self, code: str) -> State:
        return next(s for s in self.states if s.code == code)

    def sources_for(self, state: State) -> list[str]:
        """Concrete source ids for a state, in priority order."""
        out = []
        for p in self.priority:
            src = self.regions.get(state.region) if p == "rldc" else p
            if src and src in state.aliases and src not in out:
                out.append(src)
        return out


def load_config(path: Path | str = DEFAULT_CONFIG) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return Config(
        start=date.fromisoformat(raw["window"]["start"]),
        end=date.fromisoformat(raw["window"]["end"]),
        priority=list(raw["priority"]["order"]),
        regions=dict(raw["regions"]),
        states=[State(s["code"], s["name"], s["region"], dict(s.get("aliases", {}))) for s in raw["states"]],
        dq=DQConfig(**raw["dq"]),
    )
