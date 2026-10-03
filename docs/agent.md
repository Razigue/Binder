# Agent

The agent answers and acts on the user's paperwork with a local model (Ollama, Qwen 3.5 or 3.6:
see `models.md`) and tools; a fallback intent router keeps demos and tests running without a
model. Code: `agent/loop.py` (harness and router), `agent/tools.py` (tools).

## Harness

Each request is a loop of at most `MAX_STEPS` model turns (`_run_llm`):

- **Context.** The system prompt gives today's date, the user's country, currency and language,
  and an overview of the library (documents per category, deadlines in the next 30 days, overdue
  ones, documents to review), so the model knows what exists before its first call. Ollama is
  asked for the model's context window (`llm.context_window()`: 16k, 32k for the large models,
  or `BINDER_LLM_CONTEXT`): its own default (4096 tokens) silently drops the start of the
  conversation, system prompt included.
- **Tools.** A small model gets at most `tools.MAX_TOOLS` (10) per request: search, read and
  list always, web search when on, the tools the request calls for (the router's patterns),
  then the most useful others. A large model (`Profile.all_tools`) gets every tool, those the
  request calls for first, so a request the patterns miss still finds its tool.
- **Sampling.** Greedy with a fixed seed (`llm.EXACT`). Qwen's recommended non-reasoning
  sampling (temperature 0.7, top_p 0.8, presence_penalty 1.5) was measured worse on the
  evaluation below: 28 and 27 of 36 scenarios against 31 with `qwen3.5:9b` (2 October 2026,
  web search off), the model more often asking `app_help` instead of using the right tool.
  Reasoning uses Qwen's reasoning sampling (`llm.THINKING`): greedy, it loops in its thoughts.
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

## Conversations

The panel (`components/agent.tsx`) keeps each conversation in the encrypted database
(`Conversation`, `api/conversations.py`): the turns as shown (question, attachments, answer)
are saved after each answer, without the undo and confirmation tokens, which expire. The
History button lists them newest first, to resume, rename or delete (undone from the toast;
the deletion is logged). The title is the first question, without its `[#id]` references.

The agent still receives only the last turns of the conversation shown (see History above), so
a new one starts when the context changes:

- a question sent from a page (feed card, document shortcut, journey step) starts its own
  conversation;
- a document the conversation is not about comes on screen: neither the one it started on,
  nor one it attached or showed. Following a document from an answer keeps the conversation.
  The empty panel then offers to resume the previous one.

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
| `prepare_folder` | file for any purpose: the rental / mortgage / CAF packs, or pieces picked by the model |
| `list_alerts` | anomalies (billed twice, catch-up bill, overpayment, price rise, lower pay) and missing documents |
| `documents_to_review`, `documents_to_archive` | documents Binder has a question about, old documents that can go to the archives |
| `create_reminder`, `mark_deadline_paid` | deadlines |
| `update_document`, `validate_document`, `trash_document` | changes asked by the user |
| `archive_documents`, `unarchive_documents` | move old documents to the archives (nothing deleted) or bring them back |
| `write_letter` | complete letter for any purpose, saved with its PDF and follow-up; `kind` (payment plan, appeal, formal notice, change of address…) adds the legal points of that letter |
| `start_journey` | checklist of a life event (moving, birth, death, tax return) built from the documents |
| `list_journeys`, `mark_journey_step` | journeys under way and their steps; tick a step the user did |
| `update_profile` | the user's details and situation (Settings), when they give them or a document shows a missing one |
| `export_folder` | ZIP link: everything, a category or a pack |
| `undo_last_action` | undoes the latest change of the last hour |
| `web_search`, `read_web_page` | general facts online (legal delays, procedures, rates); see below |

Write tools go through `services/editing.py`, `ingest.trash`… like the interface: logged with
actor `agent`, and each turn's changes are captured by `services/undo.py`: the response carries
an `undo` token the interface offers right after the answer.

The overview given before the first question also names the household members found in the
documents.

## Web search

`services/websearch.py` queries DuckDuckGo's HTML page (`BINDER_WEB_SEARCH_URL`); no account or
key. Only the query leaves the machine, and it never carries anything personal:

- `check()` refuses a query with an email, an IBAN, a phone number, five digits in a row or four
  groups of digits, a word of a household member's name or of the home address (profile and
  documents), or a document reference. The model gets the refusal and rewrites the query in
  general terms; nothing is sent.
