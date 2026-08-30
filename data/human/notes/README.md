# Human arm reading notes

Rater-written notes and worksheets from the human arm of the Applied Research Project.
93 files, 84 PDF and 9 DOCX. These are the raters' own records of what they read and
why they called each event the way they did.

**These files are source records. Do not reformat, rename or edit them.** Filenames
carry information the analysis depends on, and any parsing writes to a separate
directory rather than modifying anything here. The one exception is a rater correcting
an error in their own file, which should be logged below.

---

## Two formats, handled differently

**Formal worksheets** (73 files). A consistent template stating the conventions sealed
before reading, the HOLD band, the timing rule, the price source, what research was
permitted, and pre-registered metrics. Then report metadata, forward guide, hedges and
concerns, pre-release context, candidate evidence quotes, a structured summary, and
final evidence quotes. Authors are named on page 1.

**Freeform notes** (19 files, all DOCX plus Meriem's and Abdul's PDFs). Terse
per-quarter entries in the form `Q4 24 - sell -0.5 sentiment (why: ...)` followed by the
date. Reasoning is compressed into a single bracketed clause per event.

**Two-pass tabular log** (1 file, `Dragos - Phase 3 reading notes.pdf`). A third format,
distinct from both of the above and the most experimentally structured item in the folder.
Six companies (Adobe, Caterpillar, Freeport-McMoRan, Home Depot, Union Pacific,
UnitedHealth), 23 events, 40 timed passes, in a table of Date, Quarter, Pass, Read, Score,
Min, Reason. Scores were sealed before any price was seen and the file records no peeked
flags.

Two things make it different in kind. Its scores are defined as **surprise rather than
quality**, better or worse than what management had already led the market to expect, so
they are not on the same scale as the sentiment scores elsewhere in the human arm and must
not be pooled with them without a stated mapping. And 17 of the 23 events are two-pass, an
assigned section read first and then the whole document, timed separately, which makes it
the only within-event measure of what the rest of a document adds once a section has been
read. The remaining 6 are full-document only.

---

## The SEALED marker, and why it matters

Formal worksheets contain a `— SEALED —` line. Everything above it was written before
the outcome was known. Everything below it is the realised overnight move, the HOLD band
test, the sign test, the call verification and the horizon returns.

**Any coding or content analysis of these notes must read only the portion above
`— SEALED —`.** Reading past it means coding the rater's reasoning with the answer
visible, which invalidates the exercise.

This is also the origin of the look-ahead contamination found on 2026-08-12. Twenty-five
of these worksheets were present inside the text passed to the model, which meant the
model was reading a human's sentiment score, directional call and the realised price
move as part of its input. Those 25 events are excluded from the model arm's graded
results. See `outputs/global/summary/worksheet_exclusion_decision.md`.

---

## Raters

| Rater | Files | Format |
|---|---|---|
| David Eji | 71 | Formal worksheets, numbered 01 to 71 |
| Dragos Macsim | 6 | 5 formal worksheets (NVIDIA, Netflix) plus 1 two-pass Phase 3 log |
| Meriem | 5 | Freeform |
| Abdul | 2 | Freeform, full transcript and backtesting sets |
| Nigel | 9 | Freeform, Phase 3 plus eight company-titled summaries |

Attribution note. Most filenames do not name the author, but the formal worksheets name
the rater on page 1, so attribution should be taken from file content rather than from
the filename. All of files 01 to 71 are David Eji's, including the 50 whose filenames
carry no name. The eight company-titled DOCX files (Bank of America, Boeing, Citigroup,
LM, LVMH, Maersk, Novo, UAL) carry no internal attribution and are Nigel's, confirmed
2026-08-12. Together with `Nigel's Notes Phase 3.docx` that is nine files.

---

## Information sets

The human arm read some events in full and others under a restricted information set.
The set is encoded in the filename and stated on page 1 of the formal worksheets.

| Token in filename | Meaning | Files |
|---|---|---|
| `financials` | Financial results only | 15 |
| `guidance` | Outlook and guidance only | 15 |
| `qanda` | Transcript Q&A only | 15 |
| `full` | Full document set | 5 |
| `manual baseline` | Full read, Dragos's baseline set | 5 |
| no token | Full read | remainder |

`sim` appears on 18 files (numbers 22 to 39) and is not yet explained. Confirm with the
group what it denotes before treating those files as comparable to the rest.

Two worksheet series titles appear, `Blind Sentiment Worksheet (Info-Source Experiment)`
on files 22 to 51 and `Human Arm Reading Sheet, offset A` on files 52 to 71. The latter
also records `rater offset A`. Both need confirming as the same experiment or recorded
as distinct.

These information sets correspond to the 94 section-level rows in
`Human_Data_Entry` and are a separate experiment from the 326 full-document reads. They
must not be pooled into a single human accuracy figure.

---

## The Reason field in Dragos's log is templated

The Reason text follows a fixed frame rather than free prose, for example `Full document
adds the hard numbers behind the section - [quote]; [quote]; [quote]. Against that:
[quote]. N forward claims flagged hypothetical and discounted, but the concrete numbers
carry it.` The same framing sentences recur across all six companies.

That matters for the planned reasoning analysis. Coding this text for reasoning types would
largely recover the template rather than the rater's thinking, so it is not comparable to
the freeform notes for that purpose. What it does carry usefully is the slotted quotes, the
counts of forward-looking claims discounted, and the scores and timings.

