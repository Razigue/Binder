import { translate, type Language } from "@/i18n/core"
import { common } from "@/i18n/messages/common"
import { currentLocale } from "@/lib/format"

export type Category =
  | "taxes" | "energy" | "insurance" | "bank" | "housing" | "health"
  | "social" | "work" | "telecom" | "identity" | "vehicle" | "family" | "purchases" | "other"

export const CATEGORIES: Category[] = [
  "taxes", "energy", "insurance", "bank", "housing", "health",
  "social", "work", "telecom", "identity", "vehicle", "family", "purchases", "other",
]

export const DOC_TYPES = [
  "identity_card", "passport", "driving_licence", "residence_permit", "roadworthiness_test",
  "vehicle_registration", "bank_details", "employment_contract", "lease", "property_tax",
  "housing_tax", "tax_notice", "rent_receipt", "payment_notice", "insurance_certificate",
  "bank_statement", "payslip", "reimbursement_statement", "certificate", "quote",
  "payment_schedule", "invoice", "contract", "loan_statement", "savings_statement",
  "annual_tax_statement", "donation_receipt", "childcare_certificate", "school_certificate",
  "civil_status", "family_record_book", "pension_statement", "benefit_decision",
  "charges_statement", "fine", "purchase_receipt", "payment_reminder",
] as const

export type DocType = (typeof DOC_TYPES)[number]

export type Theme = "system" | "light" | "dark"

export interface Preferences {
  language: "auto" | "en" | "fr"
  country: string | null
  theme: Theme
  effective_language: "en" | "fr"
  effective_country: string | null
  currency: string
  system_language: "en" | "fr"
  system_country: string | null
}

export type PreferencesUpdate = Partial<Pick<Preferences, "language" | "country" | "theme">>

/** "waiting": a real document imported before the local AI was ready; read as soon as it is. */
export type DocumentStatus = "processing" | "waiting" | "to_review" | "classified"

export interface Doc {
  id: number
  filename: string
  mime_type: string
  size: number
  title: string
  category: Category
  issuer: string | null
  amount: number | null
  amount_ht?: number | null
  amount_tva?: number | null
  amount_ttc?: number | null
  amount_due?: number | null
  issue_date: string | null
  due_date: string | null
  expiry_date: string | null
  period_start?: string | null
  period_end?: string | null
  reference: string | null
  iban?: string | null
  siret?: string | null
  confidence: number
  status: DocumentStatus
  missing_fields: string[]
  extractor: string
  page_count: number
  created_at: string
  deleted_at: string | null
  doc_type: string | null
  duplicate_of: number | null
  superseded_by: number | null
  // Set when this is a copy of a letter Binder itself wrote (re-downloaded, re-imported): not
  // mail received from someone else.
  source_letter_id: number | null
  standard_name: string
  keep_forever: boolean
  retention_rule: string | null
  keep_until: string | null
  /** Why it can go to the archives (retention period over, replaced), null when it stays. */
  archivable_reason: string | null
  /** In the archives: out of the active views, still readable and restorable. */
  archived_at: string | null
  archive_reason: "retention" | "replaced" | "user" | null
  renew_from: string | null
  person: string | null
  area: Area | null
  batch: string | null
}

export interface DocDetail extends Doc {
  text: string
}

export type DocPatch = Partial<
  Pick<
    Doc,
    "title" | "category" | "issuer" | "amount" | "issue_date" | "due_date" | "expiry_date" | "reference" | "doc_type" | "person"
  >
> & { validated?: boolean; keep_forever?: boolean }

/** The life areas of the navigation. */
/** Grouped action on the documents selected in a list. */
export interface BulkResult {
  count: number
  message: string
}

export type BulkPatch = { category?: Category; keep_forever?: boolean; validated?: boolean }

export type Area = "housing" | "money" | "work" | "family" | "health" | "identity" | "vehicle"
export const AREAS: Area[] = ["housing", "money", "work", "family", "health", "identity", "vehicle"]

export interface Deadline {
  id: number
  document_id: number | null
  title: string
  category: Category
  due_date: string
  amount: number | null
  done: boolean
  source: "extracted" | "expiry" | "manual" | "followup"
  days_left: number
}

export interface Stats {
  upcoming_deadlines: number
  to_review: number
  classified_this_week: number
  total_documents: number
  trashed: number
  archived: number
  by_category: Record<string, number>
}

export interface SystemStatus {
  version: string
  llm_available: boolean
  llm_model: string
  ocr_engine: string | null
  encrypted: boolean
  data_dir: string
}

