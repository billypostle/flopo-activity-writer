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
- Runtime generation uses the local FloPo docs in `Documentation/FloPo/Skill docs`.
- Configure:
  - `FLOPO_MODEL_SPEC_URL`
  - `FLOPO_MODEL_SPEC_VERSION` (manual semver, required)
  - `FLOPO_MODEL_SPEC_CACHE_PATH`
  - `FLOPO_MODEL_SPEC_REFRESH_SECONDS`
- The runtime prompt path injects the local model-facing spec plus routed local reference docs.

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
   - `ALLOWED_ORIGINS` (comma-separated; default `https://flopo.co.uk,https://flopo-stage.webflow.io`)
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

## Generation workflow (end-to-end)
`POST /api/generate-draft` runs a fixed pipeline in `app/generator.py`:

1. Load canonical content field order from CSV via `content_fields_from_csv()`.
2. Load the local model-facing spec via `load_model_spec_only()`.
3. Load runtime ethos skill docs via `load_runtime_ethos_skill_docs()`, using the local `Ethos Definitions.md` routing doc and its linked local markdown references.
4. Build initial system/user prompts using notes + local model spec + routed ethos docs.
5. Generate initial JSON draft with `OPENAI_MODEL`.
6. Normalize keys to canonical field labels.
7. Run deterministic validation (`validate_draft`).
8. If validation fails, run targeted rewrite loops (up to `MAX_REWRITE_ATTEMPTS`, default `3`).
9. Run an always-on QC editor pass with `OPENAI_QC_MODEL`.
10. Merge only allowed QC field edits.
11. Re-run deterministic validation after QC merge.
12. Return draft + validation + rewrite/QC metadata.

Status messages are exposed throughout this process via `GET /api/generation-status`.

## Validation framework
Validation is deterministic and implemented in `app/validators.py`. It returns:
- `passed`: overall gate result.
- `blocking_issues`: must be resolved for pass.
- `warnings`: non-blocking quality flags.

Blocking checks:
- Activity title quality and format.
- Required section completeness (except explicitly allowed empty fields).
- Exact section order lock against canonical CSV order.
- Summary and preview presence/shape checks.
- Preview quality checks:
  - no meta-preview language,
  - explicit scene actors,
  - concrete activity detail,
  - no procedural over-disclosure.
- Ethos adaptation depth checks, including Reggio environment change requirement.
- EYFS and safety sufficiency checks (specificity and minimum depth).

Warning checks:
- Potential procedural leakage in Summary/Preview.
- Banned phrase/style drift and passive voice overuse threshold.

## QC editor behavior
The QC pass is a second model call designed for targeted patching, not full rewrite.

Rules enforced by implementation:
- QC response must match required JSON schema (`pass`, `issues`, `fields_to_edit`, `revised_fields`, `editor_notes`, `spec_version`).
- Edited fields must be in the allowed field list.
- `revised_fields` outside `fields_to_edit` are ignored and logged as QC issues.
- Empty edits are rejected for required fields.
- QC edits are accepted only if they do not increase deterministic blocking issues.

Fail-open behavior:
- If QC call fails (network, parse, schema), API still returns first-pass draft.
- In fail-open, `qc_applied=false` and `qc_error` is populated.

## API QC/validation response contract
`POST /api/generate-draft` returns:
- `validation_report`: `{ passed, blocking_issues, warnings }`
- `rewrite_count`: number of rewrite loops executed.
- `qc_applied`: whether QC stage executed with a parseable payload.
- `qc_passed`: whether QC marked pass and final merged draft passed deterministic validation.
- `qc_edited_fields`: exact fields changed by QC merge.
- `qc_issues`: QC issue list (including ignored/discarded edit reasons).
- `qc_error`: fail-open diagnostic string when QC could not be applied.

## Operational QC checklist
Use this checklist before creating a Notion draft:

1. Confirm `validation_report.passed` is `true`.
2. If `qc_applied=false`, review `qc_error` and inspect high-risk sections manually (Preview, Safety, EYFS, Ethos).
3. If `qc_edited_fields` is non-empty, spot-check those fields for tone and factual alignment.
4. If any blocking issues remain, do not publish or sync to final CMS content.
5. Treat warnings as editorial follow-up, especially procedural leakage warnings.

## Testing
- `python -m pytest`
- Key suites for workflow/validation/QC:
  - `tests/test_pipeline_integration.py`
  - `tests/test_validators.py`
  - `tests/test_generator_qc.py`

## Notes
- Content fields are derived from `Databases/FloPo - Activities - 698734a9856055bb42014e7a (1).csv`.
- Themes, age adaptations, materials, and context are inferred by the model from notes + guidance docs.
- `/api/generate-draft` injects the local model spec and routed local ethos skill docs at generation time. Notion is used for activity storage, not documentation reference.
- QC pass fail-open behavior: if the second-pass QC call fails (request/parse/schema), the API returns the first-pass draft with QC metadata (`qc_applied=false`, `qc_error` populated).
- Extended runbook: `Documentation/Activity Writer Workflow, Validation and QC.md`.
