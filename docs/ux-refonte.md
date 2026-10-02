# UX overhaul (refonte UX)

Tracking file of the UX overhaul: what is done, the decisions taken where the brief left a
choice, and what is left. One commit per step.

## Steps

| # | Step | State |
|---|------|-------|
| 1 | Archives + Archives tab | done |
| 2 | Questions (filter, grouping, cap, panel with the document) | to do |
| 3 | Navigation and To do | to do |
| 4 | My papers | to do |
| 5 | Life events (Démarches) | to do |
| 6 | First launch | to do |
| 7 | Glossary and accessibility | to do |

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

## Left to do

- Steps 2 to 7.
