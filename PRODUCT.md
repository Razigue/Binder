# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

React UI served by a local FastAPI server; shipped as a desktop app (pywebview, Linux/Windows/macOS)
or opened in a browser. A separate minimal phone page (`backend/src/binder/mobile/`) scans pages by
camera over the LAN.

## Users

A private individual handling a household's paperwork, mostly in France (taxes, energy, insurance,
bank, housing, health, CAF, payslips, telecom, ID, vehicle). Not an admin expert, sometimes stressed
by letters, unwilling to put documents in a cloud. Job: drop paperwork in, trust it is filed, be told
what needs attention, by when, and what to do.

## Product Purpose

AI administrative agent, 100% local: a local model reads, files and extracts every document
(amount/dates/reference/issuer), tracks deadlines and expiry, explains letters plainly, answers
questions citing sources and acts on request (reminders, letters, folders, trash). Success:
nothing urgent missed, everything findable, actions trustworthy because checkable.

## Positioning

An AI agent for your paperwork, not a filing cabinet: it installs itself, surfaces today's
priorities, spots anomalies and missing documents, writes complete letters and follows them up,
prepares any file, and does what you ask in plain words. The AI is the product,
and it runs locally (Ollama + Qwen, SQLCipher DB, Fernet files). The rules path and intent router
only keep demos and tests running without a model: never sell them as a feature.

## Capabilities and Constraints

Features: see README.md (user guide); configuration: docs/configuration.md. Product-level constraints:
- French admin reality: service-public.fr retention, CAF, ID renewal windows. Letters to
  French-speaking administrations (FR, BE, LU, MC) are always in French.
- UI in English and French, following the OS locale and theme; no settings beyond the mailbox.
- Navigation: Today plus six life areas (Housing, Money, Work & benefits, Health, Identity,
  Vehicle); the agent is one bar away on every page.
- Loopback-only server; phone scan opens a temporary token-protected HTTPS server only during a
  session. Losing `DATA_DIR/key` loses the data unless a backup and its recovery code exist.
  Builds are not code-signed yet.

## Brand Commitments

- Name **Binder**; mark: `BookLock` icon in a navy square.
- Voice: plain, calm, second person ("Here's what needs your attention today.", "Nothing urgent.
  Everything is in order."). Privacy restated where it matters ("They stay on your computer.").
- A green-dot "Local" badge in every page header.

## Evidence on Hand

12 fictitious demo documents (`backend/src/binder/samples.py`, `binder --seed`); `scripts/evaluate.py`
scores rules on those same documents (not generalisation). No users, testimonials, benchmarks or
pricing exist: never invent them.

## Product Principles

1. **Local by construction.** Nothing leaves the machine.
2. **The agent does the work.** The local model reads, files, explains and acts; the user checks
   and confirms.
3. **Never destroy silently.** Flag, trash, suggest; every action can be undone right after; the
   user confirms anything irreversible.
4. **Show the source.** Cite the document, highlight where each figure was read; when unsure,
   ask one question with one-tap answers.
5. **Say what to do and by when.** Next action in plain words, not raw data.

## Accessibility & Inclusion

Plain language for non-experts; locale-formatted dates and amounts; urgency never by colour alone
(always a text label: "Due in 3 days", "Expired").
