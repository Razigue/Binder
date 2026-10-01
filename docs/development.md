# Development

## Architecture

```
backend/   Python 3.12, FastAPI, SQLModel on SQLCipher, PyMuPDF, Ollama
  src/binder/
    i18n.py              system locale, EN/FR message catalogs, money and date formatting
    services/text.py     PDF reading (PyMuPDF), OCR of scans (RapidOCR), page images for vision
    services/rules.py    rule-based filing and extraction
    services/llm.py      Ollama client: JSON extraction, tool calls, streaming, vision
    services/embeddings.py  semantic search (local embedding model, vectors in the database)
    services/ingest.py   pipeline: encrypted storage → reading → extraction → deadlines → index
    services/feed.py     Today feed: cards and their one-tap actions (questions.py, anomalies.py,
                         missing.py, reports.py, briefing.py, letters.py feed it)
    services/undo.py     undo steps captured around every change
    services/learning.py corrections applied again to the next documents of a sender
    services/areas.py, household.py   life areas, household members and address
    services/setup.py, backup.py, notify.py, background.py   AI setup, backups, notifications,
                         background scheduler
    agent/               tools + home-made agent loop (see agent.md)
    api/routes.py        REST API; api/assistant.py feed, actions, undo, reports, areas, letters
frontend/  React, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query
```

Extraction is done by the local model (Qwen), document type included; deterministic rules fill its
gaps. Without a model (`BINDER_LLM_ENABLED=false`), rules and an intent router run the demo
documents and the tests: they are tuned on `samples.py` only and are not a user-facing feature.
With the model enabled but not ready, real documents are stored with the status `waiting` and
read by the background loop once it is (`ingest.analyze_waiting`).

Guided journeys (`services/journeys.py`, `api/journeys.py`): moving, birth, death, tax return.
Steps are computed on every read from the event date and the documents (organisations to tell,
receipts and their total, contracts of the relative); only the date, the details given and the
ticked steps are stored (`Journey`). A step with a letter ticks itself once that letter is sent.

Language preferences are stored in the encrypted database and exposed at `GET`/`PUT
/api/preferences` (the response also gives the effective language, country and currency, and what
the system reports).

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and Node 20 or later. Binder runs its own Ollama
(downloaded at first launch, see [configuration](configuration.md#local-ai-setup)); to use one you
run yourself, set `BINDER_OLLAMA_URL=http://localhost:11434`. The tests need neither.

```bash
# Interface (built into backend/src/binder/static)
cd frontend && npm install && npm run build

# Server
cd ../backend && uv sync
uv run binder --seed      # optional: demo documents
uv run binder             # http://127.0.0.1:8765
uv run --extra desktop binder --desktop   # native window (pywebview)
```

In development: `uv run binder` on one side, `npm run dev` on the other (http://localhost:5173,
`/api` calls are proxied to the backend).

Desktop title bar on Windows: the window keeps its native frame, `binder/winframe.py` folds the
caption into the client area (WM_NCCALCSIZE) and `components/layout/TitleBar.tsx` draws the bar,
handing dragging, the window buttons and Snap Layouts back to Windows. Do not switch to
pywebview's `frameless` mode or drag region: they lose Aero Snap. The top edge does not resize
the window (the web view covers it).

Settings and OCR: see [configuration.md](configuration.md). Desktop builds and releases: see
[release.md](release.md).

## Quality

```bash
cd backend
uv run pytest               # API, encryption at rest, extraction, agent, i18n
uv run ruff check . && uv run mypy src
uv run python scripts/evaluate.py          # demo documents, rules
uv run python scripts/evaluate.py --llm    # demo documents, local model + rules
uv run python scripts/evaluate.py --corpus DIR   # real annotated documents (evaluation.md)
uv run python scripts/evaluate_agent.py    # agent on 34 realistic requests (see agent.md)
```

The demo set is 21 fictitious documents (`binder/samples.py`); the rules are tuned on them, so
their score says nothing about real documents. Real documents are measured with `--corpus`, on a
folder kept outside the repository: see [evaluation.md](evaluation.md).

## Roadmap

- Evaluation set of 100 documents, comparison of local models and APIs
- Signed installers for Windows (MSI) and macOS (notarised DMG)
- Key protected by the system keychain or a passphrase
