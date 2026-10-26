# AlphaLoom

AlphaLoom reads a company's annual report (10-K) and turns the two sections investors read first, **Business (Item 1)** and **Risk Factors (Item 1A)**, into a short brief. Every point in the brief cites the paragraphs it came from, so any claim can be checked against the original filing. The risk section also gets a sentiment score from FinBERT, a model trained on financial text, so you can compare its tone across companies and years.

A 10-K's risk section often runs to dozens of pages. AlphaLoom cuts it to about a page and keeps every line traceable to its source.

## How it works

```
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│ SOURCE                 │      │ INGEST                 │      │ STRUCTURE              │
│                        │      │                        │      │                        │
│ financialdatasets.ai   │ ───► │ skip if already cached │ ───► │ paragraphs + span IDs  │
│ /filings/items         │      │ sha256 + manifest      │      │ biz::p003, risks::p012 │
│ Item 1 + Item 1A only  │      │ raw JSON + plain text  │      │ regex fallback parser  │
└────────────────────────┘      └────────────────────────┘      └────────────┬───────────┘
                                                                             │
                                                                             ▼
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────┴───────────┐
│ INTERFACE              │      │ MERGE + SCORE          │      │ SUMMARIZE              │
│                        │      │                        │      │                        │
│ Gradio web app         │ ◄─── │ drop uncited claims    │ ◄─── │ 6 paragraphs per call  │
│ terminal CLI           │      │ fuzzy dedupe, top 7    │      │ gpt-4o-mini, JSON mode │
│ brief + risk tone      │      │ FinBERT on Item 1A     │      │ content-hash cache     │
└────────────┬───────────┘      └────────────┬───────────┘      └────────────┬───────────┘
             │                               │                               │
═════════════╧═══════════════════════════════╧═══════════════════════════════╧════════════
  STORAGE   one interface, two backends: local disk or S3 (USE_S3_STORAGE)
            raw/ · processed/ · cache/summaries/ · dash/  (same paths in both)
```

1. **Ingest** asks the filings API for only the enabled sections, not the whole filing. It hashes the text and writes the raw JSON, a plain-text copy and a manifest. If a filing has already been processed, ingestion skips the API call.
2. **Structure** splits each section into paragraphs and gives every paragraph a stable ID, such as `risks::p012`. These IDs are what the summaries cite.
3. **Summarize** sends the paragraphs to the LLM six at a time. Each call returns bullets, key numbers and uncertainties, and every item carries the span IDs of the paragraphs that support it.
4. **Merge + score** combines the chunk results into one list per section, checks every citation and runs FinBERT over the risk section.
5. **Interface** shows the brief and the risk-tone score in the web app or the terminal. The citations are stored in `summaries.json`.

## Engineering decisions

### The model can only cite what it was shown, and every citation is checked

An LLM summary of a legal document is only useful if you can verify it. Each prompt includes the exact list of span IDs in that chunk and tells the model to cite only from that list. After the calls return, [`merge_validate.py`](processing/summarize/merge_validate.py) checks every citation against the paragraphs that actually exist in the section. Invalid IDs are removed. A claim with no valid citation left is dropped entirely, and the drop is logged as a warning in the output.

The prompt alone is not enough, because a model can still invent a plausible-looking ID like `risks::p999`. The post-check catches that.

### Fetch sections, not filings

A full 10-K is hundreds of pages, and most of it is financial statements and exhibits the brief never uses. Ingestion asks the API for the enabled sections only (set in [`config/sections_config.py`](config/sections_config.py)). That keeps the downloads small and means no time is spent locating section boundaries.

If the API rejects the targeted request, ingestion falls back to the full filing, and a regex-based [sectionizer](processing/sectionize.py) finds the Item headings itself. The targeted path is the fast one; the fallback means a filing still gets processed when the targeted request fails.

### Summarize in small chunks, then merge

Each section is cut into chunks of six paragraphs, and each chunk becomes its own `gpt-4o-mini` call (JSON mode, temperature 0.2). Small chunks keep the model focused on the text in front of it, keep each list of allowed citations short, and can run in parallel: 8 threads in standard mode, or asyncio in async mode.

The merge step then:
- joins the chunk results,
- removes near-duplicates (token-set similarity ≥ 0.88, combining their citations),
- keeps the top seven items in each list.

Doing the merge in code rather than with a second LLM call keeps that step deterministic and free.

### Cache by content, not by run

Each chunk's LLM output is stored under a key built from the ticker, form, year, section, the SHA-256 of the section's text and the chunk number. If you re-run an unchanged filing, every chunk is a cache hit and no API calls are made. If a section's text changes, its hash changes, so only that section is sent to the LLM again.

A second layer of caching sits in front of the whole pipeline: if a filing already has a `summaries.json`, ingestion stops early and the existing result is reused.

### A dedicated sentiment model alongside the LLM

LLMs are good at extracting points from text but give inconsistent numbers when asked to rate tone, so their scores aren't reliable for comparing filings. For the risk section, AlphaLoom runs [`yiyanghkust/finbert-tone`](https://huggingface.co/yiyanghkust/finbert-tone), a BERT model fine-tuned on financial language:

