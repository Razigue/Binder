export type Category =
  | "Impôts" | "Énergie" | "Assurance" | "Banque" | "Logement"
  | "Santé" | "Social" | "Travail" | "Télécom" | "Identité" | "Véhicule" | "Autre"

export const CATEGORIES: Category[] = [
  "Impôts", "Énergie", "Assurance", "Banque", "Logement",
  "Santé", "Social", "Travail", "Télécom", "Identité", "Véhicule", "Autre",
]

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
  llm_available: boolean
  llm_model: string
  ocr_engine: string | null
  encrypted: boolean
  data_dir: string
}

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

export interface ChatResponse {
  answer: string
  documents: Doc[]
  deadlines: Deadline[]
  tool_calls: { name: string; arguments: Record<string, unknown> }[]
  citations: number[]
  engine: "llm" | "rules"
}

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

export type LetterKind = "resiliation" | "reclamation" | "demande"

export interface Letter {
  kind: LetterKind
  subject: string
  recipient: string
  body: string
  registered: boolean
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = typeof body.detail === "string" ? body.detail : message
    } catch {
      /* corps non JSON */
    }
    throw new ApiError(res.status, message)
  }
  return res.status === 204 ? (undefined as T) : res.json()
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

export const api = {
  status: () => request<SystemStatus>("/status"),
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
  trash: () => request<Doc[]>("/trash"),
  restoreDocument: (id: number) => request<DocDetail>(`/documents/${id}/restore`, { method: "POST" }),
  purgeDocument: (id: number) => request<void>(`/documents/${id}/purge?confirm=true`, { method: "DELETE" }),
  expirations: () => request<Expiration[]>("/expirations"),
  retention: () => request<Doc[]>("/retention"),
  trashDeletable: (ids: number[]) => request<{ trashed: number }>("/retention/trash", json("POST", { ids })),
  importSettings: () => request<ImportSettings>("/import/settings"),
  saveImportSettings: (body: ImportSettingsIn) => request<ImportSettings>("/import/settings", json("PUT", body)),
  runImports: () => request<{ folder: ImportRun; mail: ImportRun }>("/import/run", { method: "POST" }),
  activity: (p: { document_id?: number; limit?: number; before?: number } = {}) =>
    request<Activity[]>(`/activity${query(p)}`),
  deadlines: (p: { start?: string; end?: string; include_done?: boolean } = {}) =>
    request<Deadline[]>(`/deadlines${query(p)}`),
  createDeadline: (body: { title: string; due_date: string; amount?: number | null; category?: Category }) =>
    request<Deadline>("/deadlines", json("POST", body)),
  updateDeadline: (id: number, body: { done?: boolean }) => request<Deadline>(`/deadlines/${id}`, json("PATCH", body)),
  seedDemo: () => request<{ imported: number }>("/demo", { method: "POST" }),
  chat: (message: string, history: ChatMessage[]) =>
    request<ChatResponse>("/agent/chat", json("POST", { message, history })),
}

export const fileUrl = (id: number) => `/api/documents/${id}/file`
export const previewUrl = (id: number, page = 0) => `/api/documents/${id}/preview?page=${page}`
export const exportUrl = (category?: Category) => `/api/export${query({ category })}`
export const folderExportUrl = (key: string) => `/api/folders/${key}/export`
