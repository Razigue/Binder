import { useState } from "react"
import { Link, useLocation, useNavigate, useParams } from "react-router-dom"
import { ArrowLeftIcon, CaretRightIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAgentViewing } from "@/components/agent/context"
import { InfoPanel } from "@/components/document/InfoPanel"
import { DocumentPage } from "@/components/DocumentPage"
import { useDocument } from "@/hooks/queries"
import { useDocumentTitle } from "@/hooks/useDocumentTitle"
import { useT } from "@/i18n"
import { area as areaMessages } from "@/i18n/messages/area"
import { documentDetail } from "@/i18n/messages/documentDetail"

export function DocumentDetailPage() {
  const t = useT(documentDetail)
  const ta = useT(areaMessages)
  const id = Number(useParams().id)
  const { data: doc, isPending, isError } = useDocument(id)
  useAgentViewing(doc)
  // Field hovered in the panel: its source is highlighted on the page.
  const [active, setActive] = useState<string | null>(null)
  const navigate = useNavigate()
  // The desktop window has no browser back button: return to wherever the document was opened
  // from (Today, a card, a list...). Opened with no history, fall back to its area.
  const hasHistory = useLocation().key !== "default"
  const back = () => (hasHistory ? navigate(-1) : navigate(doc?.area ? `/area/${doc.area}` : "/"))
  useDocumentTitle(doc?.title)

  if (isError)
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        {t("notFound")}{" "}
        <Link to="/" className="text-primary underline">
          {t("backToDocuments")}
        </Link>
      </div>
    )

  return (
    <>
      <div className="mb-5 flex items-center gap-3 text-sm">
        <Button variant="outline" size="sm" onClick={back} className="shrink-0">
          <ArrowLeftIcon /> {t("back")}
        </Button>
        <nav aria-label={t("breadcrumbNav")} className="flex min-w-0 items-center gap-2 text-muted-foreground">
          <Link to={doc?.area ? `/area/${doc.area}` : "/"} className="hover:text-foreground">
            {doc?.area ? ta(`area.${doc.area}`) : t("breadcrumb")}
          </Link>
          <CaretRightIcon className="size-3.5" aria-hidden />
          <span aria-current="page" className="truncate font-medium text-foreground">
            {doc?.title ?? "…"}
          </span>
        </nav>
      </div>
      {isPending || !doc ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <Skeleton className="aspect-[3/4] w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          {/* A fixed height, so the zoomed page scrolls inside its frame and not the whole page. */}
          <Card className="h-[min(82vh,64rem)] gap-0 overflow-hidden p-0">
            <DocumentPage doc={doc} active={active} className="flex-1" />
          </Card>
          <InfoPanel doc={doc} onActive={setActive} />
        </div>
      )}
    </>
  )
}
