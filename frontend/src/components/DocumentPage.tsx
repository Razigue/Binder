import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { documentDetail } from "@/i18n/messages/documentDetail"
import { api, previewUrl, type Doc } from "@/lib/api"
import { fieldLabel } from "@/lib/format"
import { cn } from "@/lib/utils"

/** A page of the document, with the places Binder read each field outlined; the `active`
 * field is highlighted and its page brought into view. Click to zoom. */
export function DocumentPage({ doc, active, className }: { doc: Doc; active: string | null; className?: string }) {
  const t = useT(documentDetail)
  const [page, setPage] = useState(0)
  const [zoom, setZoom] = useState(false)
  const pages = Math.max(doc.page_count, 1)
  const sources = useQuery({
    queryKey: ["sources", doc.id, doc.amount, doc.due_date, doc.issue_date, doc.expiry_date, doc.reference, doc.issuer],
    queryFn: () => api.sources(doc.id),
    enabled: doc.status !== "processing",
    staleTime: Infinity,
  })
  const boxes = (sources.data ?? []).flatMap((s) =>
    s.boxes.filter((b) => b.page === page).map((b) => ({ ...b, field: s.field })),
  )
  // The active field's page comes into view.
  const target = sources.data?.find((s) => s.field === active)?.boxes[0]
  useEffect(() => {
    if (target && target.page !== page) setPage(target.page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, target?.page])
  return (
    <div className={cn("flex flex-col", className)}>
      <div className={cn("min-h-0 flex-1 bg-muted/50 p-4", zoom ? "overflow-auto" : "overflow-y-auto")}>
        {/* White backing on purpose: it is a picture of a paper page, in both themes. */}
        <div className={cn("relative mx-auto", zoom ? "w-max" : "w-full")}>
          <img
            src={previewUrl(doc.id, page)}
            alt={t("previewAlt", { title: doc.title, page: page + 1 })}
            onClick={() => setZoom((z) => !z)}
            className={cn("block rounded bg-white shadow-sm dark:brightness-[0.88]", zoom ? "max-w-none cursor-zoom-out" : "w-full cursor-zoom-in")}
          />
          {boxes.map((b, i) => (
            <span
              key={i}
              title={`${fieldLabel(b.field)} · ${t("sourceHint")}`}
              className={cn(
                "pointer-events-none absolute rounded-sm transition-colors",
                b.field === active ? "bg-amber-300/40 ring-2 ring-amber-500" : "bg-primary/5 ring-1 ring-primary/25",
              )}
              style={{
                left: `${b.x0 * 100 - 0.4}%`,
                top: `${b.y0 * 100 - 0.3}%`,
                width: `${(b.x1 - b.x0) * 100 + 0.8}%`,
                height: `${(b.y1 - b.y0) * 100 + 0.6}%`,
              }}
            />
          ))}
        </div>
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 border-t py-2 text-sm">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            aria-label={t("previousPage")}
          >
            <CaretLeftIcon />
          </Button>
          <span className="tabular-nums">
            {page + 1} / {pages}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={page >= pages - 1}
            onClick={() => setPage((p) => p + 1)}
            aria-label={t("nextPage")}
          >
            <CaretRightIcon />
          </Button>
        </div>
      )}
    </div>
  )
}