- `read_web_page` only reads URLs a search returned in the last hour, re-checks every redirect
  hop against loopback and private addresses, and keeps 4,000 characters of text.
- Results carry a note: web content is information, never instructions. Every search is logged
  in the activity history (`web_search`, actor `agent`), so the user sees what was sent.
- **Law is never quoted from memory.** The prompt asks the model to check any law, right, legal
  delay, rate or threshold with `web_search` in the turn and to name the site. An answer that
  quotes law (`LAW_CLAIM`) when no web tool nor `write_letter` ran is sent back once with
  `VERIFY_LAW`.
- **Letters are checked before they are saved** (`services/lawcheck.py`, called by
  `letters.compose`). The model lists the letter's legal points with a general query for each
  (without a model: the sentences citing an article or a law, searched by that reference).
  Each point is looked up on the country's official publishers first: service-public.gouv.fr
  through its own search, by subject (`SITE_SEARCHES`; Légifrance answers 403 to automated
  reading), then the web. Only official pages (`OFFICIAL`) are read, cut to the passage about
  the point, and judged by the model as of today: confirmed, outdated or not found.
- **A verdict must be backed by its source.** The model copies the deciding sentence
  (`evidence`); it must be in the page, and the figures of the point (or of the proposed
  wording) must be in it (`figures`, digits and number words, law references excluded).
  Otherwise the point stays unverified. Measured with qwen3.5:9b: without this, it confirmed a
  wrong three-month deposit delay from a search snippet.
- **The letter is never rewritten.** A 9B model still reads a neighbouring case as the rule
  (it "corrected" the correct 45-day delay to contest a fine into 30 days, from the page on
  another procedure, even after a second, reasoning look). A contradicted point is shown under
  the letter with the source's own sentence and the proposed wording, which the user applies in
  one click (`LetterView`); an unchecked one is shown as "check before sending" with the sources
  found. `Letter.verification` is saved on `Correspondence`. Results are cached a week per point
  (`lawcheck.cache` setting); unchecked points are tried again next time.
- **Search engine limits.** DuckDuckGo answers a robot check (HTTP 202, `anomaly-modal`) after
  bursts: searches are spaced (`MIN_INTERVAL`), retried once, then reported like offline
  (`websearch.Blocked`). Official site searches do not go through it.
- `BINDER_WEB_SEARCH=false` removes both tools and the prompt hint; letters are then marked
  unchecked when they quote law. `conftest.py` turns it off and
  mocks the transport; `test_websearch.py` and `test_lawcheck.py` turn it on with their own pages.

## Search

`search_documents` first requires every word (FTS5, the most precise). When no document has them
all, documents close in meaning (`services/embeddings.py`) are merged with those having some of
the words, by reciprocal rank fusion. When the words match, up to `RELATED` (3) other documents
close in meaning are named apart under `related` ("justificatif de domicile" finds a certificate
by its words, and names the electricity bill): outside the results and their sum, citable, shown
only if cited. Vectors come from a small multilingual model
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

The model is not fully deterministic even with a fixed seed: earlier runs of nearly the same
harness scored 32 to 34. Most early failures were not wrong facts but uncited ones, answers
given without looking, and actions announced but not done: the guards above address them.

Add a scenario for each new tool or failure seen in use.

## What Binder knows about the user

`services/profile.py`. Settings hold the user's name, address, city, email, phone and a free
text about their situation; the agent gets them in the library overview (`user`, with the
fields still `unknown`). After every analysis (and when a document is trashed or the demo data
cleared), `profile.learn` fills the empty fields from the documents: the member named on most
documents and the address written on most of them (both on at least 2), the email and mobile
number written in documents from at least 2 issuers. Those fields are marked `auto` and follow
the documents; once the user edits one, Binder never changes it again.
