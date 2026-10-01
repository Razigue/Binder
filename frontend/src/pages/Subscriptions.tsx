import { Link } from "react-router-dom"
import { TrendingUp } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { PageHeader } from "@/components/layout/AppLayout"
import { useSubscriptions } from "@/hooks/queries"
import type { Subscription } from "@/lib/api"
import { formatAmount, formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

export function SubscriptionsPage() {
  const { data, isPending } = useSubscriptions()
  const yearly = (data ?? []).reduce((sum, s) => sum + (s.yearly_estimate ?? 0), 0)
  return (
    <>
      <PageHeader
        title="Abonnements"
        subtitle="Vos factures récurrentes, regroupées par fournisseur. Binder signale les hausses de plus de 10 %."
      />
      {isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : !data?.length ? (
        <Card className="p-10 text-center text-sm text-muted-foreground">
          Aucun abonnement détecté : il faut au moins deux factures d'un même fournisseur.
        </Card>
      ) : (
        <>
          {yearly > 0 && (
            <p className="mb-4 text-sm text-muted-foreground">
              Estimation annuelle : <span className="font-semibold text-foreground">{formatAmount(Math.round(yearly))}</span>
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {data.map((s) => (
              <SubscriptionCard key={s.key} sub={s} />
            ))}
          </div>
        </>
      )}
    </>
  )
}

function SubscriptionCard({ sub }: { sub: Subscription }) {
  const max = Math.max(...sub.history.map((p) => p.amount))
  const last = sub.history.at(-1)!
  return (
    <Card className={cn("gap-4 p-5", sub.increase && "border-amber-200")}>
      <div className="flex items-start gap-3">
        <CategoryIcon category={sub.category} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{sub.label}</p>
          <p className="text-xs text-muted-foreground">
            {sub.category} · {sub.cadence} · {sub.history.length} documents
          </p>
        </div>
        <div className="text-right">
          <p className="font-semibold tabular-nums">{formatAmount(sub.last_amount)}</p>
          {sub.yearly_estimate && <p className="text-xs text-muted-foreground">≈ {formatAmount(Math.round(sub.yearly_estimate))} / an</p>}
        </div>
      </div>
      {sub.increase && (
        <p className="flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <TrendingUp className="size-4" /> Hausse de {Math.round(sub.change_pct)} % : {formatAmount(sub.last_amount)} contre{" "}
          {formatAmount(sub.previous_amount)} la fois précédente.
        </p>
      )}
      <div className="flex h-16 items-end gap-1.5" aria-label="Historique des montants">
        {sub.history.map((p) => (
          <Link
            key={p.document_id}
            to={`/documents/${p.document_id}`}
            title={`${formatDate(p.date)} · ${formatAmount(p.amount)}`}
            className={cn(
              "min-w-3 flex-1 rounded-t bg-primary/25 hover:bg-primary/50",
              p === last && (sub.increase ? "bg-amber-400 hover:bg-amber-500" : "bg-primary/60"),
            )}
            style={{ height: `${Math.max(8, (p.amount / max) * 100)}%` }}
          />
        ))}
      </div>
      <p className="-mt-2 flex justify-between text-[11px] text-muted-foreground">
        <span>{formatDate(sub.history[0].date)}</span>
        <span>{formatDate(last.date)}</span>
      </p>
    </Card>
  )
}
