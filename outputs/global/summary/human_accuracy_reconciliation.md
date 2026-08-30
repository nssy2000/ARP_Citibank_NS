# Human arm accuracy — reconciliation of three figures

Date: 2026-08-12

## The three figures

| Label | Value | Source |
|---|---|---|
| ~51% | from the group workbook | Workbook's own `Prediction Correct?` column |
| 57.0% | this repo, `human_vs_llm_corrected.md` | Paired subset, corrected returns, FLAT excluded |
| 58.3% | this repo, same document | Like-for-like (both arms traded + graded) |

These are **not** three attempts at the same thing. They differ on four
dimensions, and the differences are the explanation.

## What differs

| Dimension | ~51% (workbook) | 57.0% (Figure B) | 58.3% (Figure C) |
|---|---|---|---|
| **Event set** | All rater rows, section=All (~161 events, multi-rater) | Paired subset: section=All, first_rater=YES, in_llm_universe=YES, not excluded. N=171 events, 131 traded | Same as B, further restricted to events where BOTH arms traded + |ret|>2%. N=48 |
| **Pricing basis** | Workbook's own price pair (original or Section C re-priced) | Corrected `returns_matrix.csv` (release_date anchor from EDGAR 8-K) | Same as B |
| **FLAT handling** | FLAT counted as wrong (`Prediction Correct?` is binary) | FLAT excluded from denominator (79 graded out of 131 traded) | FLAT excluded (48 graded) |
| **Exclusions** | None (25 worksheet events included) | 35 excluded (25 worksheet + 1 SPOT + 9 timing) | Same as B |
| **Denominator** | All traded rows | 79 (traded + |ret|>2%) | 48 (both arms traded + |ret|>2%) |

## Why they differ numerically

**FLAT handling is the largest driver.** On the corrected returns matrix:
- FLAT excluded: 45/79 = 57.0% (Figure B)
- FLAT counted as wrong: 45/131 = 34.4%

The human arm trades on 131 of 171 events (HOLD rate only 23.4%) but 52 of
those trades land inside the ±2% overnight band. Excluding vs including those
52 events in the denominator swings the figure by ~23pp.

**Pricing basis is the second driver.** The workbook uses its own price pairs
(original or Section C re-priced), which differ from the corrected
returns_matrix on every pre_market event (82 events with shifted entry) and
on 159 price-based re-priced events. We cannot reproduce the workbook's
figure from the corrected matrix because the returns are different.

**The ~51% cannot be reconstructed from this repo.** The workbook's
`Prediction Correct?` formula, its price pairs, and its full row set are not
committed. Treat ~51% as the workbook's own figure on its own basis, stated
for context rather than reconciled.

## Which is authoritative

**57.0% (Figure B) is the authoritative human arm accuracy**, because:
1. It uses the corrected release_date anchor (EDGAR-verified)
2. It excludes the 35 contaminated/unresolvable events
3. It uses the same accuracy definition as the LLM arm (correct-direction
   among traded events where |ret| > ±2%, FLAT excluded)
4. It applies first_rater_for_event to avoid double-counting

**58.3% (Figure C) is the authoritative like-for-like comparison**, because
it restricts to the 48 events where both arms traded and breached the band,
so neither arm gets credit for avoiding a hard event by calling HOLD.

**~51% is the workbook's own figure.** It is not wrong on its own terms, but
it uses different prices, different FLAT handling, and different exclusions.
A group member asking "why not 51%?" should be told: the workbook counts
flat trades as wrong and uses its own price pairs; this analysis excludes
flat trades from the denominator (same as the LLM arm) and uses
EDGAR-verified entry dates.
