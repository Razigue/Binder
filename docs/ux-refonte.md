# UX overhaul (refonte UX)

Tracking file of the UX overhaul: what is done, the decisions taken where the brief left a
choice, and what is left. One commit per step.

## Steps

| # | Step | State |
|---|------|-------|
| 1 | Archives + Archives tab | done |
| 2 | Questions (filter, grouping, cap, panel with the document) | done |
| 3 | Navigation and To do | done |
| 4 | My papers | done |
| 5 | Life events (Démarches) | done |
| 6 | First launch | done |
| 7 | Glossary and accessibility | done |

## Decisions

### Step 1: archives

- **Columns**: `Document.archived_at` and `Document.archive_reason` (`retention`, `replaced`,
  `user`), added by `db.migrate` like any new column. `db.in_use()` is the filter of every
  active view (neither trashed nor archived).
- **What leaves the active views**: feed cards, deadlines (`deadlines.sync` drops them, so
  calendars and alerts follow), expirations, anomalies, missing documents, subscriptions,
  briefing, files (`folders.current_documents`), questions, stats and the agent's listings.
  **Kept**: document page, file download, preview, export ZIP (archives are still the user's
  papers), duplicate detection and version series (a re-scan of an archived paper is still a
  duplicate), and the web-search privacy guard (archived references stay personal data).
- **Search**: `GET /api/documents?archived=true` and the agent's `search_documents(archived)`
  search the archives only; the default search skips them.
- **Archived at import**: only when retention says so on the first reading, and never a
  document the user took back out of the archives (an `unarchive` entry in its activity).
  A document that becomes "replaced" because a newer version arrives is suggested, not
  archived on its own.
- **Undo**: two new undo steps (`archive`, `unarchive`); every route and the feed action run
  inside an undo capture.
- **Agent**: `archive_documents` and `unarchive_documents`; `list` kind `to_archive` replaces
  `to_sort_out`. `archive_documents` is guarded like the trash: after reading content it waits
  for the user's confirmation (an injected "archive these" would hide deadlines).
- **API renames**: `deletable_reason` → `archivable_reason`, `POST /retention/trash` →
  `POST /retention/archive` (returns a `BulkResult`). The "Keep forever" icon became a pin
  (the archive box now means archiving).
- **Archives tab**: on the Documents page for now; it moves to My papers in step 4.

### Step 2: questions

- **Thresholds** (`services/relevance.py`, named constants): old = issued more than 730 days
  ago with no date in the future, or a payment date passed for more than 90 days, or replaced,
  or past its retention period. A missing field is asked only when it has an effect: the
  amount when a payment is due within 90 days (or unpaid for less than 90 days) or the bill is
  a recent recurring one (energy, telecom, insurance, housing: "a bill still followed"); the
  payment date on a document of the last 90 days; the end date of an identity document,
  insurance, vehicle paper or contract. The issue date, reference, sender and person are never
  asked. Journeys and letters under way are not looked up for this (the document fields
  decide alone): simpler, and those flows ask their own questions.
- **Filed as it is**: a document with nothing worth asking is `classified` straight away; its
  missing fields stay in `missing_fields` and show as "not filled in". The decision is taken
  in `ingest.refresh_status`, so a correction re-evaluates it; `question_for` also re-checks
  the age on every read, so a question disappears once the document gets old.
- **Second reading** (model only): when the model's reading has doubts on fields, it reads the
  document again, from the page image if the first reading was the text (and the other way
  round); a value read the same way twice is no longer a doubt. A document it could not place
  goes where the other documents of the same sender are, when they all agree. Without a model
  nothing is read again (the rules have nothing new to say).
- **Grouping**: same question kind and same sender, from 2 documents. An "where does it go"
  group proposes the area of the sender's other documents when they agree ("These 3 documents
  from Free go in Housing?" Yes / See one by one), otherwise the area buttons. Field groups
  offer "See one by one" and "No amount" (etc.) for all. A grouped duplicate question only
  removes the copies, never an original.
- **Cap**: 3 question cards in the feed, most useful first (payment soon, then documents in
  force, then duplicates, then the rest), and a "N more questions, whenever you like" card
  that opens the sorting session (`GET /api/questions`).
- **Panel**: every question card opens the panel (its "See the document" button, "Open",
  "See one by one"); `GET /api/questions?documents=…` gives one question per document.
  `DocumentPage` is the document page with the read places outlined; the document page's own
  preview was left as it is (that file holds uncommitted changes of yours: the two will be
  merged when they are committed).
- **Import report**: unchanged summary ("19 documents filed · 2 questions…"), with fewer
  questions; on the demo, 2 questions (garage quote, an EDF bill without a payment date).

### Step 3: navigation and To do

