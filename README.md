# Citibank APR Example

Small example project for running a DeepSeek-powered financial document analysis flow.

**This README covers the original single-issuer example only.** For the active phase2 pipeline (40 issuers, 4-layer blend, backtest, group sheet workflow), see [CLAUDE.md](CLAUDE.md) - that's the canonical source of truth for current architecture, run commands, and known gaps.

### A note on the earnings call transcripts

The model arm scored a document bundle for each event, comprising the issuer's press
release, its investor presentation and the earnings call transcript. The press releases
and presentations are in this repository. The transcripts are not, because most were
obtained from commercial providers whose terms do not permit redistribution.

Every excluded transcript is listed in `docs/TRANSCRIPT_SOURCES.md` with the company,
fiscal quarter and source, so the corpus can be reconstructed by anyone with access to
those providers. The full corpus is held locally and can be made available to
examiners on request.

Nothing else has been withheld. The scoring outputs, the analysis code, the price data
and the workbook are all present, so every figure in the report can be traced to its
source without the transcripts themselves.

## Structure

```text
.
|- docs/
|  |- netflix/
|  `- overview_document.pdf
|- manifests/
|  `- netflix_reports.json
|- outputs/
|- prompts/
|  `- llm_analysis_prompt_template.md
|- .env
|- .gitignore
|- example_runthrough.py
|- report_pipeline.py
|- README.md
|- run_reports.py
`- requirements.txt
```

## Local setup

```powershell
python -m pip install -r requirements.txt
```

*(The project root is `C:\Users\bencr\Documents\Citibank APR` - a OneDrive-alias path used earlier in the project is dead/inaccessible, see CLAUDE.md's Environment note.)*

## Run

```powershell
python example_runthrough.py
```

## Batch Run

Dry-run the Netflix batch without spending API tokens:

```powershell
python run_reports.py --issuer netflix --dry-run
```

Run the 4 Netflix reports for real:

```powershell
python run_reports.py --issuer netflix
```

For the active phase2 issuer set instead of this retired single-issuer example, see CLAUDE.md's "Running the pipeline" section.

## Backtest (P&L evaluation)

Evaluates any predictor's calls as an overnight-gap trading strategy (BUY -> long into
the report-date close, exit next open; SELL -> short; HOLD -> no trade), net of
transaction costs. This is the money-based scorecard that complements raw 3-class
accuracy - see CLAUDE.md "Round 8" for why accuracy alone understates a trading signal.

```powershell
python backtest.py                       # LLM signal, overnight-gap trades, net of 10 bps round-trip
python backtest.py --sensitivity         # + total return across several cost levels
python backtest.py --sheet export.csv     # add every HUMAN rater from a group-sheet CSV/TSV export
python backtest.py --cost-bps 20 --short-borrow-bps 5   # custom cost assumptions
```

`--sheet` takes any CSV/TSV in the group-sheet schema (columns `Ticker, Year, Quarter,
Rater, Type (Human/LM), Decision (BUY/HOLD/SELL), Prior Close ($), Next Day Open ($)`),
so each human rater is scored on the identical strategy and joins the comparison. Writes
the per-trade equity curve to `outputs/global/summary/backtest_equity.csv`.

## Notes

- `.env` should contain `DEEPSEEK_API_KEY=...`
- `example_runthrough.py` loads the system prompt and user template from `prompts/llm_analysis_prompt_template.md`
- `run_reports.py` reads the Netflix input set from `manifests/netflix_reports.json`
- PDF text extraction is local and uses `pypdf` with `pdfplumber` fallback
- The batch runner writes extracted text, latest results, logs, and summary files into `outputs/<issuer>/`
- Each batch run is also archived under `outputs/<issuer>/runs/<run_id>/` so later runs do not overwrite prior summaries and result files
- The bundled example transcript inside `example_runthrough.py` is fictional
