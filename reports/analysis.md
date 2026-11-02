# Example analysis: daily energy required, supplied and shortfall

Built from gold after run 2 (2026-11-02 15:18). Window 2026-06-02 to 2026-06-08. Units: MU (million kWh). Dates are IST operating days.

**Coverage:** OK: 21 state-days.

## 1. Weekly summary by state

| State | Region | Required | Supplied | Shortfall | Shortfall % | Avg daily supplied | Days with shortfall | Days OK |
|---|---|---|---|---|---|---|---|---|
| Maharashtra | WR | 4,600.77 | 4,599.70 | 1.07 | 0.02 | 657.10 | 2 | 7/7 |
| Uttar Pradesh | NR | 4,279.42 | 4,279.42 | 0.00 | 0.00 | 611.35 | 0 | 7/7 |
| Karnataka | SR | 1,846.53 | 1,846.53 | 0.00 | 0.00 | 263.79 | 0 | 7/7 |

## 2. Daily values

| Date | State | Required | Supplied | Shortfall | Shortfall % | Primary | Corroborated by | Diff (MU) | Quality | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-02 | KA | 279.67 | 279.67 | 0.00 | 0.00 | grid_india_psp | srldc_psp | 0.00 | OK | – |
| 2026-06-03 | KA | 274.47 | 274.47 | 0.00 | 0.00 | grid_india_psp | srldc_psp | 0.03 | OK | – |
| 2026-06-04 | KA | 269.18 | 269.18 | 0.00 | 0.00 | grid_india_psp | srldc_psp | 0.03 | OK | – |
| 2026-06-05 | KA | 274.72 | 274.72 | 0.00 | 0.00 | grid_india_psp | srldc_psp | -0.01 | OK | – |
| 2026-06-06 | KA | 265.05 | 265.05 | 0.00 | 0.00 | grid_india_psp | srldc_psp | -0.01 | OK | – |
| 2026-06-07 | KA | 233.26 | 233.26 | 0.00 | 0.00 | grid_india_psp | srldc_psp | -0.01 | OK | – |
| 2026-06-08 | KA | 250.18 | 250.18 | 0.00 | 0.00 | grid_india_psp | srldc_psp | 0.00 | OK | – |
| 2026-06-02 | MH | 646.94 | 646.80 | 0.14 | 0.02 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-03 | MH | 665.43 | 664.50 | 0.93 | 0.14 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-04 | MH | 669.60 | 669.60 | 0.00 | 0.00 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-05 | MH | 669.10 | 669.10 | 0.00 | 0.00 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-06 | MH | 654.80 | 654.80 | 0.00 | 0.00 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-07 | MH | 636.70 | 636.70 | 0.00 | 0.00 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-08 | MH | 658.20 | 658.20 | 0.00 | 0.00 | grid_india_psp | wrldc_psp | 0.00 | OK | – |
| 2026-06-02 | UP | 560.98 | 560.98 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |
| 2026-06-03 | UP | 607.60 | 607.60 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |
| 2026-06-04 | UP | 611.81 | 611.81 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |
| 2026-06-05 | UP | 592.63 | 592.63 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |
| 2026-06-06 | UP | 625.45 | 625.45 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |
| 2026-06-07 | UP | 630.48 | 630.48 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |
| 2026-06-08 | UP | 650.47 | 650.47 | 0.00 | 0.00 | grid_india_psp | nrldc_psp | 0.00 | OK | – |

## 3. Observations

- Largest shortfall: **Maharashtra on 2026-06-03**, 0.93 MU (0.140% of requirement).
- Karnataka: daily supplied ranged 233.3–279.7 MU (19.9% swing); lowest on 2026-06-07 (Sunday).
- Uttar Pradesh: daily supplied ranged 561.0–650.5 MU (16.0% swing); lowest on 2026-06-02 (Tuesday).
- Maharashtra: daily supplied ranged 636.7–669.6 MU (5.2% swing); lowest on 2026-06-07 (Sunday).

**Cross-source agreement (primary vs corroborating, energy supplied):**

| State | Corroborating source | Days compared | Max abs diff (MU) | Mean abs diff (MU) |
|---|---|---|---|---|
| KA | srldc_psp | 7 | 0.03 | 0.01 |
| MH | wrldc_psp | 7 | 0.00 | 0.00 |
| UP | nrldc_psp | 7 | 0.00 | 0.00 |

## 4. Data-quality findings (latest run)

No WARN or ERROR findings.

## Limitations

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
