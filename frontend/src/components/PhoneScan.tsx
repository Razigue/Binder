import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CircleAlert, Loader2, ScanLine, Smartphone, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { phoneScan } from "@/i18n/messages/phoneScan"
import { api, scanThumbUrl, type ScanSession } from "@/lib/api"
import { cn } from "@/lib/utils"

// Session calls run one after the other: under StrictMode, the close sent by the first unmount
// must reach the server before the session of the second mount is opened.
let pending: Promise<unknown> = Promise.resolve()
function serial<T>(call: () => Promise<T>): Promise<T> {
  const next = pending.then(call, call)
  pending = next.catch(() => undefined)
  return next
}

/** Phone scanning: QR code to open the scanner on the phone, pages received live. */
export function PhoneScanPanel({ onImported, onCancel }: { onImported: (ids: number[]) => void; onCancel: () => void }) {
  const t = useT(phoneScan)
  const [opened, setOpened] = useState<ScanSession | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [importing, setImporting] = useState(false)
  const done = useRef(false)

  useEffect(() => {
    let alive = true
    serial(api.openScan)
      .then((s) => alive && setOpened(s))
      .catch((e: Error) => alive && setError(e.message))
    return () => {
      alive = false
      // Leaving without importing discards the pages and closes the server.
      if (!done.current) void serial(api.closeScan)
    }
  }, [attempt])

  const live = useQuery({
    queryKey: ["scan-session", opened?.url],
    queryFn: api.scanSession,
    enabled: !!opened && !error,
    refetchInterval: 1200,
    initialData: opened ?? undefined,
  })
  const session = live.data ?? opened

  // Sent from the phone, or imported from here: hand the documents over and close the server.
  const imported = session?.imported
  useEffect(() => {
    if (!imported || done.current) return
    done.current = true
    void serial(api.closeScan)
    onImported(imported)
  }, [imported, onImported])

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" /> {error}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>
            {t("cancel")}
          </Button>
          <Button
            onClick={() => {
              setError(null)
              setAttempt((n) => n + 1)
            }}
          >
            {t("retry")}
          </Button>
        </div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="flex h-64 items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> {t("opening")}
      </div>
    )
  }

  const documents = session.documents
  const pageCount = documents.reduce((n, d) => n + d.length, 0)

  const importNow = () => {
    setImporting(true)
    api
      .importScan()
      .then((s) => live.refetch().then(() => s))
      .catch((e: Error) => setError(e.message))
      .finally(() => setImporting(false))
  }

  return (
    <div className="space-y-5">
      <div className={cn("grid items-center gap-5", pageCount ? "grid-cols-[112px_1fr]" : "sm:grid-cols-[208px_1fr]")}>
        <div className="mx-auto w-full max-w-52 rounded-xl border bg-white p-1.5 shadow-xs">
          <img src={session.qr_code} alt={session.url} className="block aspect-square w-full [image-rendering:pixelated]" />
        </div>
        <div className="min-w-0 space-y-3">
          <PhoneStatus connected={session.phone_connected} />
          {pageCount === 0 ? (
            <ol className="space-y-2.5 text-sm">
              {(["stepWifi", "stepScan", "stepWarning", "stepShoot"] as const).map((key, i) => (
                <li key={key} className="flex gap-2.5">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary tabular-nums">
                    {i + 1}
                  </span>
                  <span className={cn(key === "stepWarning" && "text-muted-foreground")}>{t(key)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">{t("stepShoot")}</p>
          )}
          <p className="truncate font-mono text-[11px] text-muted-foreground select-all" title={session.url}>
            {session.url.split("/?")[0]}
          </p>
        </div>
      </div>

      {pageCount > 0 && (
        <div className="space-y-4">
          {documents.map((pages, d) => (
            <section key={d} aria-label={t("document", { n: d + 1 })}>
              <p className="mb-2 text-xs font-medium text-muted-foreground">
                {t("document", { n: d + 1 })} · {t("pages", { count: pages.length })}
              </p>
              <div className="flex flex-wrap gap-2">
                {pages.map((page, i) => (
                  <div
                    key={page.id}
                    className={cn(
                      "group relative h-24 w-[72px] overflow-hidden rounded-md border bg-muted animate-in fade-in zoom-in-95",
                      !page.detected && "ring-2 ring-amber-400",
                    )}
                    title={page.detected ? undefined : t("noOutline")}
                  >
                    <img src={scanThumbUrl(page.id)} alt="" className="h-full w-full object-cover object-top" />
                    <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-[10px] font-semibold text-white tabular-nums">
                      {i + 1}
                    </span>
                    <button
                      type="button"
                      aria-label={t("deletePage", { n: i + 1 })}
                      onClick={() => api.deleteScanPage(page.id).then(() => live.refetch())}
                      className="absolute top-1 right-1 flex size-5 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <div className="flex flex-col-reverse gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground">{t("firewall")}</p>
        <div className="flex shrink-0 justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>
            {t("cancel")}
          </Button>
          <Button disabled={!pageCount || importing} onClick={importNow}>
            {importing ? <Loader2 className="animate-spin" /> : <ScanLine />}
            {pageCount ? t("import", { count: documents.length }) : t("importEmpty")}
          </Button>
        </div>
      </div>
    </div>
  )
}

function PhoneStatus({ connected }: { connected: boolean }) {
  const t = useT(phoneScan)
  return (
    <p className="flex items-center gap-2 text-sm font-medium" role="status" aria-live="polite">
      <span className={cn("size-2.5 shrink-0 rounded-full", connected ? "bg-emerald-500" : "bg-muted-foreground/50")} />
      <Smartphone className="size-4 text-muted-foreground" />
      {connected ? t("connected") : t("waiting")}
    </p>
  )
}
