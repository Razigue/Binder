import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { AgentProvider } from "@/components/agent"
import { AppLayout } from "@/components/layout/AppLayout"
import { UploadProvider } from "@/components/upload"
import { DeadlinesPage } from "@/pages/Deadlines"
import { DocumentDetailPage } from "@/pages/DocumentDetail"
import { DocumentsPage } from "@/pages/Documents"
import { HomePage } from "@/pages/Home"
import { SearchPage } from "@/pages/Search"

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
