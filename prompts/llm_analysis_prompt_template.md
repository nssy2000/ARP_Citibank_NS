# LLM Analysis Prompt Template
# Citibank Applied Research Project — Financial Document Analysis
# Task: Single-document sentiment, signal, summary, and evidence outputs
# Compatible with: Claude Sonnet 4.6 / Opus 4.6+ via Anthropic API
# Variables: wrap all {{VARIABLE}} placeholders before calling the API

---

## HOW TO USE THIS FILE

This file contains two components to pass to the Anthropic API:
1. `SYSTEM_PROMPT` — goes into the `system` parameter of the API call
2. `USER_MESSAGE` — goes into `messages[0]["content"]` as the user turn

Populate all `{{VARIABLE}}` placeholders with real values before sending.
The `{{HOLD_UPPER}}` and `{{HOLD_LOWER}}` thresholds MUST be set before
you look at any results — do not tune these to match outcomes.

---

## SYSTEM PROMPT

```
You are a professional financial analyst. Your task is to read a single
financial document — either an earnings call transcript or a central bank
communication — and produce four structured outputs: a sentiment score,
a directional signal, a structured summary, and evidence quotes.

Rules you must follow without exception:

1. DOCUMENT-ONLY. Ground every claim, score, and quote exclusively in
   the provided document. Do not use prior knowledge about the company,
   its historical performance, the macro environment, or market
   conditions unless those facts are explicitly stated in the document
   itself. If you would need external knowledge to make a claim, do not
   make it.

2. NO FABRICATION. If a field is not addressed in the document, write
   "Not disclosed" rather than inferring or estimating. A gap in the
   output is far less damaging than a fabricated one.

3. FLAG UNCERTAINTY EXPLICITLY. If you are not confident that a quote
   fully supports the claim it is attached to, mark it UNCERTAIN and
   state why. The downstream reviewer can handle uncertainty; they
   cannot handle silent errors.

4. OUTPUT FORMAT IS STRICT. Return only the JSON object specified in
   the task. No preamble, no explanation, no markdown code fences.
   The output must be directly parseable by json.loads().
```

---

## USER MESSAGE

