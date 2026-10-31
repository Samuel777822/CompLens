# CompLens

Checks a photo of a product label against the **Legal Metrology (Packaged Commodities) Rules, 2011** and
flags each violation with the exact rule it breaks. Built from the team's *CompLens Compliance Rulebook* (SIH26034).

```
photo(s) -> OpenCV clean-up (3 variants) -> EasyOCR (en+hi, then en) -> row/column text views -> product detection
      -> field extraction -> rules engine -> JSON report (+ Supabase log)
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt                           # easyocr pulls in PyTorch (big download)
cp .env.example .env                                      # fill Supabase values if you want logging
uvicorn app.main:app --reload
```

Open http://localhost:8000 (web UI) or http://localhost:8000/docs (API docs).
The first start downloads the EasyOCR model weights (one time, needs internet) and then loads them in the background;
`GET /health` shows `ocr.status` (`loading`, then `ready`).

No Supabase yet? Leave those env vars empty. Everything works; scans just are not logged.

## Deploying (Supabase + GitHub + an always-on Docker server)
Full step-by-step (Supabase, GitHub, a small server, Docker, HTTPS) in [DEPLOY-PYCHARM-AZURE.md](DEPLOY-PYCHARM-AZURE.md).
The app ships as a Docker image (`Dockerfile`) plus `docker-compose.yml` (app + Caddy web server), so it runs the same on any VPS.
It was moved off Vercel because EasyOCR + PyTorch need about 2 GB, and serverless hosts unload the app when idle (slow cold starts).

## Supabase (optional)

1. Create a project, open **SQL editor**, paste and run `supabase/schema.sql`.
2. Put `SUPABASE_URL` and the **service role** key in `.env`. Backend only. Never in frontend code, never in git.

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/api/scan` | multipart: one or more `files` (jpg/png/webp: front, back, spine are checked as ONE label), `category` (default `auto`), optional `pack_type` (`can`/`bottle`/`other`) |
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
| `app/classify.py` | what product is this, and how is its quantity measured (weight / volume / count / length / area; Table I vs II) |
| `app/pipeline.py` | multi-pass OCR, row/column views, rotation fix, multi-photo merge, best-report selection |
| `app/extract.py` | regex finders for each field (all text-in, testable without images) |
| `app/engine.py` | one check function per rule + Rule 26 exemptions, run in the rulebook's order |
| `app/data.py` | categories, standard pack-size tables (Part C), exemption lists, limitations text |
| `app/preprocess.py` / `app/ocr.py` | OpenCV clean-up, EasyOCR + merging boxes into lines |
| `app/db.py`, `supabase/schema.sql` | audit log + image storage |
| `public/index.html` | web UI (served by FastAPI; calls the API above) |

Order of checks: exemptions (Rule 26) -> legibility/language (Rule 9) -> Rule 6 fields -> pack size (Rule 5).

## Tests

```bash
pytest -q          # 100+ tests: every PASS/FAIL example from the rulebook plus edge cases
python -m scripts.run_samples      # regenerates samples/sample_results.json
```

## Decisions and known limits (say these out loud in the demo)

- **Rule 7 and 8 (font size / spacing) are skipped for EVERY product, and only those.** A photo has no real-world scale. The product is still fully recognised: the report says which table (I or II) the size rule would use.
- **Any product is understood.** Category `auto` (default) detects it from the label text; if it is not a listed commodity, the unit of the net quantity decides how it is measured (g/kg = weight, ml/l = volume, pages/pcs/pairs = count, m = length, sq m = area). A notebook's net quantity is its page count.
- **Category**: `auto` detects it; picking one yourself overrides it (a warning appears if the label text disagrees). Exemption categories (fast food, scheduled drugs, agri produce) are never guessed.
- **Manufacturer** is accepted as a name + full address with PIN even with no "Manufactured by" wording (logo + address is how most notebooks do it). It is noted, not silently trusted.
- **OCR digit fix**: the Hindi model returns digits as Devanagari/Bengali numerals; they are normalised to 0-9 before any rule runs.
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
