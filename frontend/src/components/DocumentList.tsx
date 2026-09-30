import { Link } from "react-router-dom"
import { ChevronRight, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import type { Doc } from "@/lib/api"
import { formatAmount, formatDate, missingLabel } from "@/lib/format"
import { CategoryIcon } from "./CategoryIcon"

export function StatusBadge({ doc }: { doc: Doc }) {
  if (doc.status === "processing")
    return (
      <Badge variant="secondary">
        <Loader2 className="animate-spin" /> Analyse
      </Badge>
    )
  if (doc.status === "to_review")
    return <Badge className="bg-amber-50 text-amber-700">{missingLabel(doc.missing_fields)}</Badge>
  return <Badge className="bg-emerald-50 text-emerald-700">Classé</Badge>
}

export function DocumentList({ docs, loading, empty }: { docs?: Doc[]; loading?: boolean; empty?: string }) {
  if (loading)
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  if (!docs?.length) return <p className="px-5 py-10 text-center text-sm text-muted-foreground">{empty ?? "Aucun document."}</p>
  return (
    <ul className="divide-y">
      {docs.map((d) => (
        <li key={d.id}>
          <Link
            to={`/documents/${d.id}`}
            className="grid grid-cols-[auto_1fr_auto] items-center gap-4 px-5 py-3 hover:bg-muted/40 md:grid-cols-[auto_minmax(0,2fr)_minmax(0,1fr)_110px_100px_150px_auto]"
          >
            <CategoryIcon category={d.category} />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{d.status === "processing" ? d.filename : d.title}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {d.category}
                {d.issuer ? ` · ${d.issuer}` : ""}
              </span>
            </span>
            <span className="hidden truncate text-xs text-muted-foreground md:block">{d.filename}</span>
            <span className="hidden text-sm text-muted-foreground md:block">{formatDate(d.issue_date)}</span>
            <span className="hidden text-right text-sm font-medium md:block">{formatAmount(d.amount)}</span>
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
