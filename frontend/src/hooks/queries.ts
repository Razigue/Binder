import { useCallback, useEffect, useRef } from "react"
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { api, type BulkPatch, type Category, type Doc, type DocPatch, type DocumentStatus, type Profile } from "@/lib/api"

type DocumentsParams = { q?: string; category?: Category; status?: DocumentStatus; archived?: boolean; limit?: number }
type DeadlinesParams = { start?: string; end?: string; include_done?: boolean }
type ActivityParams = { document_id?: number; limit?: number }

/** Every query key, so that reads and invalidations agree. */
export const keys = {
  stats: ["stats"] as const,
  status: ["status"] as const,
  changes: ["changes"] as const,
  preferences: ["preferences"] as const,
  documents: (p: DocumentsParams) => ["documents", p] as const,
  document: (id: number) => ["document", id] as const,
  // The reading depends on the fields: a correction asks for it again.
  sources: (d: Doc) => ["sources", d.id, d.amount, d.due_date, d.issue_date, d.expiry_date, d.reference, d.issuer] as const,
  explanation: (d: Doc) => ["explanation", d.id, d.amount, d.due_date, d.expiry_date, d.title] as const,
  deadlines: (p: DeadlinesParams) => ["deadlines", p] as const,
  trash: ["trash"] as const,
  expirations: ["expirations"] as const,
  activity: (p: ActivityParams) => ["activity", p] as const,
  subscriptions: ["subscriptions"] as const,
  feed: ["feed"] as const,
  questions: (ids?: number[]) => ["questions", ids ?? "all"] as const,
  report: (batch: string) => ["report", batch] as const,
  areas: ["areas"] as const,
  calendar: ["calendar"] as const,
  models: ["models"] as const,
  conversations: ["conversations"] as const,
  journeys: ["journeys"] as const,
  journeyKinds: ["journeyKinds"] as const,
  journey: (id: number) => ["journey", id] as const,
  letters: ["letters"] as const,
  profile: ["profile"] as const,
  essentials: ["essentials"] as const,
  household: ["household"] as const,
  reminders: ["reminders"] as const,
  backup: ["backup"] as const,
  demo: ["demo"] as const,
  importSettings: ["import-settings"] as const,
  scanSession: (url: string | undefined) => ["scan-session", url] as const,
}

/** Query definitions shared by several readers (`useQuery`, `useQueries`, the query client). */
export const queries = {
  documents: (p: DocumentsParams = {}) =>
    queryOptions({
      queryKey: keys.documents(p),
      queryFn: () => api.documents(p),
      // Refresh the list while a document is being analysed.
      refetchInterval: (q) => (q.state.data?.some((d) => d.status === "processing") ? 1500 : false),
    }),
  document: (id: number) =>
    queryOptions({
      queryKey: keys.document(id),
      queryFn: () => api.document(id),
      refetchInterval: (q) => (q.state.data?.status === "processing" ? 1000 : false),
    }),
  explanation: (doc: Doc) =>
    queryOptions({ queryKey: keys.explanation(doc), queryFn: () => api.explanation(doc.id), staleTime: Infinity }),
}

export function useStatus() {
  return useQuery({ queryKey: keys.status, queryFn: api.status, refetchInterval: 30_000 })
}

export function useStats() {
  return useQuery({ queryKey: keys.stats, queryFn: api.stats })
}

export function useDocuments(p: DocumentsParams = {}) {
  return useQuery(queries.documents(p))
}

export function useDocument(id: number | null) {
  return useQuery({ ...queries.document(id ?? 0), enabled: id !== null })
}

/** Where each field was read on the page, once the document is read. */
export function useSources(doc: Doc) {
  return useQuery({
    queryKey: keys.sources(doc),
    queryFn: () => api.sources(doc.id),
    enabled: doc.status !== "processing",
    staleTime: Infinity,
  })
}

export function useDeadlines(p: DeadlinesParams = {}) {
  return useQuery({ queryKey: keys.deadlines(p), queryFn: () => api.deadlines(p) })
}

/** Refreshes every view when Binder changed something on its own (a file dropped in the
 * watched folder, an email, an analysis that waited for the model). */
export function useLiveChanges() {
  const qc = useQueryClient()
  const seen = useRef<number | null>(null)
  const changes = useQuery({ queryKey: keys.changes, queryFn: api.changes, refetchInterval: 3000 })
  const revision = changes.data?.revision
  useEffect(() => {
    if (revision === undefined) return
    if (seen.current !== null && revision !== seen.current) {
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== keys.changes[0] })
    }
    seen.current = revision
  }, [revision, qc])
}

export function useInvalidateAll() {
  const qc = useQueryClient()
  return useCallback(() => qc.invalidateQueries(), [qc])
}

export function useUpdateDocument(id: number) {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: (patch: DocPatch) => api.updateDocument(id, patch), onSuccess: invalidate })
}

export function useDeleteDocument() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: api.deleteDocument, onSuccess: invalidate })
}

export function useReanalyze() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: api.reanalyze, onSuccess: invalidate })
}

/** Grouped actions on the documents selected in a list. */
export function useBulkDocuments() {
  const invalidate = useInvalidateAll()
  const options = { onSuccess: invalidate }
  return {
    trash: useMutation({ mutationFn: api.bulkTrash, ...options }),
    update: useMutation({
      mutationFn: ({ ids, patch }: { ids: number[]; patch: BulkPatch }) => api.bulkUpdate(ids, patch),
      ...options,
    }),
    reanalyze: useMutation({ mutationFn: api.bulkReanalyze, ...options }),
    restore: useMutation({ mutationFn: api.bulkRestore, ...options }),
    archive: useMutation({ mutationFn: api.bulkArchive, ...options }),
    unarchive: useMutation({ mutationFn: api.bulkUnarchive, ...options }),
    purge: useMutation({ mutationFn: api.bulkPurge, ...options }),
  }
}

