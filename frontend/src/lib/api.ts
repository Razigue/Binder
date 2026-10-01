import { translate, type Language } from "@/i18n/core"
import { common } from "@/i18n/messages/common"
import { currentLocale } from "@/lib/format"

export type Category =
  | "taxes" | "energy" | "insurance" | "bank" | "housing" | "health"
  | "social" | "work" | "telecom" | "identity" | "vehicle" | "other"

export const CATEGORIES: Category[] = [
  "taxes", "energy", "insurance", "bank", "housing", "health",
  "social", "work", "telecom", "identity", "vehicle", "other",
]

export const DOC_TYPES = [
  "identity_card", "passport", "driving_licence", "residence_permit", "roadworthiness_test",
  "vehicle_registration", "bank_details", "employment_contract", "lease", "property_tax",
  "housing_tax", "tax_notice", "rent_receipt", "payment_notice", "insurance_certificate",
  "bank_statement", "payslip", "reimbursement_statement", "certificate", "quote",
  "payment_schedule", "invoice", "contract",
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

export type DocumentStatus = "processing" | "to_review" | "classified"

export interface Doc {
  id: number
  filename: string
  mime_type: string
  size: number
  title: string
  category: Category
  issuer: string | null
  amount: number | null
  issue_date: string | null
  due_date: string | null
  expiry_date: string | null
  reference: string | null
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
  standard_name: string
  keep_forever: boolean
  retention_rule: string | null
  keep_until: string | null
  deletable_reason: string | null
  renew_from: string | null
}

export interface DocDetail extends Doc {
  text: string
}

export type DocPatch = Partial<
  Pick<Doc, "title" | "category" | "issuer" | "amount" | "issue_date" | "due_date" | "expiry_date" | "reference" | "doc_type">
> & { validated?: boolean; keep_forever?: boolean }

export interface Deadline {
  id: number
  document_id: number | null
  title: string
  category: Category
  due_date: string
  amount: number | null
  done: boolean
  source: "extracted" | "expiry" | "manual"
  days_left: number
}

export interface Stats {
  upcoming_deadlines: number
  to_review: number
  classified_this_week: number
  total_documents: number
  trashed: number
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

export interface ModelsOverview {
  enabled: boolean
  ollama: boolean
  ollama_url: string
  active: string
  active_installed: boolean
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
}

/** Progress of an answer: tools as they start, text as it is written. */
export type ChatEvent =
  | ({ type: "tool" } & ToolCall)
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
}

export const LETTER_KINDS = ["termination", "complaint", "request"] as const

export type LetterKind = (typeof LETTER_KINDS)[number]

export interface Letter {
  kind: LetterKind
  subject: string
  recipient: string
  body: string
  /** Advise sending it by registered mail with acknowledgement of receipt. */
  registered: boolean
  /** Language of the letter: the recipient's (French for FR/BE/LU/MC), not necessarily the UI's. */
  language: "en" | "fr"
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  await check(res)
  return res.status === 204 ? (undefined as T) : res.json()
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
  body: { message: string; history: ChatMessage[]; attachments: number[] },
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
  documents: (p: { q?: string; category?: Category; status?: DocumentStatus; limit?: number } = {}) =>
    request<Doc[]>(`/documents${query(p)}`),
  document: (id: number) => request<DocDetail>(`/documents/${id}`),
  upload: (file: File) => {
    const form = new FormData()
    form.append("file", file)
    return request<Doc>("/documents", { method: "POST", body: form })
  },
  updateDocument: (id: number, patch: DocPatch) => request<DocDetail>(`/documents/${id}`, json("PATCH", patch)),
  reanalyze: (id: number) => request<DocDetail>(`/documents/${id}/reanalyze`, { method: "POST" }),
  deleteDocument: (id: number) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  explanation: (id: number, refresh = false) =>
    request<Explanation>(`/documents/${id}/explanation${query({ refresh: refresh || undefined })}`),
  folders: () => request<Folder[]>("/folders"),
  profile: () => request<Profile>("/profile"),
  saveProfile: (body: Profile) => request<Profile>("/profile", json("PUT", body)),
  writeLetter: (body: { kind: LetterKind; document_id?: number | null; details?: string }) =>
    request<Letter>("/letters", json("POST", body)),
  subscriptions: () => request<Subscription[]>("/subscriptions"),
  trash: () => request<Doc[]>("/trash"),
  restoreDocument: (id: number) => request<DocDetail>(`/documents/${id}/restore`, { method: "POST" }),
  purgeDocument: (id: number) => request<void>(`/documents/${id}/purge?confirm=true`, { method: "DELETE" }),
  expirations: () => request<Expiration[]>("/expirations"),
  retention: () => request<Doc[]>("/retention"),
  trashDeletable: (ids: number[]) => request<{ trashed: number }>("/retention/trash", json("POST", { ids })),
  importSettings: () => request<ImportSettings>("/import/settings"),
  saveImportSettings: (body: ImportSettingsIn) => request<ImportSettings>("/import/settings", json("PUT", body)),
  runImports: () => request<{ folder: ImportRun; mail: ImportRun }>("/import/run", { method: "POST" }),
  models: () => request<ModelsOverview>("/llm"),
  chooseModel: (name: string) => request<ModelsOverview>("/llm/model", json("PUT", { name })),
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
  seedDemo: () => request<{ imported: number }>("/demo", { method: "POST" }),
  chat: (message: string, history: ChatMessage[], attachments: number[] = [], signal?: AbortSignal) =>
    request<ChatResponse>("/agent/chat", { ...json("POST", { message, history, attachments }), signal }),
  chatStream: (
    message: string,
    history: ChatMessage[],
    attachments: number[],
    onEvent: (event: ChatEvent) => void,
    signal?: AbortSignal,
  ) => chatStream({ message, history, attachments }, onEvent, signal),
}

export const fileUrl = (id: number) => `/api/documents/${id}/file`
export const previewUrl = (id: number, page = 0) => `/api/documents/${id}/preview?page=${page}`
export const exportUrl = (category?: Category) => `/api/export${query({ category })}`
export const scanThumbUrl = (id: string) => `/api/scan/pages/${id}/thumb`
export const folderExportUrl = (key: string) => `/api/folders/${key}/export`