export interface ModelDownload {
  phase: "queued" | "starting" | "downloading" | "verifying" | "error"
  completed: number
  total: number
  error: string | null
}

export interface LocalModel {
  name: string
  label: string
  description: string
  size: number
  recommended: boolean
  /** "embedding": semantic search, used as soon as it is installed (never the active model). */
  kind: "chat" | "embedding"
  in_catalog: boolean
  installed: boolean
  download: ModelDownload | null
}

/** A better model for this machine, offered because Binder chose the active one. */
export interface ModelUpgrade {
  name: string
  label: string
  /** Download size, in bytes. */
  size: number
  /** The user said yes: Binder switches to it once downloaded. */
  accepted: boolean
  download: ModelDownload | null
}

export interface ModelsOverview {
  enabled: boolean
  ollama: boolean
  ollama_url: string
  active: string
  active_installed: boolean
  active_label: string
  /** Best model for this machine, measured at this launch. */
  recommended: string
  recommended_label: string
  /** The active model was picked by Binder (upgrades offered), not by the user. */
  automatic: boolean
  upgrade: ModelUpgrade | null
  models: LocalModel[]
}

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
  /** Documents the answer showed: the next question can refer to them. */
  documents?: number[]
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  /** Set once the tool has run. */
  duration_ms?: number | null
  error?: boolean
}

/** Token counts and speed of the local model for one answer. */
export interface ChatStats {
  model: string
  /** Model turns, one per tool round trip. */
  turns: number
  prompt_tokens: number
  output_tokens: number
  tokens_per_second: number | null
  prompt_tokens_per_second: number | null
  /** Whole answer, tools included. */
  seconds: number
}

export interface ChatResponse {
  answer: string
  documents: Doc[]
  deadlines: Deadline[]
  letters: Letter[]
  tool_calls: ToolCall[]
  citations: number[]
  /** The agent changed data (reminder, deadline paid, document corrected or trashed). */
  changed: boolean
  engine: "llm" | "rules"
  /** Undoes what the agent changed during this turn. */
  undo: string | null
  /** Packs of documents put together during the turn. */
  folders: Folder[]
  /** Journeys started or read during the turn. */
  journeys: Journey[]
  /** Null when the demo rules answered, without a model. */
  stats?: ChatStats | null
  /** Changes held back until the user confirms them (proposed after reading a document). */
  confirmations?: PendingAction[]
  /** Shown under the answer (a legal point that could not be checked online). */
  warnings?: string[]
}

export interface PendingAction {
  token: string
  tool: string
  description: string
}

export interface ConfirmResult {
  message: string
  changed: boolean
  undo: string | null
}

/** Progress of an answer: tools as they start, text as it is written. */
export type ChatEvent =
  | ({ type: "tool" } & ToolCall)
  | { type: "tool_done"; duration_ms: number; error: boolean }
  | { type: "stats"; stats: ChatStats }
  | { type: "token"; text: string }
  | { type: "step" }
  | { type: "done"; response: ChatResponse }
  | { type: "error"; message: string }

export type Actor = "user" | "binder" | "agent" | "watcher" | "mail" | "demo"

export interface Activity {
  id: number
  created_at: string
  actor: Actor
  action: string
  summary: string
  document_id: number | null
  details: Record<string, unknown>
}

export interface Expiration {
  document: Doc
  expiry_date: string
  renew_from: string
  days_left: number
  state: "expired" | "renew" | "valid"
}

export interface ImportSettings {
  folder: { enabled: boolean; path: string; last_check: string | null; last_error: string | null }
  mail: {
    enabled: boolean
    host: string
    port: number
    user: string
    folder: string
    since_days: number
    password_set: boolean
    last_check: string | null
    last_error: string | null
  }
}

export interface ImportSettingsIn {
  folder?: { enabled: boolean; path: string }
  mail?: {
    enabled: boolean
    host: string
    port: number
    user: string
    folder: string
    since_days: number
    password?: string | null
  }
}

type ImportRun = { imported: number; error: string | null } | null

export interface Explanation {
  summary: string
  action_required: boolean
  actions: { label: string; due_date: string | null }[]
  key_points: string[]
  engine: "llm" | "rules"
}

export interface FolderPiece {
  key: string
  label: string
  status: "ok" | "partial" | "outdated" | "missing"
  found: number
  needed: number
  optional: boolean
  hint: string
  document_ids: number[]
  note: string
}

