import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowRight, CheckCircle2, CircleAlert, FileText, Loader2, Smartphone, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { useDocument, useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { phoneScan } from "@/i18n/messages/phoneScan"
import { upload } from "@/i18n/messages/upload"
import { api, previewUrl, type Doc } from "@/lib/api"
import { categoryLabel, formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"
import { PhoneScanPanel } from "./PhoneScan"
import { LocalBadge } from "./StatusDot"

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
  const [scanning, setScanning] = useState(false)
  const invalidate = useInvalidateAll()
  const scanT = useT(phoneScan)

  const uploadFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files)
      if (!list.length) return
      setOpen(true)
      const fresh = list.map((file, i) => ({ key: `${Date.now()}-${i}-${file.name}`, name: file.name, file }))
      setItems((prev) => [...fresh.map(({ key, name }) => ({ key, name })), ...prev])
      for (const { file, ...item } of fresh) {
        api
          .upload(file)
          .then((doc) => setItems((prev) => prev.map((it) => (it.key === item.key ? { ...it, doc } : it))))
          .catch((err: Error) =>
            setItems((prev) => prev.map((it) => (it.key === item.key ? { ...it, error: err.message } : it))),
          )
          .finally(invalidate)
      }
    },
    [invalidate],
  )

  // Documents sent from the phone: followed like uploaded files.
  const onScanned = useCallback(
    (ids: number[]) => {
      setScanning(false)
      const fresh = ids.map((id) => ({ key: `scan-${id}`, name: scanT("title") }))
      setItems((prev) => [...fresh, ...prev])
      for (const [i, id] of ids.entries()) {
        api
          .document(id)
          .then((doc) =>
            setItems((prev) => prev.map((it) => (it.key === fresh[i].key ? { ...it, name: doc.filename, doc } : it))),
          )
          .catch((err: Error) =>
            setItems((prev) => prev.map((it) => (it.key === fresh[i].key ? { ...it, error: err.message } : it))),
          )
      }
      invalidate()
    },
    [invalidate, scanT],
  )

  const onOpenChange = (open: boolean) => {
    setOpen(open)
    if (!open) {
      setItems([])
      setScanning(false)
    }
  }

  const scanWithPhone = useCallback(() => {
    setOpen(true)
    setScanning(true)
  }, [])

  return (
    <UploadContext.Provider value={{ open: () => setOpen(true), uploadFiles, scanWithPhone }}>
      {children}
      <Dialog open={isOpen} onOpenChange={onOpenChange}>
        <DialogContent className={cn("max-h-[90vh] gap-5 overflow-y-auto", scanning ? "sm:max-w-2xl" : "sm:max-w-xl")}>
          <DialogHeader>
            <DialogTitle className="text-lg">{scanning ? scanT("title") : t("title")}</DialogTitle>
            <DialogDescription className="sr-only">
              {scanning ? scanT("description") : t("description")}
            </DialogDescription>
          </DialogHeader>
          {scanning ? (
            <PhoneScanPanel onImported={onScanned} onCancel={() => setScanning(false)} />
          ) : (
            <>
              <DropZone compact={items.length > 0} />
              {items.length === 1 && <AnalysisCard item={items[0]} onDone={() => onOpenChange(false)} />}
              {items.length > 1 && (
                <div className="divide-y rounded-xl border">
                  {items.map((item) => (
                    <UploadRow key={item.key} item={item} onDone={() => onOpenChange(false)} />
                  ))}
                </div>
              )}
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <LocalBadge /> · {t("local")}
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
      <FileText className={cn("text-primary", compact ? "size-5" : "size-8")} strokeWidth={1.5} />
      <p className="text-sm font-medium">{t("dropHere")}</p>
      <p className="text-xs text-muted-foreground">{t("dropHint")}</p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
          {t("browse")}
        </Button>
        <Button variant="outline" size="sm" onClick={scanWithPhone}>
          <Smartphone /> {scanT("action")}
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

/** Tracks an uploaded document: polls the API until its analysis is done. */
function useTrackedDoc(item: UploadItem) {
  const { data } = useDocument(item.doc?.id ?? null)
  const invalidate = useInvalidateAll()
  const doc = data ?? item.doc
  const done = !!doc && doc.status !== "processing"
  // Analysis runs in the background: refresh counters and lists once it ends.
  useEffect(() => {
    if (done) invalidate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done])
  return doc
}

function AnalysisCard({ item, onDone }: { item: UploadItem; onDone: () => void }) {
  const t = useT(upload)
  const doc = useTrackedDoc(item)
  const navigate = useNavigate()
  const [textStep, setTextStep] = useState(false)
  const finished = !!doc && doc.status !== "processing"

  // Visual progress during analysis; the final steps wait for the real answer.
  useEffect(() => {
    if (finished) return
    const timer = setTimeout(() => setTextStep(true), 700)
    return () => clearTimeout(timer)
  }, [finished])

  if (item.error) return <ErrorBox message={item.error} />

  const keyFields = doc ? [doc.amount, doc.issue_date, doc.due_date, doc.reference].filter((v) => v !== null).length : 0
  const steps = [
    { label: finished ? t("identified", { title: doc!.title }) : t("received"), done: !!doc },
    { label: t("textExtracted"), done: finished || textStep },
    { label: finished ? t("keyFound", { count: keyFields }) : t("keySearching"), done: finished },
    { label: finished ? t("category", { category: categoryLabel(doc!.category) }) : t("classifying"), done: finished },
    {
      label: finished ? (doc!.due_date ? t("due", { date: formatDate(doc!.due_date) }) : t("noDeadline")) : t("deadlines"),
      done: finished,
    },
  ]
  const firstPending = steps.findIndex((s) => !s.done)

  return (
    <div className="grid gap-4 rounded-xl border p-5 sm:grid-cols-[1fr_140px]">
      <div>
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <FileText className="size-4 text-primary" />
          {finished ? t("finished") : t("analysing")}
        </p>
        <ul className="space-y-2.5">
          {steps.map((s, i) => (
            <li key={i} className={cn("flex items-center gap-2 text-sm", !s.done && "text-muted-foreground")}>
              {s.done ? (
                <CheckCircle2 className="size-4 shrink-0 fill-emerald-500 text-white dark:text-card" />
              ) : i === firstPending ? (
                <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
              ) : (
                <span className="size-4 shrink-0 rounded-full border-2 border-border" />
              )}
              <span className="truncate">{s.label}</span>
            </li>
          ))}
        </ul>
        {finished && doc!.status === "to_review" && (
          <p className="mt-3 text-xs text-amber-700 dark:text-amber-400">{t("toCheck")}</p>
        )}
        <Button
          className="mt-5"
          disabled={!finished}
          onClick={() => {
            onDone()
            navigate(`/documents/${doc!.id}`)
          }}
        >
          <ArrowRight /> {t("seeResult")}
        </Button>
      </div>
      <div className="hidden overflow-hidden rounded-lg border bg-muted/40 sm:block">
        {doc && <img src={previewUrl(doc.id)} alt="" className="h-full w-full object-cover object-top" />}
      </div>
    </div>
  )
}

function UploadRow({ item, onDone }: { item: UploadItem; onDone: () => void }) {
  const t = useT(upload)
  const doc = useTrackedDoc(item)
  const navigate = useNavigate()
  const processing = !item.error && (!doc || doc.status === "processing")
  return (
    <div className="flex items-center gap-3 px-4 py-3 text-sm">
      {item.error ? (
        <CircleAlert className="size-4 text-destructive" />
      ) : processing ? (
        <Loader2 className="size-4 animate-spin text-primary" />
      ) : (
        <CheckCircle2 className="size-4 fill-emerald-500 text-white dark:text-card" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{doc && !processing ? doc.title : item.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {item.error ??
            (processing
              ? t("analysing")
              : `${categoryLabel(doc!.category)}${doc!.status === "to_review" ? ` · ${t("toCheckShort")}` : ""}`)}
        </p>
      </div>
      {doc && !processing && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            onDone()
            navigate(`/documents/${doc.id}`)
          }}
        >
          {t("open")}
        </Button>
      )}
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
      <CircleAlert className="size-4" /> {message}
    </div>
  )
}

export function ImportButton() {
  const t = useT(upload)
  const { open } = useUpload()
  return (
    <Button onClick={open}>
      <Upload /> {t("import")}
    </Button>
  )
}
