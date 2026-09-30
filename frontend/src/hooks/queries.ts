import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, type Category, type DocPatch, type DocumentStatus } from "@/lib/api"

export const keys = {
  stats: ["stats"] as const,
  status: ["status"] as const,
  documents: (p: object) => ["documents", p] as const,
  document: (id: number) => ["document", id] as const,
  deadlines: (p: object) => ["deadlines", p] as const,
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
    // Tant qu'un document est en cours d'analyse, on rafraîchit la liste.
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