export interface Folder {
  key: string
  title: string
  description: string
  complete: boolean
  ready: number
  total: number
  pieces: FolderPiece[]
}

export interface Profile {
  name: string
  address: string
  city: string
  email: string
  phone: string
  /** What the agent must know about the user, in their own words. */
  notes: string
  /** Fields Binder filled from the documents (it keeps them up to date until the user edits). */
  auto: string[]
}

export const LETTER_KINDS = [
  "termination", "complaint", "request", "payment_plan", "appeal", "formal_notice", "address_change",
] as const

export type LetterKind = (typeof LETTER_KINDS)[number]

export interface Letter {
  kind: LetterKind | "custom" | "followup"
  subject: string
  recipient: string
  body: string
  /** Advise sending it by registered mail with acknowledgement of receipt. */
  registered: boolean
  /** Language of the letter: the recipient's (French for FR/BE/LU/MC), not necessarily the UI's. */
  language: "en" | "fr"
  /** Saved letter: PDF, "sent", follow-up. */
  id: number | null
  document_id: number | null
  recipient_address: string
  sent_on: string | null
  follow_up_on: string | null
  answered: boolean
  /** Details left in [brackets] for the user to fill in. */
  blanks: number
  /** Its legal points, checked online when it was written. */
  verification: LegalCheck | null
  /** Web pages it was adapted from: the organisation's procedure and conditions. */
  sources: LegalSource[]
}

export interface LegalSource {
  title: string
  url: string
}

/** A legal point of a letter. `outdated`: the official source says otherwise (`evidence`, its own
 * sentence); the letter is not changed, `correction` is the wording the user can apply. */
export interface LegalPoint {
  claim: string
  status: "confirmed" | "outdated" | "unverified"
  evidence: string
  correction: string
  sources: LegalSource[]
}

/** `outdated`: a source contradicts a point; `unverified`: a point could not be checked;
 * `none`: the letter quotes no law. */
export interface LegalCheck {
  status: "verified" | "outdated" | "unverified" | "none"
  checked_on: string
  points: LegalPoint[]
}

export type Tone = "urgent" | "soon" | "info"

/** One-tap action of a Today card. Server actions go through POST /actions; the others are
 * handled by the interface (open, agent, upload, report, pdf). */
export interface FeedAction {
  type: string
  label: string
  primary: boolean
  params: Record<string, unknown>
}

export interface FeedItem {
  key: string
  kind:
    | "report" | "briefing" | "question" | "deadline" | "expiry" | "anomaly"
    | "missing" | "letter" | "suggestion" | "household" | "journey" | "waiting"
  tone: Tone
  title: string
  detail: string
  area: Area | null
  category: Category | null
  amount: number | null
  when: string | null
  document_ids: number[]
  actions: FeedAction[]
  extra: Record<string, unknown>
}

export const FOLDER_KINDS = ["rental", "mortgage", "caf", "identity_renewal", "school", "retirement"] as const

export type FolderKind = (typeof FOLDER_KINDS)[number]

export const JOURNEY_KINDS = ["moving", "birth", "death", "tax_return"] as const

export type JourneyKind = (typeof JOURNEY_KINDS)[number]

/** What a step offers to do in one tap. */
export type StepAction =
  | { type: "letter"; label: string; params: { kind?: LetterKind; purpose?: string; details?: string; document_id?: number } }
  | { type: "folder"; label: string; params: { kind: FolderKind } }
  | { type: "open"; label: string; params: { url: string } }

export interface JourneyStep {
  key: string
  title: string
  detail: string
  due: string | null
  done: boolean
  /** Done on its own: the letter was sent, the document arrived. */
  auto: boolean
  document_ids: number[]
  amount: number | null
  action: StepAction | null
}

export interface Journey {
  id: number
  kind: JourneyKind
  title: string
  description: string
  event_label: string
  event_date: string
  details: Record<string, string>
  steps: JourneyStep[]
  done: number
  total: number
  closed: boolean
  created_at: string
}

export interface JourneyKindInfo {
  kind: JourneyKind
  title: string
  description: string
  event_label: string
  default_date: string | null
  /** What can be told when starting ({key: label}). */
  fields: Record<string, string>
}

export interface SetupStatus {
  phase: "disabled" | "checking" | "installing" | "starting" | "downloading" | "ready" | "error"
  completed: number
  total: number
  model: string | null
  error: string | null
  /** Works, but not as well as it should (an outdated Ollama, a model too heavy). Localized. */
  warning?: string | null
  /** A better model for this machine, offered (never downloaded without a yes). */
  upgrade?: ModelUpgrade | null
}

