# FloPo Activity Writer

Local-first web app for generating FloPo activity drafts with OpenAI, validating against writing rules, saving markdown locally, and creating Notion drafts.

## What it does
- `POST /api/generate-draft`: generate + validate + auto-rewrite (up to 3 attempts), then run an always-on QC editor pass that can patch only failing sections.
- `POST /api/save-local`: save markdown to `C:\Users\billy\Documents\FloPo\Activities`.
- `POST /api/notion/create-draft`: create draft entry in your Notion database.
- `POST /api/publish/notion-webflow-draft`: create Notion draft, then create Webflow CMS draft (all-or-error with partial-result details).
- `GET /api/resources`: exposes parsed themes/materials/age bands/EYFS + CSV-driven field list.

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
- `app/generator.py`: OpenAI generation + rewrite loop
- `app/validators.py`: deterministic QA checks
- `app/notion_client.py`: Notion page creation
- `app/webflow_client.py`: Webflow CMS staged draft creation
- `app/markdown_writer.py`: markdown rendering + save logic
- `app/resources.py`: skill docs and CSV parsers
- `app/static/index.html`: local UI
- `tests/`: parser/validator/save tests

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
   - `WEBFLOW_API_TOKEN` (needs `CMS:write` scope)
   - `WEBFLOW_COLLECTION_ID` (optional if CSV defaults are present)
   - `WEBFLOW_CMS_LOCALE_IDS` (optional comma-separated list; optional if CSV default is present)
   - `WEBFLOW_API_BASE_URL` (default `https://api.webflow.com`)
4. (Optional) Copy `config/notion_field_map.example.json` to `config/notion_field_map.json` and adjust property mapping.
5. (Optional) Copy `config/notion_skill_docs.example.json` to `config/notion_skill_docs.json` and map each skill doc filename to a Notion page URL/ID.
6. (Optional) Copy `config/webflow_field_map.example.json` to `config/webflow_field_map.json` and adjust Webflow field slugs.

## Run
- `uvicorn app.main:app --reload`
- Open `http://127.0.0.1:8000`

## One-click launch (Windows)
- Double-click [Launch_FloPo_Activity_Writer.bat](C:\Users\billy\Documents\FloPo\Tools\Activity_Writer\Launch_FloPo_Activity_Writer.bat)
- It will:
  - start the server if it is not already running
  - open `http://127.0.0.1:8000` in your browser

Repo-root shortcuts are also available:
- [Open_FloPo_Activity_Writer.bat](C:\Users\billy\Documents\FloPo\Open_FloPo_Activity_Writer.bat)
- [Stop_FloPo_Activity_Writer.bat](C:\Users\billy\Documents\FloPo\Stop_FloPo_Activity_Writer.bat)

To stop the server, double-click:
- [Stop_FloPo_Activity_Writer.bat](C:\Users\billy\Documents\FloPo\Tools\Activity_Writer\Stop_FloPo_Activity_Writer.bat)

## Notion integration setup
1. Create a Notion internal integration.
2. Share the target database with that integration.
3. Set `NOTION_API_KEY` and `NOTION_DATABASE_ID` in `.env`.
4. If property names differ, update `config/notion_field_map.json`.
5. Draft status is not set automatically; manage it manually in Notion.

At app startup, Notion config is verified against `GET /v1/databases/{NOTION_DATABASE_ID}`.
If verification fails, `/api/notion/create-draft` returns a clear startup verification error.

## Webflow integration setup
1. Create a Webflow API token with `CMS:write`.
2. Set `WEBFLOW_API_TOKEN` in `.env`.
3. Set `WEBFLOW_COLLECTION_ID` and `WEBFLOW_CMS_LOCALE_IDS`, or allow CSV defaults from `Collection ID` and `Locale ID`.
4. Update `config/webflow_field_map.json` with your collection's field slugs.
5. Use `POST /api/publish/notion-webflow-draft` to create both drafts in sequence.

If Notion succeeds and Webflow fails, the endpoint returns `success=false` and includes the created Notion page details in the response.

## Testing
- `pytest`

## Notes
- Content fields are derived from `Databases/FloPo - Activities - 698734a9856055bb42014e7a (1).csv`.
- Themes, age adaptations, materials, and context are inferred by the model from notes + guidance docs (no manual guided selectors in UI).
- Visual style guide and strategic grounding docs are intentionally excluded from generation context.
- Skill docs can still be loaded live from Notion for admin/debug tooling via `NOTION_SKILL_DOCS_MODE`:
  - `local`: use local files only from `Skill docs/`.
  - `live`: use Notion-only for all included skill docs; every doc must be mapped in `config/notion_skill_docs.json`.
  - `live_with_fallback`: attempt Notion first for mapped docs, then fall back to local files.
- `/api/generate-draft` no longer injects multi-doc skill guides at runtime; it injects only the Model Spec.
- QC pass fail-open behavior: if the second-pass QC call fails (request/parse/schema), the API returns the first-pass draft with QC metadata (`qc_applied=false`, `qc_error` populated).
