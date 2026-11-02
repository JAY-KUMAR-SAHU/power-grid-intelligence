# Pipeline demo: rerun, late file, correction, failed download

Workspace: `C:\Users\HP\AppData\Local\Temp\pgi_demo_l3ql_be3` (temporary copy of `data/landing`, fresh warehouse).

## Step 1: initial load (SRLDC report for 6 June not yet available)

`06-06-2026-psp.pdf` is held back to simulate a late file. Karnataka on 6 June has only the Grid-India value, so it is flagged `single_source`.

`run 1: success | files new=27 skipped=0 failed=0 | gold rows=21 changed=21`

Integrity: gold rows=21, distinct state-days=21, duplicate silver keys=0, bronze files=27

| State | Date | Required | Supplied | Shortfall | Primary file | Corroborated by | Quality | Notes |
|---|---|---|---|---|---|---|---|---|
| KA | 2026-06-06 | 265.05 | 265.05 | 0.00 | 06.06.26_NLDC_PSP_996.xls | – | WARN | single_source |

## Step 2: rerun with no new input

Every file is recognised by its content hash and skipped. Gold is recomputed and diffed: nothing changes, no duplicates are created.

`run 2: success | files new=0 skipped=27 failed=0 | gold rows=21 changed=0`

Integrity: gold rows=21, distinct state-days=21, duplicate silver keys=0, bronze files=27

## Step 3: the late SRLDC file arrives

Only the new file is ingested. Karnataka 6 June is now corroborated and moves from WARN to OK; the change is recorded in history.

`run 3: success | files new=1 skipped=27 failed=0 | gold rows=21 changed=1`

Integrity: gold rows=21, distinct state-days=21, duplicate silver keys=0, bronze files=28

| State | Date | Required | Supplied | Shortfall | Primary file | Corroborated by | Quality | Notes |
|---|---|---|---|---|---|---|---|---|
| KA | 2026-06-06 | 265.05 | 265.05 | 0.00 | 06.06.26_NLDC_PSP_996.xls | srldc_psp | OK | – |

## Step 4: a revised Grid-India report for 5 June is published (SYNTHETIC)

The revision has a later publication time, so it supersedes the original for every state in it. Uttar Pradesh changes (supplied 592.63 -> 590.13 MU, shortfall 0 -> 2.50 MU); Maharashtra and Karnataka values are identical, so only their `revised` note changes. Because NRLDC did not revise its report, UP now disagrees with its corroborating source and is flagged for review. Both versions remain in silver.

`run 4: success | files new=1 skipped=28 failed=0 | gold rows=21 changed=3`

Integrity: gold rows=21, distinct state-days=21, duplicate silver keys=0, bronze files=29

| State | Date | Required | Supplied | Shortfall | Primary file | Corroborated by | Quality | Notes |
|---|---|---|---|---|---|---|---|---|
| UP | 2026-06-05 | 592.63 | 590.13 | 2.50 | 05.06.26_NLDC_PSP_REVISED_SYNTHETIC.xlsx | nrldc_psp | WARN | revised(v2); sources_disagree(grid_india_psp vs nrldc_psp: supplied -2.50 MU, shortfall +2.50 MU) |

| Source | File | Published | Supplied | Shortfall |
|---|---|---|---|---|
| nrldc_psp | daily050626.pdf | 2026-06-06 07:45 | 592.63 | 0.00 |
| grid_india_psp | 05.06.26_NLDC_PSP_700.xls | 2026-06-06 10:54 | 592.63 | 0.00 |
| grid_india_psp | 05.06.26_NLDC_PSP_REVISED_SYNTHETIC.xlsx | 2026-06-09 18:00 | 590.13 | 2.50 |

## Step 5: a truncated re-download lands (failure)

The file cannot be parsed, so it is quarantined with the reason and the run still succeeds. Gold keeps the last good values.

`run 5: success | files new=1 skipped=29 failed=1 | gold rows=21 changed=0`

Integrity: gold rows=21, distinct state-days=21, duplicate silver keys=0, bronze files=30

| Source | File | Status | Error |
|---|---|---|---|
| grid_india_psp | 07.06.26_NLDC_PSP_REDOWNLOAD.xls | failed | cannot read sheet MOP_E: Cannot detect file format |

## Step 6: final rerun

Steady state: nothing new, nothing changes.

`run 6: success | files new=0 skipped=30 failed=0 | gold rows=21 changed=0`

Integrity: gold rows=21, distinct state-days=21, duplicate silver keys=0, bronze files=30

## Gold change history (updates only)

| Run | Change | State | Date | Old supplied | New supplied | Old shortfall | New shortfall | Old status | New status | New notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 3 | update | KA | 2026-06-06 | 265.05 | 265.05 | 0.00 | 0.00 | WARN | OK | – |
| 4 | update | KA | 2026-06-05 | 274.72 | 274.72 | 0.00 | 0.00 | OK | OK | revised(v2) |
| 4 | update | MH | 2026-06-05 | 669.10 | 669.10 | 0.00 | 0.00 | OK | OK | revised(v2) |
| 4 | update | UP | 2026-06-05 | 592.63 | 590.13 | 0.00 | 2.50 | OK | WARN | revised(v2); sources_disagree(grid_india_psp vs nrldc_psp: supplied -2.50 MU, shortfall +2.50 MU) |
