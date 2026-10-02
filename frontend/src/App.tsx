import { lazy } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { AgentProvider } from "@/components/agent"
import { PanelsProvider } from "@/components/panels"
import { UndoToasts } from "@/components/undo"
import { I18nProvider } from "@/i18n"
import { AppLayout } from "@/components/layout/AppLayout"
import { UploadProvider } from "@/components/upload"
import { HomePage } from "@/pages/Home"

// To do ships with the app; the other pages load on first visit.
const PapersPage = lazy(() => import("@/pages/Papers").then((m) => ({ default: m.PapersPage })))
const PreparePage = lazy(() => import("@/pages/Prepare").then((m) => ({ default: m.PreparePage })))
const DocumentDetailPage = lazy(() => import("@/pages/DocumentDetail").then((m) => ({ default: m.DocumentDetailPage })))
const HistoryPage = lazy(() => import("@/pages/History").then((m) => ({ default: m.HistoryPage })))
const SettingsPage = lazy(() => import("@/pages/Settings").then((m) => ({ default: m.SettingsPage })))
const TrashPage = lazy(() => import("@/pages/Trash").then((m) => ({ default: m.TrashPage })))

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: true } },
})

/** A life area is now a filter of My papers. */
function AreaRedirect() {
  const { area } = useParams()
  return <Navigate to={`/papers?area=${encodeURIComponent(area ?? "")}`} replace />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <PanelsProvider>
            <UploadProvider>
              <AgentProvider>
                <Routes>
                  <Route element={<AppLayout />}>
                    <Route index element={<HomePage />} />
                    <Route path="papers" element={<PapersPage />} />
                    <Route path="procedures" element={<PreparePage />} />
                    {/* Former addresses (activity log, agent answers, bookmarks). */}
                    <Route path="area/:area" element={<AreaRedirect />} />
                    <Route path="prepare" element={<Navigate to="/procedures" replace />} />
                    <Route path="documents" element={<Navigate to="/papers" replace />} />
                    <Route path="documents/:id" element={<DocumentDetailPage />} />
                    <Route path="history" element={<HistoryPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                    <Route path="trash" element={<TrashPage />} />
                    <Route path="*" element={<HomePage />} />
                  </Route>
                </Routes>
              </AgentProvider>
            </UploadProvider>
          </PanelsProvider>
          <UndoToasts />
          <Toaster position="bottom-right" />
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  )
}
