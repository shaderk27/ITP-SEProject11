# Lab Budget Monitoring System

## Database setup
Copy `.env.example` to `.env` and replace `<PASSWORD>` with your local Postgres password:

```powershell
Copy-Item .env.example .env
```

The backend automatically reads `.env` from the repo root. Real `.env` files are ignored by Git.
Login cookies stay valid for `ACCESS_TOKEN_EXPIRE_MINUTES`; restarting the frontend does not clear browser cookies.

### Which SQL file to run, and when

`db_setup.sql`, `migrate_lab_ic_to_assignments.sql` and `add_rag_knowledge.sql` live in `backend/migrations/`. `dev_seed.sql` and `w7_auth_seed.sql` live in `backend/seeds/`.

| File | What it does | When to run it |
|---|---|---|
| `db_setup.sql` | **Destructive.** Drops and recreates every table with the current schema (including `lab_ic_assignments`, `users.is_active` and `password_reset_tokens`). Creates no data. | A brand-new database, or when you want to wipe everything and start over. **Never** on a database whose data you want to keep. |
| `migrate_lab_ic_to_assignments.sql` | Non-destructive, safe to re-run. Converts the old Lab IC model (`users.lab_id` or `labs.user_id`) into `lab_ic_assignments`, keeping existing data. | Only on an **existing** database created before `lab_ic_assignments` existed. Not needed after a fresh `db_setup.sql`. Do not also run the older `migrate_lab_ic_to_labs.sql`. |
| `dev_seed.sql` | Safe to re-run. Adds schema columns the app needs that `db_setup.sql` does not create (`pr_status` on purchase requests and lines, the alert-notification flags on `labs` and `lab_groups`, and nullable `labs.lab_group_id`). Also seeds roles, the FY2026 budget period, spending categories, lab groups, labs and three test users. | After `db_setup.sql` or the migration, on every database you set up, including fresh ones. Despite the name, it contains schema changes, so skipping it leaves the app with missing columns. |
| `w7_auth_seed.sql` | Safe to re-run. Adds demo users with Lab IC assignments for testing Lab IC scoping. Reuses the same lab groups and labs as `dev_seed.sql`. | Optional, after `dev_seed.sql`, and only once `lab_ic_assignments` exists. |
| `add_rag_knowledge.sql` | Non-destructive, safe to re-run. Turns on the `pgvector` extension and creates the empty `knowledge_documents` and `knowledge_chunks` tables used by Ask AI's purchase search. Touches no existing data. | Optional. Only if you want Ask AI's purchase search (see [Purchase search (RAG)](#purchase-search-rag)). Needs the pgvector **Postgres extension** installed on your Postgres server first. This is not the pip package. Re-run it after every `db_setup.sql`, because a reset drops these tables. |

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
5. Optionally run `add_rag_knowledge.sql` for Ask AI's purchase search.

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

### Purchase search (RAG)

**What it does.** On top of the budget figures, Ask AI can search committed purchase request (PR) lines by meaning, not just by matching words. A question like "did we buy anything for 3D printing?" can find a line described as "PLA filament spools", even though no words match. Relevant lines are passed to the AI as evidence. The answer cites them as `[PR 4500012345 line 2]`, and they're listed under **Sources** in the widget.

How it works:

- Each committed PR line gets a short text card (item, lab, category, purpose, date, amount, status) plus an *embedding*, which is a list of numbers that represents what the text means. Cards are stored in `knowledge_chunks` using the `pgvector` Postgres extension.
- When someone asks a question, the question is embedded the same way, and the closest cards are found.
- **Role scope is applied in SQL before the search ranks anything**, using the same rules as the rest of the chatbot. A Lab IC only ever gets lines from their assigned labs, and a Team Lead only gets their lab group. Assignment changes apply on the next question.
- Only approved lines are searched, and lines that aren't close enough to the question are dropped. So an unrelated question gets "no matching purchases" rather than random lines.
- Totals, rankings and utilisation **always** come from the SQL budget figures, never from the search.

**It's off by default and optional.** With `EMBEDDING_PROVIDER` blank, nothing changes: Ask AI answers from the budget figures exactly as before, and batch commits skip indexing. You only need the steps below if you want to use or test purchase search.

**Two different things are both called "pgvector":**

| | pgvector **Python package** | pgvector **Postgres extension** |
|---|---|---|
| What it is | A small library that lets the backend code describe a `vector` column | An add-on installed into your Postgres database server that stores and searches vectors |
| Install | `pip`, as part of `backend/requirements.txt`. It's pure Python, so it's the same on every OS with nothing to compile | `brew` on macOS, a Visual Studio build on Windows, or `apt` on Linux (step 1 below) |
| Who needs it | **Everyone**, even with purchase search off | **Only** people turning purchase search on |

**After pulling this change, everyone** must reinstall the backend requirements. That installs the pgvector **Python package**, which the backend needs just to start, because it loads the `knowledge_chunks` table definition at startup. You do **not** need the Postgres extension for this:

```powershell
python -m pip install -r backend/requirements.txt
```

The backend only touches the RAG tables when `EMBEDDING_PROVIDER` is set, so a database without the extension or the tables works fine while purchase search is off.

**Turning purchase search on locally (on your own machine)**

Recommended for anyone working on Ask AI, the review/commit flow or the PR-line tables. Without it, Ask AI skips purchase search, and the purchase-search database tests are skipped instead of run.

1. Install the pgvector **Postgres extension** on your Postgres server (once per machine):
   - macOS (Homebrew Postgres): `brew install pgvector`
   - Windows: follow the Windows steps in the [pgvector README](https://github.com/pgvector/pgvector#windows). It's built with the Visual Studio C++ build tools, then copied into your PostgreSQL install folder.
   - Linux: `sudo apt install postgresql-<major version>-pgvector`
2. Create the RAG tables. This is non-destructive and safe on a database with data:
   ```powershell
   psql "$env:DATABASE_URL" -f backend/migrations/add_rag_knowledge.sql
   ```
   If it fails with `extension "vector" is not available`, step 1 didn't install into the Postgres server you're connecting to.
3. Install the free local embedding model's package:
   ```powershell
   python -m pip install -r backend/requirements-dev.txt
   ```
4. Add these lines to the root `.env`:
   ```text
   EMBEDDING_PROVIDER=local
   EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
   ```
5. Restart the backend, then build cards for the PR lines already in your database. The first run downloads the model, about 70 MB, once. It takes about 15 seconds per ~1,700 lines:
   ```powershell
   $env:PYTHONPATH="backend"
   python -m app.scripts.index_knowledge
   ```
   From then on, every batch commit indexes its own lines automatically in the background.

**Embedding settings** (root `.env`, backend only)

| Variable | Required | What it does |
|---|---|---|
| `EMBEDDING_PROVIDER` | To turn search on | `local` runs a free model inside the backend (needs `fastembed`, from `requirements-dev.txt`). `api` calls any OpenAI-compatible `/embeddings` API. Blank turns search off. |
| `EMBEDDING_MODEL` | No | Defaults to `BAAI/bge-small-en-v1.5` for `local` and `text-embedding-3-small` for `api`. |
| `EMBEDDING_API_KEY` | For `api` | The provider's key. Not used by `local`. |
| `EMBEDDING_BASE_URL` | No | For `api` only. Defaults to OpenAI (`https://api.openai.com/v1`). |
| `EMBEDDING_MAX_DISTANCE` | No | How close a line must be to count as relevant (cosine distance; lower is stricter). Defaults to `0.35` for `BAAI/bge-small-en-v1.5`. Other models have no default, so set it yourself when you switch (see below). |

**When to re-run the indexing script** (`python -m app.scripts.index_knowledge`)

It's safe to run any time, because unchanged lines are skipped.

- After `db_setup.sql` + `add_rag_knowledge.sql` and loading data, since a reset drops the cards.
- After changing `EMBEDDING_PROVIDER` or `EMBEDDING_MODEL`. Cards from different models can't be compared, so each model needs its own.
- After renaming labs or categories, so the card text is up to date. Who can see which lines is always worked out live and doesn't need this.
- If a commit happened while purchase search was off or the model failed to load. The backend log shows `PR-line indexing skipped` or `failed`.

**Tuning the relevance cutoff.** The `0.35` default was measured on the synthetic test data. To check it against real data or a new model, compare distances for questions that should match and questions that shouldn't:

```powershell
$env:PYTHONPATH="backend"
python -m app.scripts.probe_knowledge "calibration equipment" "glassware" "hello" "which lab spent the most?"
```

Set `EMBEDDING_MAX_DISTANCE` between the two groups' best distances.

**If something goes wrong, Ask AI still answers.** If purchase search is on but fails (model can't load, provider down, or `add_rag_knowledge.sql` not run), Ask AI answers from the budget figures alone. The label under the answer then ends with `Purchase search is unavailable right now; this answer uses budget figures only.`

**Deployment.** Every deploy needs `pip install -r backend/requirements.txt`, for the pgvector Python package. To turn purchase search on there as well, the server's Postgres also needs the pgvector **Postgres extension**, and `add_rag_knowledge.sql` run through the team's non-destructive schema-update path. Never get it by running `db_setup.sql` on Lightsail. Until then, leave `EMBEDDING_PROVIDER` blank there.

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
