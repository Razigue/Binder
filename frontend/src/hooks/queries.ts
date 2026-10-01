import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, type Category, type DocPatch, type DocumentStatus } from "@/lib/api"

export const keys = {
  stats: ["stats"] as const,
  status: ["status"] as const,
  documents: (p: object) => ["documents", p] as const,
  document: (id: number) => ["document", id] as const,
  deadlines: (p: object) => ["deadlines", p] as const,
  trash: ["trash"] as const,
  expirations: ["expirations"] as const,
  retention: ["retention"] as const,
  activity: (p: object) => ["activity", p] as const,
}

export function useStatus() {
  return useQuery({ queryKey: keys.status, queryFn: api.status, refetchInterval: 30_000 })
}

export function useStats() {
  return useQuery({ queryKey: keys.stats, queryFn: api.stats })
}

export function useDocuments(p: { q?: string; category?: Category; status?: DocumentStatus; limit?: number } = {}) {
  return useQuery({
    queryKey: keys.documents(p),
    queryFn: () => api.documents(p),
    // Refresh the list while a document is being analysed.
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === "processing") ? 1500 : false),
  })
}

export function useDocument(id: number | null) {
  return useQuery({
    queryKey: keys.document(id ?? 0),
    queryFn: () => api.document(id!),
    enabled: id !== null,
    refetchInterval: (q) => (q.state.data?.status === "processing" ? 1000 : false),
  })
}

export function useDeadlines(p: { start?: string; end?: string; include_done?: boolean } = {}) {
  return useQuery({ queryKey: keys.deadlines(p), queryFn: () => api.deadlines(p) })
}

export function useInvalidateAll() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries()
}

export function useUpdateDocument(id: number) {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: (patch: DocPatch) => api.updateDocument(id, patch), onSuccess: invalidate })
}

export function useDeleteDocument() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: api.deleteDocument, onSuccess: invalidate })
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

export function useActivity(p: { document_id?: number; limit?: number } = {}) {
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
  return useQuery({ queryKey: ["subscriptions"], queryFn: api.subscriptions })
}

export function useExpirations() {
  return useQuery({ queryKey: keys.expirations, queryFn: api.expirations })
}

export function useRetention() {
  return useQuery({ queryKey: keys.retention, queryFn: api.retention })
}

export const feedKey = ["feed"] as const

/** The Today feed; refreshed often while the local AI installs, documents arrive in the background. */
export function useFeed() {
  return useQuery({
    queryKey: feedKey,
    queryFn: api.feed,
    refetchInterval: (q) => {
      const phase = q.state.data?.setup.phase
      return phase && phase !== "ready" && phase !== "disabled" ? 2000 : 30_000
    },
  })
}

export function useJourneys() {
  return useQuery({ queryKey: ["journeys"], queryFn: api.journeys })
}

export function useJourneyKinds() {
  return useQuery({ queryKey: ["journeyKinds"], queryFn: api.journeyKinds, staleTime: Infinity })
}

export function useJourney(id: number | null) {
  return useQuery({ queryKey: ["journey", id], queryFn: () => api.journey(id!), enabled: id !== null })
}

/** Letters Binder wrote, most recent first: drafts, sent ones awaiting an answer, answered. */
export function useLetters() {
  return useQuery({ queryKey: ["letters"], queryFn: api.letters })
}

export function useProfile() {
  return useQuery({ queryKey: ["profile"], queryFn: api.profile, staleTime: 60_000 })
}
