# Lab Budget Monitoring System

## Database setup
Copy `.env.example` to `.env` and replace `<PASSWORD>` with your local Postgres password:

```powershell
Copy-Item .env.example .env
```

The backend automatically reads `.env` from the repo root. Real `.env` files are ignored by Git.
Login cookies stay valid for `ACCESS_TOKEN_EXPIRE_MINUTES`; restarting the frontend does not clear browser cookies.

### Which SQL file to run, and when

`db_setup.sql` and `migrate_lab_ic_to_assignments.sql` live in `backend/migrations/`. `dev_seed.sql` and `w7_auth_seed.sql` live in `backend/seeds/`.

| File | What it does | When to run it |
|---|---|---|
| `db_setup.sql` | **Destructive.** Drops and recreates every table with the current schema (including `lab_ic_assignments`, `users.is_active` and `password_reset_tokens`). Creates no data. | A brand-new database, or when you want to wipe everything and start over. **Never** on a database whose data you want to keep. |
| `migrate_lab_ic_to_assignments.sql` | Non-destructive, safe to re-run. Converts the old Lab IC model (`users.lab_id` or `labs.user_id`) into `lab_ic_assignments`, keeping existing data. | Only on an **existing** database created before `lab_ic_assignments` existed. Not needed after a fresh `db_setup.sql`. Do not also run the older `migrate_lab_ic_to_labs.sql`. |
| `dev_seed.sql` | Safe to re-run. Adds schema columns the app needs that `db_setup.sql` does not create (`pr_status` on purchase requests and lines, the alert-notification flags on `labs` and `lab_groups`, and nullable `labs.lab_group_id`). Also seeds roles, the FY2026 budget period, spending categories, lab groups, labs and three test users. | After `db_setup.sql` or the migration, on every database you set up, including fresh ones. Despite the name, it contains schema changes, so skipping it leaves the app with missing columns. |
| `w7_auth_seed.sql` | Safe to re-run. Adds demo users with Lab IC assignments for testing Lab IC scoping. Reuses the same lab groups and labs as `dev_seed.sql`. | Optional, after `dev_seed.sql`, and only once `lab_ic_assignments` exists. |

**New database**

1. Create the empty database (once):
   ```powershell
   psql "postgresql://postgres:<PASSWORD>@localhost:5432/postgres" -c "CREATE DATABASE budget_system;"
   ```
2. Run `db_setup.sql`, connected to `budget_system`.
3. Run `dev_seed.sql`.
4. Optionally run `w7_auth_seed.sql`.

**Existing database with data you want to keep**

1. Back up first (for example `pg_dump`).
2. Run `migrate_lab_ic_to_assignments.sql` once. Skip this if the database already has a `lab_ic_assignments` table.
3. Run `dev_seed.sql`.
4. Optionally run `w7_auth_seed.sql`.

Do not run `db_setup.sql` on an existing database unless you intend to erase it.

Run each file the same way, changing only its path (for example `backend/migrations/migrate_lab_ic_to_assignments.sql` or `backend/seeds/w7_auth_seed.sql`):

```powershell
$env:DATABASE_URL="postgresql://postgres:<PASSWORD>@localhost:5432/budget_system"
psql "$env:DATABASE_URL" -f backend/migrations/db_setup.sql
psql "$env:DATABASE_URL" -f backend/seeds/dev_seed.sql
```

If PowerShell says `psql` is not recognized, use the full PostgreSQL path:

```powershell
$env:DATABASE_URL="postgresql://postgres:<PASSWORD>@localhost:5432/budget_system"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" "$env:DATABASE_URL" -f backend/seeds/dev_seed.sql
```

You can also open any of these files in pgAdmin's Query Tool and run them there. Make sure the Query Tool is connected to `budget_system` first.

### Seeded login accounts

Seeded local login accounts use placeholder passwords when `ALLOW_PLACEHOLDER_PASSWORDS=true`. Use any non-empty password for them in local development.

