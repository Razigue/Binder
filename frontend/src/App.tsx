import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { AgentProvider } from "@/components/agent"
import { AppLayout } from "@/components/layout/AppLayout"
import { UploadProvider } from "@/components/upload"
import { DeadlinesPage } from "@/pages/Deadlines"
import { DocumentDetailPage } from "@/pages/DocumentDetail"
import { DocumentsPage } from "@/pages/Documents"
import { FoldersPage } from "@/pages/Folders"
import { HistoryPage } from "@/pages/History"
import { LettersPage } from "@/pages/Letters"
import { HomePage } from "@/pages/Home"
import { SearchPage } from "@/pages/Search"
import { SettingsPage } from "@/pages/Settings"
import { SortingPage } from "@/pages/Sorting"
import { SubscriptionsPage } from "@/pages/Subscriptions"
import { TrashPage } from "@/pages/Trash"

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: true } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <UploadProvider>
          <AgentProvider>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<HomePage />} />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="documents/:id" element={<DocumentDetailPage />} />
                <Route path="echeances" element={<DeadlinesPage />} />
                <Route path="recherche" element={<SearchPage />} />
                <Route path="historique" element={<HistoryPage />} />
                <Route path="dossiers" element={<FoldersPage />} />
                <Route path="courriers" element={<LettersPage />} />
                <Route path="abonnements" element={<SubscriptionsPage />} />
                <Route path="tri" element={<SortingPage />} />
                <Route path="reglages" element={<SettingsPage />} />
                <Route path="corbeille" element={<TrashPage />} />
                <Route path="*" element={<HomePage />} />
              </Route>
            </Routes>
          </AgentProvider>
        </UploadProvider>
        <Toaster position="bottom-right" />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