export interface Feed {
  items: FeedItem[]
  documents: number
  setup: SetupStatus
}

export interface ActResult {
  message: string
  letter: Letter | null
}

export interface ReportItem {
  document: Doc
  facts: string[]
  events: string[]
  question: { key: string; title: string; detail: string; choices: { id: string; label: string; primary: boolean }[] } | null
}

export interface ImportReport {
  batch: string
  source: string
  processing: number
  items: ReportItem[]
  summary: string
  to_pay: number
}

export interface Member {
  name: string
  documents: number
  areas: Area[]
}

export interface AreaSummary {
  area: Area
  label: string
  documents: number
  attention: number
}

export interface AreaDetail {
  area: Area
  label: string
  documents: Doc[]
  deadlines: Deadline[]
  subscriptions: Subscription[]
  items: FeedItem[]
  members: Member[]
  yearly_cost: number
}

export interface FieldSource {
  field: string
  boxes: { page: number; x0: number; y0: number; x1: number; y1: number }[]
}

export interface BackupInfo {
  code: string | null
  confirmed: boolean
  folder: string
  last_backup: string | null
  last_error: string | null
}

export interface Subscription {
  key: string
  label: string
  category: Category
  doc_type: string | null
  cadence: string
  interval_days: number | null
  last_amount: number
  previous_amount: number
  change_pct: number
  yearly_estimate: number | null
  increase: boolean
  history: { document_id: number; date: string; amount: number }[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Outside React: the language comes from the locale set by I18nProvider.
function genericError(): string {
  const language: Language = currentLocale().startsWith("fr") ? "fr" : "en"
  return translate(common, language)("state.error")
}

/** Called after every change the backend can undo (X-Undo header): the app offers "Undo". */
type UndoListener = (token: string, body: unknown) => void
let undoListener: UndoListener | null = null

export function onUndoable(listener: UndoListener | null) {
  undoListener = listener
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  await check(res)
  const body = res.status === 204 ? (undefined as T) : await res.json()
  const token = res.headers.get("X-Undo")
  if (token && undoListener) undoListener(token, body)
  return body
}

async function check(res: Response) {
  if (!res.ok) {
    // The backend localises `detail` itself; anything else gets a generic message.
    let message = genericError()
    try {
      const body = await res.json()
      if (typeof body.detail === "string") message = body.detail
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, message)
  }
}

/** Agent answer as a stream of events (newline-delimited JSON); resolves with the response. */
async function chatStream(
  body: { message: string; history: ChatMessage[]; attachments: number[]; viewing?: number },
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await fetch("/api/agent/chat/stream", { ...json("POST", body), signal })
  await check(res)
  if (!res.body) throw new ApiError(500, genericError())
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ""
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line) as ChatEvent
      if (event.type === "done") return event.response
      if (event.type === "error") throw new ApiError(500, event.message)
      onEvent(event)
    }
  }
  throw new ApiError(500, genericError())
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

function query(params: Record<string, string | number | boolean | undefined | null>) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ""
}

export interface ScanPage {
  id: string
  /** False when no outline was found: the whole photo is kept. */
  detected: boolean
}

export interface ScanSession {
  /** Address of the scanning page on the local network, carried by the QR code. */
  url: string
  qr_code: string
  phone_connected: boolean
  documents: ScanPage[][]
  /** Ids of the documents created once the scan is sent, null until then. */
  imported: number[] | null
}