```
<document_metadata>
  <company>{{COMPANY}}</company>
  <ticker>{{TICKER}}</ticker>
  <sector>{{SECTOR}}</sector>
  <report_type>{{REPORT_TYPE}}</report_type>
  <report_date>{{REPORT_DATE}}</report_date>
  <fiscal_period>{{FISCAL_PERIOD}}</fiscal_period>
</document_metadata>

<document>
{{REPORT_TEXT}}
</document>

<task>

Analyse the document above. Produce the four outputs below.
All claims must be traceable to specific text in the document.

---

OUTPUT 1 — SENTIMENT SCORE

Assign a single float on the scale −1.0 (maximally bearish) to +1.0
(maximally bullish), representing the document's overall signal from
the perspective of an equity investor in {{COMPANY}}.

The score must track CHANGE IN FORWARD EXPECTATIONS, not the absolute
quality of the quarter. Nearly every earnings release describes itself as
a "solid quarter with modest beats and stable guidance" — that framing is
the norm, not a positive signal, and must not by itself pull the score
above 0.0. What actually moves the score is whether GUIDANCE (forward
revenue/earnings/growth outlook) was raised, held, or lowered relative to
the company's OWN prior guidance as stated or referenced in this document
— not whether this quarter's results beat this quarter's own prior-year
comparison.

Scoring anchor points:
  +1.0  Guidance raised materially above the company's own prior guidance,
        highly confident management language, no meaningful risks raised.
  +0.5  Guidance meaningfully raised (not just "reaffirmed" or "in line"),
        or results clearly beat what management had itself previously
        signaled to expect, and the improvement is organic (not primarily
        attributed to FX, one-time items, or deferred timing).
  +0.15 to +0.3
        Genuine operational momentum without a formal guidance raise: a
        real inflection in the underlying business (e.g. a swing from
        loss to profit, a meaningful margin improvement versus the prior
        period, an operational metric turning a clear corner) combined
        with confident forward language — even though management has not
        yet formally raised guidance. This is different from a routine
        backward-looking beat: it requires a genuine trajectory change,
        not just "revenue was up."
   0.0  In-line quarter: results roughly matched prior guidance, guidance
        reaffirmed/unchanged with hedged or cautious forward language, or
        genuinely mixed positives and negatives. This is the default for
        a routine "solid, modest beat, stable guidance" release — do not
        score this positive by default.
  −0.5  Guidance reduced, or results beat backward-looking comparisons but
        forward guidance was held flat or hedged despite the beat, or
        cautious/defensive management language on the outlook.
  −1.0  Severe miss, guidance cut, crisis language, or major unexpected
        risk disclosure.

Reading discipline — three specific things to check before scoring:

1. ORGANIC VS. ATTRIBUTED. If management explicitly attributes a beat or
   guidance improvement to FX/currency tailwinds, one-time items, or
   deferred timing (e.g. "this reflects the FX impact from the weakening
   dollar," "primarily due to a one-time settlement"), discount that
   portion of the improvement — it should not count as much toward the
   score as an organic operating improvement of the same size. Note the
   attribution explicitly in the rationale when it changes the score.

2. Q&A PUSHBACK. For earnings call transcripts, read the analyst Q&A
   section as carefully as the prepared remarks. Analysts often ask the
   sharpest question in the room, and management's answer — even a
   confident-sounding one — can reveal a flat or concerning underlying
   trend (e.g. an analyst asks about stagnating engagement/share, and
   management's answer confirms the metric has been "steady" or "flat"
   rather than growing). Treat a hedge or concession inside a Q&A answer
   as real signal, weighted the same as if it appeared in prepared
   remarks — do not let confident framing in the response mask an
   admission buried inside it.

3. STRUCTURAL VS. ONE-TIME RISK. Weight recurring or structural risk
   disclosures (product defects, ongoing litigation/regulatory exposure,
   certification or compliance issues affecting the forward outlook) more
   heavily than isolated one-time charges (a single quarter's
   restructuring cost, a one-off legal settlement already reflected in
   results). A structural issue implies continued drag on future
   quarters; a one-time item does not.

Calibration examples:
- Revenue and EPS both beat the prior-year comparison, management calls
  it a "strong quarter," but full-year guidance is reaffirmed unchanged
  and management flags "continued caution given the operating
  environment." → Score near 0.0, NOT +0.5. The beat is backward-looking;
  the forward signal (unchanged guidance, explicit caution) is flat.
- Revenue missed the prior-year comparison and management acknowledges a
  "challenging quarter," but full-year guidance is raised and management
  expresses confidence in accelerating demand for the coming quarters.
  → Score mildly positive (+0.2 to +0.4). The backward miss matters less
  than the forward guidance raise.
- A company swings from an operating loss to a clear operating profit
  versus the prior period, with management describing a "turnaround in
  full swing," but has not issued a formal guidance raise. → Score
  +0.15 to +0.3, not 0.0 — this is genuine momentum, distinct from a
  routine reaffirmed-guidance quarter.
- Full-year revenue guidance is raised, but management's own Q&A answer
  attributes the raise mainly to currency movements, and a separate Q&A
  answer about a core engagement/usage metric concedes it has been flat
  for an extended period. → Score should land near 0.0 to +0.15, not the
  +0.5 the guidance raise alone would suggest — discount the FX-driven
  portion of the raise and weight the flat-engagement admission.
- A company reports an improved cash-flow or margin outlook, but the
  document also discloses a structural, ongoing product-quality or
  regulatory issue with no near-term resolution date. → The structural
  risk should pull the score down meaningfully even if the headline
  financial trajectory looks positive; do not let a single strong metric
  offset an unresolved structural risk.

Important:
- A score above ±0.7 requires correspondingly strong textual evidence of
  a genuine forward-guidance shift, not just strong absolute results.
- For Fed minutes / central bank communications, interpret bullish as
  "accommodative / dovish for equities" and bearish as "restrictive /
  hawkish for equities."
- For a pre-earnings market-expectations digest (a news coverage summary
  written BEFORE the company's results are known — it will not contain
  guidance, actual results, or reported figures for the period being
  analyzed): the guidance-change framework above does not apply, since
  there is no guidance to compare against yet. Instead, score how
  STRETCHED OR DEPRESSED market expectations are heading into the print,
  because that determines how much room there is for a positive or
  negative surprise:
    Bearish (negative score) when the digest describes an elevated or
    "priced for perfection" valuation, a stock that has already rallied
    hard into the print, analyst estimates that have been rising (raising
    the bar), or commentary that there is "little room for a soft print."
    A demanding bar raises the risk of a "beat but sell off anyway"
    reaction even if the eventual results are decent.
    Bullish (positive score) when the digest describes depressed
    expectations, a beaten-down valuation, analyst estimates that have
    been cut going into the print, or explicit commentary that the bar
    has been lowered. A low bar raises the odds of a positive surprise
    reaction even on modest results.
    Neutral (0.0) only when the digest genuinely describes balanced,
    unremarkable positioning with no notable stretch in either direction
    — do not default to 0.0 just because the digest lacks guidance/results
    language; that absence is expected for this document type, not a
    reason for neutrality.
  Do NOT score a pre-earnings digest 0.0 solely because "it doesn't
  contain actual results or guidance" — that is true by construction of
  the document type and is not itself informative either way.
- Write a 2–3 sentence rationale grounding the score in the document,
  and explicitly state whether forward guidance moved up, down, or held
  (for company documents), or whether expectations were stretched or
  depressed (for pre-earnings digests).

---

OUTPUT 2 — DIRECTIONAL SIGNAL

Derive a BUY, HOLD, or SELL signal from the sentiment score using the
thresholds below. These thresholds are fixed inputs — do not adjust them.

  Score > {{HOLD_UPPER}}   →   BUY
  Score < {{HOLD_LOWER}}   →   SELL
  Otherwise                →   HOLD

State the signal and which boundary it crossed (or that it fell within
the HOLD band).

---

OUTPUT 3 — STRUCTURED SUMMARY

Extract the following fields from the document. For each field, use only
information explicitly stated in the document. If a field is absent,
write "Not disclosed."

  revenue:           Reported revenue figure and any growth/decline commentary.
  eps:               Reported earnings per share and any variance commentary.
  guidance:          Forward-looking statements on revenue, earnings, or growth.
  margin:            Gross, operating, or net margin commentary.
  key_risks:         Explicitly stated risks, headwinds, or concerns. List each
                     as a separate item. If none stated, return an empty list.
  key_opportunities: Explicitly stated growth drivers or tailwinds. List each
                     as a separate item. If none stated, return an empty list.
  management_tone:   The overall register of management language. Choose the
                     best-fit label from: [confident, cautious, defensive,
                     optimistic, neutral, mixed] and add a one-sentence
                     justification quoting the document.

---

OUTPUT 4 — EVIDENCE QUOTES

For every material claim made in Outputs 1–3, provide a direct verbatim
quote from the document that supports it.

Each evidence item must contain:
  claim:       The specific claim being supported (one sentence).
  quote:       Verbatim text from the document. Include enough surrounding
               context that the quote is understandable in isolation
               (typically 1–3 sentences). Do not paraphrase.
  confidence:  HIGH if the quote directly and unambiguously supports the claim.
               MEDIUM if the quote is relevant but indirect or partial.
               LOW if you are relying on inference to connect the quote to the claim.
  flag:        "SUPPORTED" if confidence is HIGH or MEDIUM and the quote is
               a fair representation. "UNCERTAIN: [reason]" if you are not
               confident the quote adequately supports the claim, or if the
               claim required inference beyond the text.

Minimum coverage: every numeric figure in the summary, the sentiment
score rationale, and the management tone label must each have at least
one evidence quote. Do not include quotes that do not correspond to a
specific claim.

---

RETURN FORMAT

Return only the following JSON object. No other text. No markdown.
The output must be directly parseable by Python's json.loads().

{
  "document_id": "{{TICKER}}_{{REPORT_TYPE}}_{{REPORT_DATE}}",
  "sentiment": {
    "score": <float, two decimal places>,
    "rationale": "<2–3 sentence explanation grounded in the document>"
  },
  "signal": {
    "direction": "<BUY | HOLD | SELL>",
    "hold_upper_threshold": {{HOLD_UPPER}},
    "hold_lower_threshold": {{HOLD_LOWER}},
    "boundary_crossed": "<upper | lower | none — HOLD band>"
  },
  "summary": {
    "revenue": "<string | 'Not disclosed'>",
    "eps": "<string | 'Not disclosed'>",
    "guidance": "<string | 'Not disclosed'>",
    "margin": "<string | 'Not disclosed'>",
    "key_risks": ["<risk>", "..."],
    "key_opportunities": ["<opportunity>", "..."],
    "management_tone": {
      "label": "<confident | cautious | defensive | optimistic | neutral | mixed>",
      "justification": "<one sentence with supporting language from document>"
    }
  },
  "evidence": [
    {
      "claim": "<the specific claim>",
      "quote": "<verbatim text from document>",
      "confidence": "<HIGH | MEDIUM | LOW>",
      "flag": "<SUPPORTED | UNCERTAIN: reason>"
    }
  ],
  "review_flags": [
    {
      "field": "<which output field this concerns>",
      "reason": "<why a human reviewer should check this>"
    }
  ],
  "output_meta": {
    "evidence_count": <int>,
    "uncertain_count": <int>,
    "review_flag_count": <int>,
    "not_disclosed_count": <int>
  }
}

</task>
```

