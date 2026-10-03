# AGENTS.md

Binder: local, encrypted AI administrative agent. Product: `PRODUCT.md`. UI rules: `DESIGN.md`.
User guide: `README.md`. Dev setup, env vars, releases: `docs/`. Read those instead of re-deriving
them; document new dev topics in `docs/*.md`, keep `README.md` user-facing.

## Layout

```
backend/src/binder/   Python 3.12, FastAPI, SQLModel on SQLCipher
  api/                  REST API (`/api`): one router per domain, aggregated by routes.py;
                        common.py (SessionDep, get_or_404, disposition); scan.py phone scan
  services/             ingest pipeline, rules, llm (Ollama), deadlines, folders, letters, ...
  agent/                tools.py + loop.py (LLM tool calling, or intent router without a model)
  i18n.py               locale detection, EN/FR catalogs, money/date formatting
  guard.py              Host/origin checks, session token, CSP
  security.py           master key, SQLCipher + Fernet
  db.py                 engine, additive schema migration, FTS5 index
  mobile/               standalone phone scan page (plain HTML/CSS/JS)
  static/               built UI (generated, gitignored)
backend/tests/        pytest; backend/scripts/evaluate.py rule accuracy
frontend/src/         React 19, TS, Vite, Tailwind v4, shadcn/ui, TanStack Query
  pages/ components/ hooks/queries.ts lib/api.ts i18n/messages/
packaging/            PyInstaller build (build.py), desktop entry
```

## Commands

```bash
cd backend && uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run python scripts/evaluate.py
uv run binder            # http://127.0.0.1:8765 (add --seed for demo data)
cd frontend && npm ci && npm run lint && npm run build   # build outputs to backend static/
npm run dev              # :5173, proxies /api to :8765
```

CI runs all of the above on Linux, Windows and macOS: keep code cross-platform (`pathlib`, no
shell-specific calls, UTF-8 I/O).

`main` is only fed by pull requests, and each merged PR is a release: `tag.yml` tags the merge
commit (patch bump; PR label `minor` or `major` for more, `no-release` for none) and the tag builds
and publishes the GitHub release (`docs/release.md`). Label the PR before merging it.

## Rules

- **Local only.** Never add network calls that send document data off the machine. Ollama
  (`localhost`), the update check, the first-run download of Ollama and its models, and the
  agent's web search (`services/websearch.py`: general queries only, personal data refused) are
  the only outbound traffic.
- **AI first; rules for the demo only.** Binder is an AI agent: the local model reads, files and
  acts. The rules path and intent router exist only so the demo documents (`samples.py`) and the
  tests run without a model (`BINDER_LLM_ENABLED=false`, a modest machine for a presentation);
  never present them as a feature. With the model enabled but not ready, real documents wait
  (`waiting`) and are read once it is. A feature needs a rules path that works on the demo
  data, not on real documents: do not grow the rules to generalise, improve the model path.
- **Nothing is deleted silently.** Use the trash, `superseded_by` or the review queue; log actions
  through `services/activity.py`.
- **Encryption.** Files go through `security.py`; never write plaintext documents to disk.
- **Security middleware.** Do not loosen `guard.py` (Host, same-origin, token, CSP) or bind the
  main server beyond loopback.
- **Schema.** Changes to `models.py` must stay additive so `db.migrate` handles them.
- **i18n.** No hard-coded user-facing strings. Frontend: add EN+FR keys in
  `src/i18n/messages/<namespace>.ts` (`defineMessages` enforces parity; plurals `key_one`/
  `key_other`). Backend: `i18n.catalog(...)`. Letters to FR/BE/LU/MC administrations stay French.
- **Typing.** mypy strict, ruff line length 100; TS strict, oxlint.
- **Tests.** Add pytest coverage for backend changes; fixtures in `tests/conftest.py` isolate data
  dir, disable LLM and auto-import, and pin locale `en_US`; samples are built for a fixed `TODAY`.
- **UI.** Follow `DESIGN.md`; reuse `components/ui/*`, `PageHeader`, `CategoryIcon`, query hooks
  in `hooks/queries.ts`, API types in `lib/api.ts`.

## Conventions

- Code, comments, docstrings and docs: English. Comments explain why, briefly.
- Commit messages: French, short summary line (`Domaine : changement`, e.g.
  `Aide : courriers types préremplis`).