export const api = {
  status: () => request<SystemStatus>("/status"),
  preferences: () => request<Preferences>("/preferences"),
  updatePreferences: async (patch: PreferencesUpdate) => {
    const current = await request<Preferences>("/preferences")
    const body = { language: current.language, country: current.country, theme: current.theme, ...patch }
    return request<Preferences>("/preferences", json("PUT", body))
  },
  stats: () => request<Stats>("/stats"),
  documents: (p: { q?: string; category?: Category; status?: DocumentStatus; archived?: boolean; limit?: number } = {}) =>
    request<Doc[]>(`/documents${query(p)}`),
  document: (id: number) => request<DocDetail>(`/documents/${id}`),
  upload: (file: File, batch?: string) => {
    const form = new FormData()
    form.append("file", file)
    return request<Doc>(`/documents${query({ batch })}`, { method: "POST", body: form })
  },
  updateDocument: (id: number, patch: DocPatch) => request<DocDetail>(`/documents/${id}`, json("PATCH", patch)),
  reanalyze: (id: number) => request<DocDetail>(`/documents/${id}/reanalyze`, { method: "POST" }),
  deleteDocument: (id: number) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  bulkTrash: (ids: number[]) => request<BulkResult>("/documents/bulk/trash", json("POST", { ids })),
  bulkUpdate: (ids: number[], patch: BulkPatch) =>
    request<BulkResult>("/documents/bulk/update", json("POST", { ids, ...patch })),
  bulkReanalyze: (ids: number[]) => request<BulkResult>("/documents/bulk/reanalyze", json("POST", { ids })),
  bulkArchive: (ids: number[]) => request<BulkResult>("/documents/bulk/archive", json("POST", { ids })),
  bulkUnarchive: (ids: number[]) => request<BulkResult>("/archives/restore", json("POST", { ids })),
  archiveDocument: (id: number) => request<DocDetail>(`/documents/${id}/archive`, { method: "POST" }),
  unarchiveDocument: (id: number) => request<DocDetail>(`/documents/${id}/unarchive`, { method: "POST" }),
  bulkRestore: (ids: number[]) => request<BulkResult>("/trash/restore", json("POST", { ids })),
  bulkPurge: (ids: number[]) => request<BulkResult>("/trash/purge", json("POST", { ids, confirm: true })),
  explanation: (id: number, refresh = false) =>
    request<Explanation>(`/documents/${id}/explanation${query({ refresh: refresh || undefined })}`),
  folders: () => request<Folder[]>("/folders"),
  profile: () => request<Profile>("/profile"),
  saveProfile: (body: Profile) => request<Profile>("/profile", json("PUT", body)),
  writeLetter: (body: { kind?: LetterKind; purpose?: string; document_id?: number | null; details?: string }) =>
    request<Letter>("/letters", json("POST", body)),
  editLetter: (id: number, body: string) => request<Letter>(`/letters/${id}`, json("PUT", { body })),
  letterSent: (id: number) => request<Letter>(`/letters/${id}/sent`, { method: "POST" }),
  letterAnswered: (id: number) => request<Letter>(`/letters/${id}/answered`, { method: "POST" }),
  letterFollowUp: (id: number) => request<Letter>(`/letters/${id}/follow-up`, { method: "POST" }),
  deleteLetter: (id: number) => request<void>(`/letters/${id}`, { method: "DELETE" }),
  letters: () => request<Letter[]>("/letters"),
  feed: () => request<Feed>("/feed"),
  act: (action: Pick<FeedAction, "type" | "params">) =>
    request<ActResult>("/actions", json("POST", { type: action.type, params: action.params })),
  undo: (token: string) => request<void>(`/undo/${encodeURIComponent(token)}`, { method: "POST" }),
  confirmAction: (token: string) =>
    request<ConfirmResult>(`/agent/confirm/${encodeURIComponent(token)}`, { method: "POST" }),
  report: (batch: string) => request<ImportReport>(`/reports/${encodeURIComponent(batch)}`),
  reportSeen: (batch: string) => request<void>(`/reports/${encodeURIComponent(batch)}/seen`, { method: "POST" }),
  areas: () => request<AreaSummary[]>("/areas"),
  area: (area: Area) => request<AreaDetail>(`/areas/${area}`),
  household: () => request<Member[]>("/household"),
  sources: (id: number) => request<FieldSource[]>(`/documents/${id}/sources`),
  prepareFolder: (purpose: string) => request<Folder>("/folders/prepare", json("POST", { purpose })),
  journeyKinds: () => request<JourneyKindInfo[]>("/journeys/kinds"),
  journeys: () => request<Journey[]>("/journeys"),
  journey: (id: number) => request<Journey>(`/journeys/${id}`),
  startJourney: (body: { kind: JourneyKind; event_date: string; details: Record<string, string> }) =>
    request<Journey>("/journeys", json("POST", body)),
  updateJourney: (id: number, body: { event_date?: string; details?: Record<string, string>; closed?: boolean }) =>
    request<Journey>(`/journeys/${id}`, json("PATCH", body)),
  journeyStep: (id: number, key: string, done: boolean) =>
    request<Journey>(`/journeys/${id}/steps/${encodeURIComponent(key)}`, json("PUT", { done })),
  setup: () => request<SetupStatus>("/setup"),
  retrySetup: () => request<SetupStatus>("/setup/retry", { method: "POST" }),
  backup: () => request<BackupInfo>("/backup"),
  backupNow: () => request<BackupInfo>("/backup/now", { method: "POST" }),
  confirmRecoveryCode: () => request<BackupInfo>("/backup/confirm", { method: "POST" }),
  renewRecoveryCode: () => request<BackupInfo>("/backup/code", { method: "POST" }),
  restoreBackup: (file: File, code: string) => {
    const form = new FormData()
    form.append("file", file)
    form.append("code", code)
    return request<void>("/backup/restore", { method: "POST", body: form })
  },
  subscriptions: () => request<Subscription[]>("/subscriptions"),
  trash: () => request<Doc[]>("/trash"),
  restoreDocument: (id: number) => request<DocDetail>(`/documents/${id}/restore`, { method: "POST" }),
  purgeDocument: (id: number) => request<void>(`/documents/${id}/purge?confirm=true`, { method: "DELETE" }),
  expirations: () => request<Expiration[]>("/expirations"),
  importSettings: () => request<ImportSettings>("/import/settings"),
  saveImportSettings: (body: ImportSettingsIn) => request<ImportSettings>("/import/settings", json("PUT", body)),
  runImports: () => request<{ folder: ImportRun; mail: ImportRun }>("/import/run", { method: "POST" }),
  models: () => request<ModelsOverview>("/llm"),
  chooseModel: (name: string) => request<ModelsOverview>("/llm/model", json("PUT", { name })),
  acceptUpgrade: () => request<ModelsOverview>("/llm/upgrade", { method: "POST" }),
  declineUpgrade: () => request<ModelsOverview>("/llm/upgrade/decline", { method: "POST" }),
  downloadModel: (name: string) =>
    request<ModelsOverview>(`/llm/models/${encodeURIComponent(name)}/download`, { method: "POST" }),
  cancelDownload: (name: string) =>
    request<void>(`/llm/models/${encodeURIComponent(name)}/download`, { method: "DELETE" }),
  deleteModel: (name: string) => request<void>(`/llm/models/${encodeURIComponent(name)}`, { method: "DELETE" }),
  activity: (p: { document_id?: number; limit?: number; before?: number } = {}) =>
    request<Activity[]>(`/activity${query(p)}`),
  deadlines: (p: { start?: string; end?: string; include_done?: boolean } = {}) =>
    request<Deadline[]>(`/deadlines${query(p)}`),
  createDeadline: (body: { title: string; due_date: string; amount?: number | null; category?: Category }) =>
    request<Deadline>("/deadlines", json("POST", body)),
  updateDeadline: (id: number, body: { done?: boolean }) => request<Deadline>(`/deadlines/${id}`, json("PATCH", body)),
  openScan: () => request<ScanSession>("/scan/session", { method: "POST" }),
  scanSession: () => request<ScanSession>("/scan/session"),
  importScan: () => request<ScanSession>("/scan/session/import", { method: "POST" }),
  closeScan: () => request<void>("/scan/session", { method: "DELETE" }),
  deleteScanPage: (id: string) => request<void>(`/scan/pages/${id}`, { method: "DELETE" }),
  seedDemo: () => request<{ imported: number; batch: string | null }>("/demo", { method: "POST" }),
  demoStatus: () => request<{ documents: number; leftovers: number }>("/demo"),
  clearDemo: () => request<{ removed: number; files: number }>("/demo", { method: "DELETE" }),
  eraseData: () => request<{ removed: number }>("/data?confirm=true", { method: "DELETE" }),
  chat: (message: string, history: ChatMessage[], attachments: number[] = [], signal?: AbortSignal) =>
    request<ChatResponse>("/agent/chat", { ...json("POST", { message, history, attachments }), signal }),
  chatStream: (
    message: string,
    history: ChatMessage[],
    attachments: number[],
    onEvent: (event: ChatEvent) => void,
    signal?: AbortSignal,
    // Document open on screen: the question may be about it.
    viewing?: number,
  ) => chatStream({ message, history, attachments, viewing }, onEvent, signal),
}

export const fileUrl = (id: number) => `/api/documents/${id}/file`
export const previewUrl = (id: number, page = 0) => `/api/documents/${id}/preview?page=${page}`
export const exportUrl = (category?: Category) => `/api/export${query({ category })}`
export const selectionExportUrl = (ids: number[]) => `/api/export?${ids.map((id) => `ids=${id}`).join("&")}`
export const scanThumbUrl = (id: string) => `/api/scan/pages/${id}/thumb`
export const folderExportUrl = (key: string) => `/api/folders/${key}/export`
export const letterPdfUrl = (id: number) => `/api/letters/${id}/pdf`