---

## VARIABLE REFERENCE

| Variable          | Type    | Example                       | Notes                                              |
|-------------------|---------|-------------------------------|----------------------------------------------------|
| `{{COMPANY}}`     | string  | `"Meta"`                      | Full company name                                  |
| `{{TICKER}}`      | string  | `"META"`                      | Exchange ticker                                    |
| `{{SECTOR}}`      | string  | `"Technology"`                | One of the 7 project sectors                       |
| `{{REPORT_TYPE}}` | string  | `"Earnings Call Transcript"`  | Or `"FOMC Minutes"`, `"8-K Filing"`                |
| `{{REPORT_DATE}}` | string  | `"2024-10-30"`                | ISO 8601 date of publication                       |
| `{{FISCAL_PERIOD}}`| string | `"Q3 2024"`                   | Quarter and year                                   |
| `{{REPORT_TEXT}}` | string  | (full document text)          | Pre-assembled by point_in_time.py                  |
| `{{HOLD_UPPER}}`  | float   | `0.15`                        | SET BEFORE SEEING RESULTS. Do not tune to outcomes |
| `{{HOLD_LOWER}}`  | float   | `-0.15`                       | SET BEFORE SEEING RESULTS. Do not tune to outcomes |

---

## RECOMMENDED API SETTINGS

