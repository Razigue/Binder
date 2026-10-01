# Agent

The agent answers and acts on the user's paperwork with a local model (Ollama, Qwen 3.5) and
tools; a fallback intent router keeps demos and tests running without a model. Code: `agent/loop.py`
(harness and router), `agent/tools.py` (tools).

## Harness

Each request is a loop of at most `MAX_STEPS` model turns (`_run_llm`):

- **Context.** The system prompt gives today's date, the user's country, currency and language,
  and an overview of the library (documents per category, deadlines in the next 30 days, overdue
  ones, documents to review), so the model knows what exists before its first call. Ollama is
  asked for a `BINDER_LLM_CONTEXT` window (16k): its own default (4096 tokens) silently drops the
  start of the conversation, system prompt included.
- **History.** The last turns are sent with the ids and titles of the documents each answer
  showed, so "and when is it debited?" refers to a known id; those documents stay citable.
- **Guards.**
  - An answer given before any tool call is discarded once, with a request to look first: small
    models otherwise invent documents.
  - An answer announcing an action ("I'll move it to the trash", "let me check") without the
    tool call is sent back once; so is an answer handing the request back to the user ("could
    you tell me the amount?") when nothing was done.
  - Arguments are checked and converted against the tool's signature (`tools.call`): "3" for 3,
    unknown arguments dropped, errors returned to the model so it can correct itself. Invalid
    JSON gets the same treatment.
  - The same call with the same arguments gets its result again with a note to answer.
  - Out of steps, a last turn without tools forces an answer.
- **Citations.** Facts are cited `[#id]`. "(ID #12)" or "document #6" are rewritten when they name
  a document returned by the tools; citations of other ids are removed. An answer without any
  citation gets one for each document of the turn it names unambiguously: by its title,
  reference or amount, when no other document of the turn shares it.
- **Streaming.** `POST /api/agent/chat/stream` sends newline-delimited JSON: `tool` events as
  tools start, `token` events as the answer is written, `step` to discard a preamble, then `done`
  with the full response (or `error`). The interface shows the steps live. Closing the request
  stops the agent at its next step.
- **Vision.** With a model that reads images (`/api/show` capabilities), `view_document` sends a
  page as an image in the tool result.
- `BINDER_LLM_THINK=true` lets the model reason before each step: slower, and no better on the
  evaluation (see below).

## Tools

| Tool | Purpose |
|---|---|
| `search_documents` | full-text + semantic search, passages where the words appear, sum of amounts |
| `read_document` | fields, retention, text by pages, or only the passages about a query |
| `view_document` | a page as an image (vision models only) |
| `explain_document` | plain-language explanation and actions |
| `list_deadlines` | unpaid deadlines of a period, overdue ones, total |
| `list_expirations` | every document with an end of validity and its state |
| `list_subscriptions` | recurring bills, yearly cost, price increases |
| `check_folder` | rental / mortgage / CAF application pack |
| `documents_to_review`, `documents_to_sort_out` | review queue, documents that can go |
| `create_reminder`, `mark_deadline_paid` | deadlines |
| `update_document`, `validate_document`, `trash_document` | changes asked by the user |
| `draft_letter` | termination, complaint or request letter, shown ready to copy |
| `export_folder` | ZIP link: everything, a category or a pack |

Write tools go through `services/editing.py`, `ingest.trash`… like the interface: logged with
actor `agent`, reversible (trash, reopened deadline, old values in the activity log).

## Search

`search_documents` first requires every word (FTS5, the most precise). When no document has them
all, documents close in meaning (`services/embeddings.py`) are merged with those having some of
the words, by reciprocal rank fusion. Vectors come from a small multilingual model
(`BINDER_EMBED_MODEL`, Qwen3 Embedding 0.6B, offered in Settings), computed at import, after a
correction, and for existing documents on first search; they live in the encrypted database
(`Embedding` table). A document counts as related above a cosine similarity of 0.42 and within
0.08 of the best match (calibrated on the demo documents: unrelated questions score below 0.37).

## Evaluation

```bash
cd backend
uv run python scripts/evaluate_agent.py            # configured model
uv run python scripts/evaluate_agent.py --rules    # router without a model
uv run python scripts/evaluate_agent.py -k rappel -v   # some scenarios, answers shown
uv run python scripts/evaluate_agent.py --think --model qwen3.5:27b
```

34 scenarios in French and English on the demo documents plus a photographed water bill: facts
in fields and in the text, sums over several documents, advice, packs, subscriptions, actions
(checked in the database), a letter, a follow-up question, a scan, and a question about a
document that does not exist. Each scenario starts from a fresh copy of the library.

Results on 1 October 2026 (RTX 4080 SUPER, `qwen3.5:9b`):

| Engine | Passed | Time per request |
|---|---|---|
| Router without a model, previous router | 8/34 | instant |
| Router without a model | 16/34 | instant |
| Model, new tools without the guards and citation repair | 15/34 | 7.5 s |
| Model, current harness (two consecutive runs) | 34/34, 34/34 | 10.3 s |
| Model, current harness, `BINDER_LLM_THINK=true` | 31/34 | 12.6 s |

The model is not fully deterministic even at temperature 0: earlier runs of nearly the same
harness scored 32 to 34. Most early failures were not wrong facts but uncited ones, answers
given without looking, and actions announced but not done: the guards above address them.

Add a scenario for each new tool or failure seen in use.