export function useToggleDeadline() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => api.updateDeadline(id, { done }),
    onSuccess: invalidate,
  })
}

export function useTrash() {
  return useQuery({ queryKey: keys.trash, queryFn: api.trash })
}

export function useActivity(p: ActivityParams = {}) {
  return useQuery({ queryKey: keys.activity(p), queryFn: () => api.activity(p) })
}

export function useRestoreDocument() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: api.restoreDocument, onSuccess: invalidate })
}

export function usePurgeDocument() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: api.purgeDocument, onSuccess: invalidate })
}

export function useSubscriptions() {
  return useQuery({ queryKey: keys.subscriptions, queryFn: api.subscriptions })
}

export function useExpirations() {
  return useQuery({ queryKey: keys.expirations, queryFn: api.expirations })
}

/** Archive or bring back one document (both offer "Undo"). */
export function useArchiveDocument() {
  const invalidate = useInvalidateAll()
  return {
    archive: useMutation({ mutationFn: api.archiveDocument, onSuccess: invalidate }),
    unarchive: useMutation({ mutationFn: api.unarchiveDocument, onSuccess: invalidate }),
  }
}

/** The Today feed; refreshed often while the local AI installs, documents arrive in the background. */
export function useFeed() {
  return useQuery({
    queryKey: keys.feed,
    queryFn: api.feed,
    refetchInterval: (q) => {
      const setup = q.state.data?.setup
      const installing = setup && setup.phase !== "ready" && setup.phase !== "disabled"
      return installing || setup?.upgrade?.accepted ? 2000 : 30_000
    },
  })
}

/** The questions Binder has: every one (grouped), or one per document of `ids`. */
export function useQuestions(ids?: number[]) {
  return useQuery({ queryKey: keys.questions(ids), queryFn: () => api.questions(ids) })
}

/** What an import brought in. */
export function useReport(batch: string) {
  return useQuery({
    queryKey: keys.report(batch),
    queryFn: () => api.report(batch),
    retry: false,
    // Until every document of the import is read (and while the first one is still uploading).
    refetchInterval: (q) => (!q.state.data || q.state.data.processing ? 1500 : false),
  })
}

export function useAreas() {
  return useQuery({ queryKey: keys.areas, queryFn: api.areas, refetchInterval: 30_000 })
}

/** The administrative year: what comes back every year. */
export function useCalendar() {
  return useQuery({ queryKey: keys.calendar, queryFn: api.calendar, staleTime: 300_000 })
}

/** The local AI models; refreshed while an accepted upgrade downloads. */
export function useModels() {
  return useQuery({
    queryKey: keys.models,
    queryFn: api.models,
    refetchInterval: (q) => (q.state.data?.upgrade?.accepted ? 2000 : false),
  })
}

export function useConversations() {
  return useQuery({ queryKey: keys.conversations, queryFn: api.conversations })
}

export function useJourneys() {
  return useQuery({ queryKey: keys.journeys, queryFn: api.journeys })
}

export function useJourneyKinds() {
  return useQuery({ queryKey: keys.journeyKinds, queryFn: api.journeyKinds, staleTime: Infinity })
}

export function useJourney(id: number | null) {
  return useQuery({ queryKey: keys.journey(id ?? 0), queryFn: () => api.journey(id ?? 0), enabled: id !== null })
}

/** Letters Binder wrote, most recent first: drafts, sent ones awaiting an answer, answered. */
export function useLetters() {
  return useQuery({ queryKey: keys.letters, queryFn: api.letters })
}

export function useDeleteLetter() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: api.deleteLetter, onSuccess: invalidate })
}

export function useUpdateJourney() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: ({ id, closed }: { id: number; closed: boolean }) => api.updateJourney(id, { closed }),
    onSuccess: invalidate,
  })
}

/** The user's details; `fresh` for a form editing them, else a minute old is fine (a name shown). */
export function useProfile({ fresh = false } = {}) {
  return useQuery({ queryKey: keys.profile, queryFn: api.profile, ...(fresh ? {} : { staleTime: 60_000 }) })
}

/** Saves answers about the user's situation on top of the latest profile (the details form keeps
 * its own unsaved edits); the papers to have follow. */
export function useSaveSituation(onSaved?: () => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (answer: Partial<Profile>) => api.saveProfile({ ...(await api.profile()), ...answer }),
    onSuccess: (saved) => {
      qc.setQueryData(keys.profile, saved)
      void qc.invalidateQueries({ queryKey: keys.essentials })
      onSaved?.()
    },
    onError: (e) => toast.error(e.message),
  })
}

/** The papers to have for the user's situation. */
export function useEssentials() {
  return useQuery({ queryKey: keys.essentials, queryFn: api.essentials })
}

export function useHousehold() {
  return useQuery({ queryKey: keys.household, queryFn: api.household })
}

export function useReminders() {
  return useQuery({ queryKey: keys.reminders, queryFn: api.reminders })
}

export function useBackup() {
  return useQuery({ queryKey: keys.backup, queryFn: api.backup })
}

export function useDemoStatus() {
  return useQuery({ queryKey: keys.demo, queryFn: api.demoStatus })
}

export function useImportSettings() {
  return useQuery({ queryKey: keys.importSettings, queryFn: api.importSettings })
}
