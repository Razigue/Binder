import { Link } from "react-router-dom"
import { ChevronRight } from "lucide-react"
import { Card } from "@/components/ui/card"
import { CategoryIcon } from "@/components/CategoryIcon"
import { useExpirations } from "@/hooks/queries"
import type { Expiration } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

const STATES: Record<Expiration["state"], { label: (e: Expiration) => string; pill: string }> = {
  expired: { label: () => "Expiré", pill: "bg-red-50 text-red-700" },
  renew: { label: (e) => `À renouveler · expire dans ${e.days_left} j`, pill: "bg-amber-50 text-amber-700" },
  valid: { label: (e) => `Valide · à renouveler dès le ${formatDate(e.renew_from)}`, pill: "bg-emerald-50 text-emerald-700" },
}

/** Pièces d'identité, attestations, contrôle technique : validité et délai de renouvellement. */
export function ExpirationSection() {
  const { data, isPending } = useExpirations()
  if (isPending || !data?.length) return null
  return (
    <section className="mb-6">
      <h2 className="mb-3 font-semibold">Validité de vos documents</h2>
      <Card className="gap-0 p-0">
        <ul className="divide-y">
          {data.map((e) => {
            const state = STATES[e.state]
            return (
              <li key={e.document.id}>
                <Link to={`/documents/${e.document.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/40">
                  <CategoryIcon category={e.document.category} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{e.document.title}</span>
                    <span className="block text-xs text-muted-foreground">Valable jusqu'au {formatDate(e.expiry_date, "long")}</span>
                  </span>
                  <span className={cn("hidden rounded-full px-2.5 py-1 text-xs font-medium sm:block", state.pill)}>{state.label(e)}</span>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </Link>
              </li>
            )
          })}
        </ul>
      </Card>
    </section>
  )
}
