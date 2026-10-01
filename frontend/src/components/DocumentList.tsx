import { Link } from "react-router-dom"
import { ChevronRight, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useT } from "@/i18n"
import { documentList } from "@/i18n/messages/documentList"
import type { Doc } from "@/lib/api"
import { categoryLabel, formatAmount, formatDate, missingLabel } from "@/lib/format"
import { CategoryIcon } from "./CategoryIcon"

export function StatusBadge({ doc }: { doc: Doc }) {
  const t = useT(documentList)
  if (doc.status === "processing")
    return (
      <Badge variant="secondary">
        <Loader2 className="animate-spin" /> {t("processing")}
      </Badge>
    )
  if (doc.status === "to_review")
    return (
      <Badge className="bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
        {missingLabel(doc.missing_fields)}
      </Badge>
    )
  if (doc.superseded_by !== null) return <Badge variant="secondary">{t("oldVersion")}</Badge>
  return (
    <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">{t("classified")}</Badge>
  )
}

export function DocumentList({ docs, loading, empty }: { docs?: Doc[]; loading?: boolean; empty?: string }) {
  const t = useT(documentList)
  if (loading)
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  if (!docs?.length) return <p className="px-5 py-10 text-center text-sm text-muted-foreground">{empty ?? t("empty")}</p>
  return (
    <ul className="divide-y">
      {docs.map((d) => (
        <li key={d.id}>
          <Link
            to={`/documents/${d.id}`}
            className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3 md:gap-4 hover:bg-muted/40 md:grid-cols-[auto_minmax(0,2fr)_minmax(0,1fr)_110px_100px_150px_auto]"
          >
            <CategoryIcon category={d.category} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{d.status === "processing" ? d.filename : d.title}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {categoryLabel(d.category)}
                {d.issuer ? ` · ${d.issuer}` : ""}
              </span>
            </span>
            {/* Phone: the amount, and the status only when it asks for something. */}
            <span className="flex flex-col items-end gap-1 md:hidden">
              {d.amount !== null && <span className="text-sm font-medium tabular-nums">{formatAmount(d.amount)}</span>}
              {(d.status !== "classified" || d.superseded_by !== null) && <StatusBadge doc={d} />}
            </span>
            <span className="hidden truncate text-xs text-muted-foreground md:block">{d.filename}</span>
            <span className="hidden text-sm text-muted-foreground tabular-nums md:block">{formatDate(d.issue_date)}</span>
            <span className="hidden text-right text-sm font-medium tabular-nums md:block">{formatAmount(d.amount)}</span>
            <span className="hidden md:block">
              <StatusBadge doc={d} />
            </span>
            <ChevronRight className="size-4 text-muted-foreground" />
          </Link>
        </li>
      ))}
    </ul>
  )
}