From `dev_seed.sql`:

```text
admin@test.com
teamlead.fcb@test.com
labic@test.com
```

`labic@test.com` has no lab assignment. To test Lab IC scoping, also run `w7_auth_seed.sql`, which adds:

```text
admin@example.com          admin
teamlead.fcb@example.com   team lead, FCB group
teamlead.non@example.com   team lead, no group
labic.fcb@example.com      Lab IC, lab W3-01-021 (primary)
labic.ict@example.com      Lab IC, lab E2-02-02 (primary)
labic.non@example.com      Lab IC, no labs assigned
```

Re-running `w7_auth_seed.sql` resets these accounts' role, group and password hash back to the seed values.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173/`.

## Backend setup

```bash
python -m pip install -r backend/requirements.txt
python -m pip install -r backend/requirements-dev.txt
$env:PYTHONPATH="backend"
python -m uvicorn app.main:app --reload --app-dir backend --port 8080
```

The backend runs on `http://127.0.0.1:8080/`. The frontend dev server proxies `/api` requests to this backend.

## Ask AI setup

Ask AI is the floating button shown to every logged-in role. It answers questions about the budget and purchase data that user is allowed to see. The backend fetches and role-scopes the data first; the AI provider only turns those figures into a written answer and never queries the database.

Set these in the root `.env`. They are backend only, so never prefix them with `VITE_`:

| Variable | Required | What it does |
|---|---|---|
| `LLM_API_KEY` | For AI answers | The provider's API key. Leave blank to run Ask AI without an AI provider (see fallback below). |
| `LLM_BASE_URL` | No | Any OpenAI-compatible chat completions endpoint. This is what chooses the provider. |
| `LLM_MODEL` | No | The model name, spelled the way the provider spells it. |

Example for OpenAI:

```text
LLM_API_KEY=<your key>
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

<!-- TODO(client-handover): remove the OpenRouter paragraph below before final submission to the client. -->
OpenRouter is the interim provider during development: `LLM_BASE_URL=https://openrouter.ai/api/v1` with `LLM_MODEL=google/gemini-2.5-flash-lite`. These are also the current defaults when `LLM_BASE_URL` or `LLM_MODEL` is left blank, and the older `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` names are still read if the `LLM_*` ones are not set.

Switching provider means changing these lines and restarting the backend. No code change is needed.

**Fallback without AI.** If `LLM_API_KEY` is blank, the provider is unreachable, returns an error, or takes longer than 30 seconds, `POST /api/chatbot/ask` returns `503` and the widget answers with the built-in rule-based answers from `POST /api/chatbot/query-context` instead. Ask AI keeps working either way; the label under each answer shows which one was used:

- `AI answer · <period> · from N budget lines in your scope`
- `AI unavailable · basic rule-based answer`

Models that reject a custom `temperature` (some OpenAI reasoning models) are retried automatically without it.

## Dependency notes

- Run frontend npm commands from `frontend`, not the repo root.
- Use `frontend/package.json` and `frontend/package-lock.json` for the React app dependencies.
- Do not copy `node_modules` from another folder.
- Do not commit `node_modules`; it is generated by `npm install` and should stay ignored.
- If dependencies are missing, run `npm install` again inside `frontend`.

## Build check

```bash
npm --prefix frontend run lint -- --max-warnings=-1
npm --prefix frontend run type-check
npm --prefix frontend run build
```

```bash
$env:PYTHONPATH="backend"
python -m pytest backend/app/tests
```

Backend CI also runs these checks from the `backend` directory:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy app/
```

Security checks used by CI:

```bash
python -m pip_audit -r backend/requirements.txt
python -m bandit -r backend/app/ -ll
npm --prefix frontend audit --audit-level=high
```

The current frontend uses email/password login. Upload, review queue, and records pages also send the logged-in user's email to the backend for current local RBAC checks.

## Api endpoints
You can check api documentation at:
http://localhost:8080/docs
