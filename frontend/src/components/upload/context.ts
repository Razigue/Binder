import { createContext, use } from "react"

interface UploadContextValue {
  open: () => void
  uploadFiles: (files: FileList | File[]) => void
  scanWithPhone: () => void
}

export const UploadContext = createContext<UploadContextValue | null>(null)

export function useUpload() {
  const ctx = use(UploadContext)
  if (!ctx) throw new Error("useUpload must be used inside UploadProvider")
  return ctx
}
