# PackCheck

Checks a photo of a product label against the **Legal Metrology (Packaged Commodities) Rules, 2011** and
flags each violation with the exact rule it breaks. Built from the team's *PackCheck Compliance Rulebook* (SIH26034).

```
photo -> OpenCV clean-up -> EasyOCR (en + hi) -> field extraction (regex) -> rules engine -> JSON report (+ Supabase log)
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                           # easyocr pulls in PyTorch (big download)
cp .env.example .env                                      # fill Supabase values if you want logging
uvicorn app.main:app --reload
```

Open http://localhost:8000 (web UI) or http://localhost:8000/docs (API docs).
The first photo scan downloads the EasyOCR model weights (one time, needs internet).

No Supabase yet? Leave those env vars empty. Everything works; scans just are not logged.

## Supabase (optional)

1. Create a project, open **SQL editor**, paste and run `supabase/schema.sql`.
2. Put `SUPABASE_URL` and the **service role** key in `.env`. Backend only. Never in frontend code, never in git.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/scan` | multipart: `file` (jpg/png/webp), `category`, optional `pack_type` (`can`/`bottle`/`other`) |
| POST | `/api/check-text` | JSON `{text, category, pack_type}`. Rules engine only, no OCR. Best for testing |
| GET | `/api/categories` | category keys for the dropdown |
| GET | `/api/samples` | demo labels |
| GET | `/api/history`, `/api/scans/{id}` | logged scans (needs Supabase) |

Per-field output (superset of the rulebook schema):

```json
{ "field": "net_quantity", "status": "FAIL", "violation_code": "VAGUE_LANGUAGE",
  "detected_text": "approx 120g", "rule_reference": "Rule 6(1)(c)",
  "detail": "Banned qualifier 'approx'. Net quantity must be a definite number.",
  "sub_case": null, "confidence": 0.93 }
```

`status`: PASS, FAIL, REVIEW (needs a human), NOT_APPLICABLE, EXEMPT.
`violation_code`: MISSING, FORMAT_ERROR, UNIT_ERROR, NONSTANDARD_PACK, VAGUE_LANGUAGE, LANGUAGE_ERROR, LOW_CONFIDENCE.
`SIZE_ERROR` is not implemented (Rule 7 skipped by team decision).
Overall `verdict`: COMPLIANT, NON_COMPLIANT, NEEDS_REVIEW, EXEMPT. Full examples: `samples/sample_results.json`.

## Where things are

| File | Rulebook part |
|---|---|
| `app/extract.py` | regex finders for each field (all text-in, testable without images) |
| `app/engine.py` | one check function per rule + Rule 26 exemptions, run in the rulebook's order |
| `app/data.py` | categories, standard pack-size tables (Part C), exemption lists, limitations text |
| `app/preprocess.py` / `app/ocr.py` | OpenCV clean-up, EasyOCR + merging boxes into lines |
| `app/db.py`, `supabase/schema.sql` | audit log + image storage |
| `static/index.html` | web UI (served by FastAPI; calls the API above) |

Order of checks: exemptions (Rule 26) -> legibility/language (Rule 9) -> Rule 6 fields -> pack size (Rule 5).

## Tests

```bash
pytest -q          # 81 tests: every PASS/FAIL example from the rulebook plus edge cases
python -m scripts.run_samples      # regenerates samples/sample_results.json
```

## Decisions and known limits (say these out loud in the demo)

- **Rule 7 and 8 are not checked.** A photo has no real-world scale. Stated limitation, per the rulebook.
- **Category comes from the user** (dropdown), as the rulebook suggests. The OCR text alone rarely says "this is tea".
- **Low OCR confidence never silently passes or fails.** It becomes REVIEW / LOW_CONFIDENCE. A field that is
  "missing" on a blurry photo is also REVIEW, because the text may just not have been read.
- **"Marketed by" only** is flagged as FORMAT_ERROR with `sub_case: MARKETED_BY_ONLY`. Same for importer without
  foreign manufacturer and for a manufacturer with no PIN code.
- **Expiry dates are not accepted as manufacture dates.** Date next to Exp/Best before is ignored.
- **Generic name** is a keyword match. If the category is "other" and no product word is recognised, the result is
  REVIEW, not FAIL, because the code cannot tell a brand from a product name.
- **Language** is checked on the whole label. EasyOCR configured for en+hi cannot read Kannada/Tamil etc., so
  regional-only labels reach the engine as junk or very little text (REVIEW). `LANGUAGE_ERROR` fires reliably on text input.
- **Pincode check** is a 6-digit pattern near the manufacturer line. A stray 6-digit number can fool it.
- The MRP rounding rule (paise) is not checkable from a photo and is not implemented.
- The OCR part (EasyOCR on real photos) was **not run in the build environment**. Everything else is tested.
  First thing to do on your machine: scan 8 to 10 real labels and tune regexes in `extract.py` against what EasyOCR really outputs.