- The text is packed into chunks of about 400 tokens along sentence boundaries.
- FinBERT classifies each chunk, and the class probabilities are averaged.
- The headline score is P(positive) − P(negative), which ranges from −1 to +1.

The same text always gets the same score. That makes it possible to compare companies, or one company's filings over time. The model's label order is read from its own config rather than hardcoded.

### Stages communicate through files

Ingestion, structuring and summarization are separate programs. Each one passes its results to the next as JSON files:

- Ingestion writes the raw filing (JSON plus a plain-text copy).
- Structuring turns that into `sections.json` and `chunks.json`.
- Summarization produces `summaries.json`.

The web app runs the stages in order, but any stage can be re-run on its own and every intermediate file can be inspected. When a summary looks wrong, you can open `chunks.json` and see exactly what the model was given.

Data is kept in three zones: `raw/` holds data exactly as received, `processed/` holds everything derived from it, and `dash/` holds the pointers the interface reads.

### One storage interface, two backends

All file reads and writes go through [`HybridStorage`](ingestion/storage/hybrid.py). Setting `USE_S3_STORAGE=true` moves everything to S3, and the stage code doesn't change. An S3 key is the local path with the leading `data/` removed, so [`migrate_to_s3.py`](migrate_to_s3.py) can move an existing local dataset to S3 one-to-one. Local writes go to a temporary file first and are then renamed into place, so a crash never leaves a half-written JSON file.

## Output

Each filing produces `processed/{TICKER}/{FORM}/{YEAR}/summaries.json`:

```jsonc
{
  "ticker": "AAPL",
  "form": "10-K",
  "year": 2023,
  "sections": [
    {
      "section_name": "Item 1A",
      "section_alias": "Risk Factors",
      "section_hash": "3f9c2a7e1b04d8c6",   // first 16 hex chars of the section text's SHA-256
      "bullets":       [{ "text": "…", "span_ids": ["risks::p004", "risks::p005"] }],
      "key_numbers":   [{ "text": "…", "span_ids": ["risks::p031"] }],
      "uncertainties": [{ "text": "…", "span_ids": ["risks::p012"] }],
      "sentiment_analysis": {
        "negative": 0.61, "neutral": 0.34, "positive": 0.05,
        "overall_score": -0.56, "sentiment_label": "Negative", "confidence": 0.61,
        "model_used": "yiyanghkust/finbert-tone", "chunks_analyzed": 48
      },
      "warnings": ["Dropped item with no valid citations: '…'"]
    }
  ]
}
```

The values above show the format only; they are not real results.

## Running it

Requires Python 3.9+. FinBERT runs on a CUDA GPU if one is available, and on the CPU otherwise.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.sample config/.env   # then fill in the keys below
```

| Variable | Required | Purpose |
|---|---|---|
| `FINANCIAL_DATASETS_API_KEY` | yes | Filing text from financialdatasets.ai |
| `OPENAI_API_KEY` | yes | Chunk summarization |
| `USE_S3_STORAGE` | no | `true` to store everything in S3 instead of `data/` |
| `AWS_S3_BUCKET`, `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | if S3 | S3 bucket and credentials |

**Web app** (http://localhost:7860):

```bash
python app.py
```

**Terminal app** (local storage only, so leave `USE_S3_STORAGE` unset):

```bash
python terminal_app.py
```

**One stage at a time:**

```bash
python -m ingestion.run_filings_s3 --ticker AAPL --filing-type 10-K --year 2023
python processing/sectionize.py --ticker AAPL --form 10-K --year 2023 \
  --input-text data/raw/filings/AAPL/<file>.txt --out-dir data/processed/AAPL/10-K/2023
python -m processing.summarize.runner AAPL 10-K 2023 --sections "Item 1" "Item 1A"
```

Use `processing.summarize.runner_async` with `--max-concurrent N` for the async runner, which skips the FinBERT step. Tests: `pytest tests/`.

## Repository layout

```
app.py, terminal_app.py      web and terminal interfaces; run the stages in order
config/                      enabled sections, env template
ingestion/
  providers/                 financialdatasets.ai client (+ legacy Seeking Alpha transcripts)
  storage/                   HybridStorage, local backend
  run_filings_s3.py          ingestion entry point
processing/
  sectionize.py              regex sectionizer + paragraph span IDs
  summarize/                 prompt, LLM clients, chunk cache, merge/validate, runners
  sentiment/                 FinBERT analyzer
services/                    S3 client, pipeline-level cache
tests/                       sectionizer heading-pattern tests
```

## Limitations

- The web app offers four companies (AAPL, MSFT, NVDA, TSLA) and fiscal years 2020–2023. The pipeline itself takes any ticker and year the filings API has.
- The cache key doesn't include the model or prompt version, so changing the prompt means clearing `cache/summaries/` by hand.
- The sync and async runners are separate implementations of the same logic and need to be merged into one.
- FinBERT reads text in chunks of about 400 tokens, so a single risk statement that spans a chunk boundary is scored in two parts.