The templating is also what makes the cross-company quote duplication noted below
plausible, so establish how the field was generated before relying on any of its content.

## The two-pass design in Dragos's Phase 3 log

This is the human-arm analogue of the model arm's section ablation (Item C) and the only
place in the corpus where the marginal value of additional reading is measured within the
same event by the same rater.

Across the 17 two-pass events, the second pass added a mean 3.5 minutes of reading, from
13.5 to 17.0, and revised the score by a mean absolute 0.112 on a −1 to +1 scale, mean
signed +0.065. Six of the 17 produced no revision at all and the largest single revision
was 0.4.

Revision size varies by which section was read first. Reading the financials first left
almost nothing for the full document to add, mean absolute revision 0.017 across 6 events.
Guidance-first and Q&A-first left more, 0.183 across 6 and 0.140 across 5.

Two cautions before any of that is reported. These are score revisions rather than
directional accuracy, since the file records no correctness, so nothing here speaks to
whether the second pass produced better calls. And 17 events across three section types is
far too thin to test differences between them, so the by-section figures are descriptive
only.

## Grading conventions are not uniform across raters

The HOLD band stated in the worksheets differs by rater. David's worksheets state
2.00 per cent. Dragos's state 1.00 per cent. Other raters' bands are unrecorded or
implicit.

This does not affect the corrected analysis, because all events are regraded from
`outputs/global/summary/returns_matrix.csv` at a single pre-registered band of
2.00 per cent on the overnight move. But any figure taken from a worksheet's own
`Call verification` block reflects that rater's band rather than the project's, so
worksheet-internal correctness flags should not be pooled or reported.

---

## What the raters got right that the code did not

The formal worksheets state the timing rule per event and apply it correctly. David's
Caterpillar worksheet records that the company releases before the market open and
defines the move as release-day open over prior-day close. His Amazon worksheet records
an after-close release and uses release-day close to next-day open.

The pipeline applied one uniform window to every event until 2026-08-12. So the
convention was correctly pre-registered in the planning document and correctly executed
by hand in the human arm, and the error was a code omission rather than a methodological
oversight. Worth stating plainly in the write-up.

---

## Known errors in individual files

- `Nigel's Notes Phase 3.docx` — **outstanding.** `Booking Holdings` is a Heading 1
  under the `Workday` Title, so the four Booking Holdings events are attributed to
  Workday. Workday reads as nine events instead of four. Any parser grouping by Title
  style will mis-attribute them. Fix by promoting `Booking Holdings` to Title style.
- `Dragos - Phase 3 reading notes.pdf` — **outstanding, and the more serious of the two.**
  Two evidence quotes appear verbatim under different companies. `pattern is a hallmark of
  our 16.5% annual return track record` and `shows management has actually surgically cut
  $100 million in waste to focus` both appear in the Adobe Q3 rows and again in the
  Caterpillar Q3 row. A quote cannot belong to two issuers, so at least one attribution is
  wrong. This is the same class of fault as the Parker-Hannifin text found in Spotify's
  transcript slot on 2026-08-12, and it suggests the Reason field was assembled from a
  quote pool rather than from each document individually. Until it is resolved, the quoted
  evidence in this file cannot be used for any evidence-alignment work, though the scores
  and timings are unaffected. Ask Dragos how the Reason field was produced.
- `Nigel's Notes Phase 3.docx` — **resolved 2026-08-12.** Two malformed dates, Dell Q4
  `26/25/25` and Standard Chartered Q1 2025 `2/5/26`, removed when all dates were
  stripped from the file. See the note on date removal below.

## Date removal in Nigel's Phase 3 notes

Dates, scores, decisions and reading times were removed from the event headings of
`Nigel's Notes Phase 3.docx` on 2026-08-12. Headings now read `Q1 – Financial Results`
and carry the quarter and information set only. Three consequences.

The notes join to events on company and quarter alone. That is the same key the workbook
uses, `Company|Year|Quarter`, so the join still works, but there is no longer an
independent date in the file to verify the match against.

Several headings carry no year, for example `Q1 – Financial Results` under Hermes,
Workday, Dell and Allianz. The year has to be inferred from the workbook rather than read
from the note.

Scores, decisions and times must be taken from `Human_Data_Entry` rather than from the
notes. The notes now hold reasoning only.

One provenance cost worth recording. Removing the dates removes the only in-file evidence
of when each note was written, so whether a note predates the outcome can no longer be
established from the document itself. Nigel can state it directly, and that statement
should be written into this file rather than left implicit.

---

## Open questions for the group

1. What does `sim` denote on files 22 to 39?
2. Are `Info-Source Experiment` and `Human Arm Reading Sheet, offset A` the same
   experiment, and what does `rater offset A` mean?
3. Were the freeform notes written before or after the outcome was known? The formal
   worksheets are explicit about this and the freeform ones are not. Nigel can state this
   directly for his own nine files, leaving only Meriem's and Abdul's outstanding.
4. How was the Reason field in `Dragos - Phase 3 reading notes.pdf` produced, and why do
   two evidence quotes appear under two different companies?
5. Dragos's Phase 3 scores are defined as surprise against expectation while the rest of
   the human arm scores sentiment. Are those the same quantity, and if not, is there a
   stated mapping?
6. Did the raters know at the time of writing that these notes might be analysed? Notes
   written as a private aide-memoire and notes written for analysis are different kinds
   of evidence and a reader will ask.

---

Last updated 2026-08-12.