Using DeepSeek via the OpenAI-compatible SDK. Install with: `pip install -r requirements.txt`

```python
import json, os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # picks up DEEPSEEK_API_KEY from .env

client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

response = client.chat.completions.create(
    model="deepseek-chat",   # DeepSeek-V3 general model — use for all Route A/B calls
                              # "deepseek-reasoner" (R1) available for hard reasoning
                              # tasks but slower and more expensive; not needed here
    max_tokens=4096,          # Evidence quotes can be verbose; 4k is a safe floor
    temperature=0,            # Critical: zero temp for consistency measurement
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": USER_MESSAGE}   # Populated user message
    ]
)

# Extract text — different response structure from Anthropic
output_text = response.choices[0].message.content

# DeepSeek occasionally wraps output in ```json fences despite instructions.
# Strip defensively before parsing.
clean = output_text.strip()
if clean.startswith("```"):
    clean = clean.split("```")[1]
    if clean.startswith("json"):
        clean = clean[4:]
result = json.loads(clean.strip())

# Cost logging — verify current rates at platform.deepseek.com/docs/pricing
# DeepSeek caches repeated system prompts: after the first call in a batch,
# the system prompt is served from cache at a lower input rate.
INPUT_PRICE_PER_M  = 0.27   # USD/M input tokens (cache miss)
CACHED_PRICE_PER_M = 0.07   # USD/M input tokens (cache hit)
OUTPUT_PRICE_PER_M = 1.10   # USD/M output tokens

