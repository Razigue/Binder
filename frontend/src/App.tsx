import { lazy } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { AgentProvider } from "@/components/agent"
import { I18nProvider } from "@/i18n"
import { AppLayout } from "@/components/layout/AppLayout"
import { UploadProvider } from "@/components/upload"
import { HomePage } from "@/pages/Home"

// The home page ships with the app; the others load on first visit.
const DeadlinesPage = lazy(() => import("@/pages/Deadlines").then((m) => ({ default: m.DeadlinesPage })))
const DocumentDetailPage = lazy(() => import("@/pages/DocumentDetail").then((m) => ({ default: m.DocumentDetailPage })))
const DocumentsPage = lazy(() => import("@/pages/Documents").then((m) => ({ default: m.DocumentsPage })))
const FoldersPage = lazy(() => import("@/pages/Folders").then((m) => ({ default: m.FoldersPage })))
const HistoryPage = lazy(() => import("@/pages/History").then((m) => ({ default: m.HistoryPage })))
const LettersPage = lazy(() => import("@/pages/Letters").then((m) => ({ default: m.LettersPage })))
const SearchPage = lazy(() => import("@/pages/Search").then((m) => ({ default: m.SearchPage })))
const SettingsPage = lazy(() => import("@/pages/Settings").then((m) => ({ default: m.SettingsPage })))
const SortingPage = lazy(() => import("@/pages/Sorting").then((m) => ({ default: m.SortingPage })))
const SubscriptionsPage = lazy(() => import("@/pages/Subscriptions").then((m) => ({ default: m.SubscriptionsPage })))
const TrashPage = lazy(() => import("@/pages/Trash").then((m) => ({ default: m.TrashPage })))

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: true } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <UploadProvider>
            <AgentProvider>
              <Routes>
                <Route element={<AppLayout />}>
                  <Route index element={<HomePage />} />
                  <Route path="documents" element={<DocumentsPage />} />
                  <Route path="documents/:id" element={<DocumentDetailPage />} />
                  <Route path="deadlines" element={<DeadlinesPage />} />
                  <Route path="search" element={<SearchPage />} />
                  <Route path="history" element={<HistoryPage />} />
                  <Route path="folders" element={<FoldersPage />} />
                  <Route path="letters" element={<LettersPage />} />
                  <Route path="subscriptions" element={<SubscriptionsPage />} />
                  <Route path="sorting" element={<SortingPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="trash" element={<TrashPage />} />
                  <Route path="*" element={<HomePage />} />
                </Route>
              </Routes>
            </AgentProvider>
          </UploadProvider>
          <Toaster position="bottom-right" />
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  )
}
