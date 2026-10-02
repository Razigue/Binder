import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react"
import { WarningCircleIcon, FileTextIcon, CircleNotchIcon, LockIcon, DeviceMobileIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { phoneScan } from "@/i18n/messages/phoneScan"
import { upload } from "@/i18n/messages/upload"
import { api, type Doc } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ReportView } from "./panels"
import { PhoneScanPanel } from "./PhoneScan"

export const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"

interface UploadItem {
  key: string
  name: string
  doc?: Doc
  error?: string
}

interface UploadContextValue {
  open: () => void
  uploadFiles: (files: FileList | File[]) => void
  scanWithPhone: () => void
}

const UploadContext = createContext<UploadContextValue | null>(null)

export function useUpload() {
  const ctx = useContext(UploadContext)
  if (!ctx) throw new Error("useUpload must be used inside UploadProvider")
  return ctx
}

export function UploadProvider({ children }: { children: ReactNode }) {
  const t = useT(upload)
  const [isOpen, setOpen] = useState(false)
  const [items, setItems] = useState<UploadItem[]>([])
  // Files dropped together form one import, reported together.
  const [batch, setBatch] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const invalidate = useInvalidateAll()
  const scanT = useT(phoneScan)

  const uploadFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files)
      if (!list.length) return
      setOpen(true)
      const id = crypto.randomUUID().replace(/-/g, "").slice(0, 16)
      setBatch(`upload-${id}`)
      const fresh = list.map((file, i) => ({ key: `${Date.now()}-${i}-${file.name}`, name: file.name, file }))
      setItems(fresh.map(({ key, name }) => ({ key, name })))
      for (const { file, ...item } of fresh) {
        api
          .upload(file, id)
          .then((doc) => setItems((prev) => prev.map((it) => (it.key === item.key ? { ...it, doc } : it))))
          .catch((err: Error) =>
            setItems((prev) => prev.map((it) => (it.key === item.key ? { ...it, error: err.message } : it))),
          )
          .finally(invalidate)
      }
    },
    [invalidate],
  )

  // Documents sent from the phone: reported like uploaded files.
  const onScanned = useCallback(
    (ids: number[]) => {
      setScanning(false)
      setItems([])
      if (ids.length)
        api
          .document(ids[0])
          .then((doc) => setBatch(doc.batch))
          .catch(() => setBatch(null))
      invalidate()
    },
    [invalidate],
  )

  const onOpenChange = (open: boolean) => {
    setOpen(open)
    if (!open) {
      if (batch) api.reportSeen(batch).finally(invalidate)
      setItems([])
      setBatch(null)
      setScanning(false)
    }
  }

  const scanWithPhone = useCallback(() => {
    setOpen(true)
    setScanning(true)
  }, [])

  const failed = items.filter((it) => it.error)
  const sent = items.some((it) => it.doc)

  return (
    <UploadContext.Provider value={{ open: () => setOpen(true), uploadFiles, scanWithPhone }}>
      {children}
      <Dialog open={isOpen} onOpenChange={onOpenChange}>
        <DialogContent className={cn("max-h-[90vh] gap-5 overflow-y-auto", scanning ? "sm:max-w-2xl" : "sm:max-w-xl")}>
          <DialogHeader>
            <DialogTitle className="text-lg">{scanning ? scanT("title") : batch ? t("reportTitle") : t("title")}</DialogTitle>
            <DialogDescription className="sr-only">
              {scanning ? scanT("description") : t("description")}
            </DialogDescription>
          </DialogHeader>
          {scanning ? (
            <PhoneScanPanel onImported={onScanned} onCancel={() => setScanning(false)} />
          ) : (
            <>
              {!batch && <DropZone />}
              {failed.map((it) => (
                <ErrorBox key={it.key} message={`${it.name} · ${it.error}`} />
              ))}
              {batch && (sent || !items.length) && <ReportView batch={batch} onNavigate={() => onOpenChange(false)} />}
              {/* Mounted before the upload starts, so screen readers hear the change. */}
              <div role="status">
                {batch && !sent && items.length > failed.length && (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <CircleNotchIcon className="size-4 animate-spin" /> {t("analysing")}
                  </p>
                )}
              </div>
              {batch && (
                <div className="flex justify-between gap-2">
                  <DropZone compact className="flex-1" />
                </div>
              )}
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <LockIcon className="size-3.5" /> {t("local")}
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </UploadContext.Provider>
  )
}

export function DropZone({ compact = false, className }: { compact?: boolean; className?: string }) {
  const t = useT(upload)
  const scanT = useT(phoneScan)
  const { uploadFiles, scanWithPhone } = useUpload()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        uploadFiles(e.dataTransfer.files)
      }}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-muted/30 text-center transition-colors",
        compact ? "px-4 py-5" : "px-6 py-10",
        over && "border-primary/50 bg-accent",
        className,
      )}
    >
      <FileTextIcon className={cn("text-primary", compact ? "size-5" : "size-8")} weight="light" />
      <p className="text-sm font-medium">{t("dropHere")}</p>
      <p className="text-xs text-muted-foreground">{t("dropHint")}</p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
          {t("browse")}
        </Button>
        <Button variant="outline" size="sm" onClick={scanWithPhone}>
          <DeviceMobileIcon /> {scanT("action")}
        </Button>
      </div>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files) uploadFiles(e.target.files)
          e.target.value = ""
        }}
      />
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
      <WarningCircleIcon className="size-4" /> {message}
    </div>
  )
}
