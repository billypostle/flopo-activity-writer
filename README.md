# FloPo Activity Writer

Web-based app for generating FloPo activity drafts with OpenAI, validating against writing rules, and creating Notion drafts.

## What it does
- `POST /api/generate-draft`: generate + validate + auto-rewrite (up to 3 attempts), then run an always-on QC editor pass that can patch only failing sections.
- `POST /api/notion/create-draft`: create draft entry in your Notion database.
- `GET /api/resources`: exposes parsed themes/materials/age bands/EYFS + CSV-driven field list.
- `GET /api/generation-status`: live status updates for long-running draft generation.
- `GET /healthz`: unauthenticated health check.

## Security model
- App-level HTTP Basic auth protects all routes except `/healthz`.
- CORS allowlist is controlled by `ALLOWED_ORIGINS`.
- Security headers include CSP `frame-ancestors` for Webflow iframe embedding.
- In `ENVIRONMENT=production`, FastAPI docs/openapi endpoints are disabled.

## Core writing context (mandatory)
- Runtime generation uses one authoritative Model Spec page in Notion.
- Configure:
  - `FLOPO_MODEL_SPEC_URL`
  - `FLOPO_MODEL_SPEC_VERSION` (manual semver, required)
  - `FLOPO_MODEL_SPEC_CACHE_PATH`
  - `FLOPO_MODEL_SPEC_REFRESH_SECONDS`
- The runtime prompt path injects only this Model Spec plus deterministic validators.
- If fetched Model Spec content hash changes, the app logs:
  - `Model spec content changed; bump FLOPO_MODEL_SPEC_VERSION (semver) after review.`

## Project layout
- `app/main.py`: FastAPI app and endpoints
- `app/generator.py`: OpenAI generation + rewrite + QC loop
- `app/validators.py`: deterministic QA checks
- `app/notion_client.py`: Notion page creation
- `app/markdown_writer.py`: markdown rendering helpers
- `app/resources.py`: skill docs and CSV parsers
- `app/static/index.html`: web UI
- `api/index.py`: Vercel Python function entrypoint
- `vercel.json`: Vercel routing/build config
- `tests/`: test suite

## Prerequisites
- Python 3.10+

## Setup
1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill values:
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` (default `gpt-5.2`)
   - `OPENAI_QC_MODEL` (default `o3`)
   - `NOTION_API_KEY`
   - `NOTION_DATABASE_ID`
   - `NOTION_DRAFT_PROPERTY`
   - `FLOPO_MODEL_SPEC_URL`
   - `FLOPO_MODEL_SPEC_VERSION` (default `1.0.0`)
   - `FLOPO_MODEL_SPEC_CACHE_PATH` (default `.cache/model_spec.json`)
   - `FLOPO_MODEL_SPEC_REFRESH_SECONDS` (default `3600`)
   - `NOTION_SKILL_DOCS_MODE` (`local`, `live`, or `live_with_fallback`; default `live_with_fallback`)
   - `NOTION_SKILL_DOCS_REQUEST_TIMEOUT_SECONDS` (default `30`)
   - `ENVIRONMENT` (`development` or `production`)
   - `APP_AUTH_USERNAME`
   - `APP_AUTH_PASSWORD`
   - `ALLOWED_ORIGINS` (comma-separated; default `https://flopo.co.uk`)
4. (Optional) Copy `config/notion_field_map.example.json` to `config/notion_field_map.json` and adjust property mapping.
5. (Optional) Copy `config/notion_skill_docs.example.json` to `config/notion_skill_docs.json` and map each skill doc filename to a Notion page URL/ID.

## Local run
- `uvicorn app.main:app --reload`
- Open `http://127.0.0.1:8000`

## Vercel deployment
1. Create a Vercel project with root directory set to `Tools/Activity_Writer`.
2. Ensure Vercel uses the included `vercel.json` and `api/index.py`.
3. Add all required environment variables in the Vercel dashboard.
4. Deploy and note your `*.vercel.app` URL.
5. Embed that URL in your Webflow password-protected page via iframe.

## Notion integration setup
1. Create a Notion internal integration.
2. Share the target database with that integration.
3. Set `NOTION_API_KEY` and `NOTION_DATABASE_ID` in `.env`.
4. If property names differ, update `config/notion_field_map.json`.

At app startup, Notion config is verified against `GET /v1/databases/{NOTION_DATABASE_ID}`.
If verification fails, `/api/notion/create-draft` returns a clear startup verification error.

## Testing
- `python -m pytest`

## Notes
- Content fields are derived from `Databases/FloPo - Activities - 698734a9856055bb42014e7a (1).csv`.
- Themes, age adaptations, materials, and context are inferred by the model from notes + guidance docs.
- `/api/generate-draft` injects only the Model Spec at runtime (not multi-doc skill guide context).
- QC pass fail-open behavior: if the second-pass QC call fails (request/parse/schema), the API returns the first-pass draft with QC metadata (`qc_applied=false`, `qc_error` populated).