- **Routes**: `/` To do, `/papers` My papers, `/procedures` Life events ("Démarches"; English
  label "Life events": every entry is a situation). `/area/:area` redirects to
  `/papers?area=…`, `/prepare` to `/procedures`, `/documents` to `/papers`; `/documents/:id`
  (the document page, used by the activity log, the agent's citations and the feed) is
  unchanged.
- **Ask bar removed**: the agent opens from ＋ (on every page) or Ctrl K. Fewer things on screen;
  the brief makes Ctrl K a shortcut, not the only path, and ＋ is that path.
- **＋ menu**: phone scan first and highlighted (the quickest way for a paper letter), then
  "Choose a file", then "Ask a question". Drag and drop anywhere still works.
- **To do**: the feed's cards, one card each, import report first, then urgent, soon, for
  information (stable order within a tone). The weekly briefing card is not shown (it repeats
  the cards); the timeline and "Coming up" moved out (Calendar tab of My papers, step 4); "In
  progress" lives in Life events. The count in the menu is the number of cards that are not
  merely for information.
- **Temporary**: until steps 4 and 5, `/papers` shows the former Documents page (with the
  `?area=` filter) and `/procedures` the former Prepare page.
- **Your local changes**: `AppLayout.tsx` keeps your `useLiveChanges` import on its own line,
  so that your uncommitted change stays separate from these commits.

### Step 4: My papers

- **Tiles**: `GET /api/areas` now gives each area a `state` sentence and a `tone`: the most
  pressing card of that area (a payment says its date, "+N more" when there are others), else
  an end of validity within 180 days ("Passport expires in 4 months"), else "Up to date", or
  "Nothing here yet". Questions never show on a tile (they belong to To do). A tile is the area
  filter (tap again, or "All areas", to clear).
- **Filters**: area (tiles), household member (chips, shown when the documents involve more than
  one person), words (search, by content). `?area=` and `?tab=` are kept in the address.
- **Calendar tab**: the timeline (two weeks back, four months ahead) and the list of upcoming
  deadlines, then the administrative year (`services/calendar.py`, `GET /api/calendar`): a static
  table of what comes back each month in France, marked "Concerns you" when a document of the
  matching type is held. Countries other than France get no table (Binder does not know theirs).
  The country follows Settings, then the system.
- **Removed**: the area pages (`pages/Area.tsx`) and their messages, the Documents page (now
  `pages/Papers.tsx`), "Coming up" (`components/upcoming.tsx`), the import button of the
  former page headers (＋ replaces it). The backend `GET /api/areas/{area}` is kept (tested,
  harmless) but the interface no longer calls it; the area's recurring bills are no longer shown
  in the interface (the agent still lists them: "How much do my subscriptions cost?").

### Step 5: life events

- **Frontend only**: the eight life events are groupings of what already exists (checklists,
  letter kinds, file kinds, a question to the agent, adding a paper), defined in
  `pages/Procedures.tsx`. No new backend: every sub-action already works without the model
  (letter templates, folder rules, the journeys' own steps), and the questions go to the agent.
  "I'm starting a job" and "I'm retiring" have no checklist of their own (none existed): a
  file and a question to the agent stand in.
- **Kept**: the checklists of the income tax return, the ID renewal and mortgage files, and any
  other letter or file, under "Other procedures".
- **In progress** sits on top of the page (it left To do in step 3); the finished letters stay
  at the bottom.
- **Removed**: `pages/Prepare.tsx`, the per-area `PrepareCard`, and their messages.

### Step 6: first launch

- **Answers** in the existing profile (`Profile.situation`, `housing`, `vehicle`, validated
  against `profile.CHOICES`; additive JSON fields), given to the agent with the profile.
- **Papers to have**: `services/essentials.py` (static table, i18n, works without the model),
  `GET /api/essentials`: why, how long to keep, present or missing (missing first).
- **Welcome screen**: three screens of one question, then the list with "Scan my first paper"
  and "Choose a file"; demo and restore stay at the bottom. "Skip for now" goes to the list.
- **Afterwards**: a row at the top of My papers ("The papers you should have · 6 of 9 already
  here") opens the list, with "Change my answers". The answers are not in Settings (the
  Settings page holds uncommitted changes of yours): the list is the place to change them.

### Step 7: in short, glossary, accessibility

- **In short at import**: each import report line starts with one sentence from the document's
  fields (`reports.brief`): what it is, the payment or renewal date or "nothing to do", how
  long it is kept. Immediate and without the model (the model's own "In short" stays on the
  document page, where it may take a few seconds). The details below no longer repeat it.
- **Glossary**: 17 terms, EN+FR definitions in `i18n/messages/glossary.ts`, matched in French
  and English wording (documents are French whatever the interface language). Applied to the
  To do cards, the question panel, the import report and "In short".
- **Print**: the app cannot print the PDF itself (every response carries `X-Frame-Options:
  DENY`, which `guard.py` must keep), so Print prints the letter's text through a print-only
  sheet; the PDF stays one click away.
- **Send by post**: no online posting service (local only): the four steps, with the
  recipient's address when Binder has it, then "I sent it", which starts the follow-up.
- **Text size**: kept in the browser's local storage (a display preference of this screen,
  like the theme of a window), applied before the first paint.
- **Labelled buttons**: every icon-only button already had an `aria-label` (or a screen-reader
  text); nothing to add.

## Summary

The seven steps are done, each in its own commit. Verified at every step: ruff, mypy, pytest,
`scripts/evaluate.py` (97.9%, the same telecom → other mistake as before the overhaul: not
touched), oxlint, frontend build, and the screens touched, on a desktop width and at 390 px
(headless Chrome with device emulation once the Chrome extension disconnected). On the demo,
an import shows 2 questions.

## Left to do

- `DocumentDetail`'s preview to reuse `DocumentPage` (the file holds uncommitted changes of
  yours).
- The first-launch answers can only be changed from the papers list, not in Settings (same
  reason).
- A test of the model's second reading (needs the fake Ollama of the tests).
- `evaluate.py`: the demo telecom bill read as "other" (rules: 97.9%, not 100% as PRODUCT.md
  says).
- `DocumentDetail`'s preview to reuse `DocumentPage`.
