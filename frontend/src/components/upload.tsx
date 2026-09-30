import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowRight, CheckCircle2, CircleAlert, FileText, Loader2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { useDocument, useInvalidateAll } from "@/hooks/queries"
import { api, previewUrl, type Doc } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"
import { LocalBadge } from "./StatusDot"

const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"

interface UploadItem {
  key: string
  file: File
  doc?: Doc
  error?: string
}

interface UploadContextValue {
  open: () => void
  uploadFiles: (files: FileList | File[]) => void
}

const UploadContext = createContext<UploadContextValue | null>(null)

export function useUpload() {
  const ctx = useContext(UploadContext)
  if (!ctx) throw new Error("useUpload hors de UploadProvider")
  return ctx
}

export function UploadProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false)
  const [items, setItems] = useState<UploadItem[]>([])
  const invalidate = useInvalidateAll()

  const uploadFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files)
      if (!list.length) return
      setOpen(true)
      const fresh = list.map((file, i) => ({ key: `${Date.now()}-${i}-${file.name}`, file }))
      setItems((prev) => [...fresh, ...prev])
      for (const item of fresh) {
        api
          .upload(item.file)
          .then((doc) => setItems((prev) => prev.map((it) => (it.key === item.key ? { ...it, doc } : it))))
          .catch((err: Error) =>
            setItems((prev) => prev.map((it) => (it.key === item.key ? { ...it, error: err.message } : it))),
          )
          .finally(invalidate)
      }
    },
    [invalidate],
  )

  const onOpenChange = (open: boolean) => {
    setOpen(open)
    if (!open) setItems([])
  }

  return (
    <UploadContext.Provider value={{ open: () => setOpen(true), uploadFiles }}>
      {children}
      <Dialog open={isOpen} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] gap-5 overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-lg">Importer un document</DialogTitle>
            <DialogDescription className="sr-only">Déposez des PDF ou des photos à analyser.</DialogDescription>
          </DialogHeader>
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
            <LocalBadge /> · Vos données restent sur votre machine
          </p>
        </DialogContent>
      </Dialog>
    </UploadContext.Provider>
  )
}

export function DropZone({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { uploadFiles } = useUpload()
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
      <p className="text-sm font-medium">Déposez vos documents ici</p>
      <p className="text-xs text-muted-foreground">PDF, JPG, PNG · Ils restent sur votre machine.</p>
      <Button variant="outline" size="sm" className="mt-2" onClick={() => input.current?.click()}>
        Parcourir les fichiers
      </Button>
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

/** Suivi d'un document : interroge l'API tant que l'analyse n'est pas terminée. */
function useTrackedDoc(item: UploadItem) {
  const { data } = useDocument(item.doc?.id ?? null)
  const invalidate = useInvalidateAll()
  const doc = data ?? item.doc
  const done = !!doc && doc.status !== "processing"
  // L'analyse tourne en tâche de fond : on rafraîchit compteurs et listes à la fin.
  useEffect(() => {
    if (done) invalidate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done])
  return doc
}

function AnalysisCard({ item, onDone }: { item: UploadItem; onDone: () => void }) {
  const doc = useTrackedDoc(item)
  const navigate = useNavigate()
  const [tick, setTick] = useState(0)
  const finished = !!doc && doc.status !== "processing"

  // Progression visuelle pendant l'analyse ; les étapes finales attendent la vraie réponse.
  useEffect(() => {
    if (finished) return
    const t = setInterval(() => setTick((n) => n + 1), 700)
    return () => clearInterval(t)
  }, [finished])

  if (item.error) return <ErrorBox message={item.error} />

  const keyFields = doc ? [doc.amount, doc.issue_date, doc.due_date, doc.reference].filter((v) => v !== null).length : 0
  const steps = [
    { label: finished ? `Document identifié : ${doc!.title}` : "Document reçu", done: !!doc },
    { label: "Texte extrait", done: finished || tick >= 1 },
    { label: finished ? `Informations clés trouvées (${keyFields})` : "Recherche des informations clés", done: finished },
    { label: finished ? `Catégorie : ${doc!.category}` : "Classement", done: finished },
    {
      label: finished ? (doc!.due_date ? `Échéance : ${formatDate(doc!.due_date)}` : "Aucune échéance") : "Échéances",
      done: finished,
    },
  ]
  const firstPending = steps.findIndex((s) => !s.done)

  return (
    <div className="grid gap-4 rounded-xl border p-5 sm:grid-cols-[1fr_140px]">
      <div>
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <FileText className="size-4 text-primary" />
          {finished ? "Analyse terminée" : "Analyse en cours…"}
        </p>
        <ul className="space-y-2.5">
          {steps.map((s, i) => (
            <li key={i} className={cn("flex items-center gap-2 text-sm", !s.done && "text-muted-foreground")}>
              {s.done ? (
                <CheckCircle2 className="size-4 shrink-0 fill-emerald-500 text-white" />
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
          <p className="mt-3 text-xs text-amber-700">Quelques informations sont à vérifier.</p>
        )}
        <Button
          className="mt-5"
          disabled={!finished}
          onClick={() => {
            onDone()
            navigate(`/documents/${doc!.id}`)
          }}
        >
          <ArrowRight /> Voir le résultat
        </Button>
      </div>
      <div className="hidden overflow-hidden rounded-lg border bg-muted/40 sm:block">
        {doc && <img src={previewUrl(doc.id)} alt="" className="h-full w-full object-cover object-top" />}
      </div>
    </div>
  )
}

function UploadRow({ item, onDone }: { item: UploadItem; onDone: () => void }) {
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
        <CheckCircle2 className="size-4 fill-emerald-500 text-white" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{doc && !processing ? doc.title : item.file.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {item.error ?? (processing ? "Analyse en cours…" : `${doc!.category}${doc!.status === "to_review" ? " · à vérifier" : ""}`)}
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
          Ouvrir
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
  const { open } = useUpload()
  return (
    <Button onClick={open}>
      <Upload /> Importer
    </Button>
  )
}
