import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Viewer } from "@/components/viewer"
import { useT } from "@/i18n"
import { documentDetail } from "@/i18n/messages/documentDetail"
import { api, previewUrl, type Doc } from "@/lib/api"
import { fieldLabel } from "@/lib/format"

// An A4 page until the image tells its own proportions.
const A4 = 297 / 210

/** A page of the document, with the places Binder read each field outlined; the `active`
 * field is highlighted and its page brought into view. Zoom and drag in the `Viewer`. */
export function DocumentPage({ doc, active, className }: { doc: Doc; active: string | null; className?: string }) {
  const t = useT(documentDetail)
  const [page, setPage] = useState(0)
  const [aspect, setAspect] = useState(A4)
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

  const pager = pages > 1 && (
    <>
      <Button
        variant="ghost"
        size="icon-sm"
        disabled={page === 0}
        onClick={() => setPage((p) => p - 1)}
        aria-label={t("previousPage")}
      >
        <CaretLeftIcon />
      </Button>
      <span aria-hidden className="tabular-nums">
        {page + 1} / {pages}
      </span>
      <span role="status" className="sr-only">
        {t("pageOf", { page: page + 1, total: pages })}
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
    </>
  )

  return (
    <Viewer aspect={aspect} extra={pager} className={className}>
      {/* White backing on purpose: it is a picture of a paper page, in both themes. */}
      <img
        src={previewUrl(doc.id, page)}
        alt={t("previewAlt", { title: doc.title, page: page + 1 })}
        draggable={false}
        onLoad={(e) => {
          const img = e.currentTarget
          if (img.naturalWidth) setAspect(img.naturalHeight / img.naturalWidth)
        }}
        className="block w-full rounded bg-white shadow-sm dark:brightness-[0.88]"
      />
      {boxes.map((b, i) => (
        <span
          key={i}
          title={`${fieldLabel(b.field)} · ${t("sourceHint")}`}
          className={
            b.field === active
              ? "pointer-events-none absolute rounded-sm bg-amber-300/40 ring-2 ring-amber-500 transition-colors"
              : "pointer-events-none absolute rounded-sm bg-paper-ink/5 ring-1 ring-paper-ink/25 transition-colors"
          }
          style={{
            left: `${b.x0 * 100 - 0.4}%`,
            top: `${b.y0 * 100 - 0.3}%`,
            width: `${(b.x1 - b.x0) * 100 + 0.8}%`,
            height: `${(b.y1 - b.y0) * 100 + 0.6}%`,
          }}
        />
      ))}
    </Viewer>
  )
}
