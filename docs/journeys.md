# Journey archives, trash and shared chat drafts

A journey is a checklist; its documents remain independent. Closing it records `closed_at` in
UTC and moves it to My papers > Archives. Reopening clears that date. Existing closed journeys
without a recorded date stay visible with an unknown date; migration does not invent one.

Deleting an archived journey sets nullable `deleted_at`. Normal listings, detail edits, the
active feed and tax-return life events exclude deleted journeys. The profile menu's Trash lists
them separately from documents. Restoring keeps the completion date and closed status. Closing,
reopening, trashing and restoring support the existing undo mechanism.

The journey API exposes `GET /api/journeys/trash`, `DELETE /api/journeys/{id}` (archived only),
`POST /api/journeys/{id}/restore` and `DELETE /api/journeys/{id}/permanent?confirm=true` (trashed
only). Permanent deletion requires explicit UI confirmation. Every deletion and restoration is
logged through the activity service. None of these actions removes linked documents or files.

The shared chat draft lives in AgentProvider memory and is used by the bottom ask bar and side
composer. It survives closing the panel or consulting history, and clears on sending. It is not
written to browser storage. The selected model is indicated by the picker rather than a second
summary above it. User-facing descriptions speak as “I” directly to “you”, in both catalogs and
the agent system prompt.