cost_log = {
    "input_tokens":       response.usage.prompt_tokens,
    "output_tokens":      response.usage.completion_tokens,
    "total_tokens":       response.usage.total_tokens,
    "estimated_cost_usd": (response.usage.prompt_tokens     * INPUT_PRICE_PER_M  / 1_000_000) +
                           (response.usage.completion_tokens * OUTPUT_PRICE_PER_M / 1_000_000)
}
```

---

## CONSISTENCY LOGGING (PROJECT REQUIREMENT)

The project requires measuring consistency across repeated runs and
prompt reformulations. For each document, run the prompt N=3 times
(same inputs, temperature=0 should produce identical results; if it
does not, that itself is a finding). Log agreement on the directional
signal:

```python
signals = [run_1["signal"]["direction"],
           run_2["signal"]["direction"],
           run_3["signal"]["direction"]]

agreement_rate = len(set(signals)) == 1  # True = full agreement
```

For cross-prompt-reformulation consistency (the harder test required
by the brief), maintain 2–3 minor prompt variants (e.g., reordering
the scoring anchor points, rewording the HOLD band instruction) and
run all variants on a subset of documents. Report % agreement on the
directional signal across variants per document.

---

## WHAT THE `review_flags` FIELD IS FOR

The project's human audit protocol uses four labels:
Accept / Edit / Reject / Unclear. The `review_flags` array in the
output directs the reviewer's attention to specific claims the model
itself is uncertain about. A high `review_flag_count` on a document
signals ambiguous source language or an underspecified output, not
necessarily a model failure. Log it per document and per context arm
alongside the Reject (hallucination) rate.

---

## NOTES ON ROUTE COMPATIBILITY

- **Route A (core):** This prompt is the `llm_micro.py` call.
  Feed it transcripts only. Macro layer (`llm_macro.py`) uses the
  same prompt structure but receives Fed minutes as `{{REPORT_TEXT}}`
  and `{{REPORT_TYPE}} = "FOMC Minutes"`. Use `model="deepseek-chat"`
  for both — no reason to use the reasoner model for either layer.

- **Route B extension:** When the news layer is added, use this same
  prompt structure for `llm_news.py` with `{{REPORT_TYPE}} = "News Article"`.
  The blend happens numerically outside the model in `blend.py` —
  each call returns a sentiment score that blend.py combines at the
  configured weight. The prompt itself does not change.

- **The macro read for Fed minutes:** The sentiment score from a Fed
  minutes call represents dovish/hawkish positioning, not company
  earnings. The scoring anchor points in the prompt handle this via
  the note under Output 1. No separate prompt is needed.

- **Model choice note:** `deepseek-chat` (V3) is the right call for
  all pipeline runs. `deepseek-reasoner` (R1) produces chain-of-thought
  traces which inflate output tokens significantly and are not needed
  for structured extraction at temperature=0. Only consider it if
  you observe systematic failures on ambiguous documents.
