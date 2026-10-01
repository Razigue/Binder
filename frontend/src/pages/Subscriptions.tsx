import { Link } from "react-router-dom"
import { TrendingUp } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { PageHeader } from "@/components/layout/AppLayout"
import { useSubscriptions } from "@/hooks/queries"
import { useT } from "@/i18n"
import type { Translate } from "@/i18n/core"
import { subscriptions as messages } from "@/i18n/messages/subscriptions"
import type { Subscription } from "@/lib/api"
import { categoryLabel, formatAmount, formatDate, formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

type T = Translate<(typeof messages)["en"]>

// Cadence identifiers sent by the backend (subscriptions are computed on the fly, never stored).
const CADENCES = ["monthly", "bimonthly", "quarterly", "half_yearly", "yearly", "irregular"] as const

function cadenceLabel(t: T, cadence: string): string {
  const key = CADENCES.find((c) => c === cadence)
  return key ? t(`cadence.${key}`) : cadence
}

export function SubscriptionsPage() {
  const t = useT(messages)
  const { data, isPending } = useSubscriptions()
  const yearly = (data ?? []).reduce((sum, s) => sum + (s.yearly_estimate ?? 0), 0)
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : !data?.length ? (
        <Card className="p-10 text-center text-sm text-muted-foreground">{t("empty")}</Card>
      ) : (
        <>
          {yearly > 0 && (
            <p className="mb-4 text-sm text-muted-foreground">
              {t("yearly")} <span className="font-semibold text-foreground">{formatAmount(Math.round(yearly))}</span>
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {data.map((s) => (
              <SubscriptionCard key={s.key} sub={s} t={t} />
            ))}
          </div>
        </>
      )}
    </>
  )
}

function SubscriptionCard({ sub, t }: { sub: Subscription; t: T }) {
  const max = Math.max(...sub.history.map((p) => p.amount))
  const last = sub.history.at(-1)!
  return (
    <Card className={cn("gap-4 p-5", sub.increase && "border-amber-200 dark:border-amber-500/40")}>
      <div className="flex items-start gap-3">
        <CategoryIcon category={sub.category} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{sub.label}</p>
          <p className="text-xs text-muted-foreground">
            {categoryLabel(sub.category)} · {cadenceLabel(t, sub.cadence)} · {t("documents", { count: sub.history.length })}
          </p>
        </div>
        <div className="text-right">
          <p className="font-semibold tabular-nums">{formatAmount(sub.last_amount)}</p>
          {sub.yearly_estimate && (
            <p className="text-xs text-muted-foreground">
              {t("perYear", { amount: formatAmount(Math.round(sub.yearly_estimate)) })}
            </p>
          )}
        </div>
      </div>
      {sub.increase && (
        <p className="flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
          <TrendingUp className="size-4 shrink-0" />
          {t("increase", {
            pct: formatNumber(Math.round(sub.change_pct)),
            last: formatAmount(sub.last_amount),
            previous: formatAmount(sub.previous_amount),
          })}
        </p>
      )}
      <div role="group" className="flex h-16 items-end gap-1.5" aria-label={t("history")}>
        {sub.history.map((p) => (
          <Link
            key={p.document_id}
            to={`/documents/${p.document_id}`}
            title={`${formatDate(p.date)} · ${formatAmount(p.amount)}`}
            aria-label={`${formatDate(p.date)} · ${formatAmount(p.amount)}`}
            className={cn(
              "min-w-3 flex-1 rounded-t bg-primary/25 hover:bg-primary/50",
              p === last && (sub.increase ? "bg-amber-400 hover:bg-amber-500" : "bg-primary/60"),
            )}
            style={{ height: `${Math.max(8, (p.amount / max) * 100)}%` }}
          />
        ))}
      </div>
      <p className="-mt-2 flex justify-between gap-4 text-[11px] text-muted-foreground tabular-nums">
        <span>
          {formatDate(sub.history[0].date)} · {formatAmount(sub.history[0].amount)}
        </span>
        <span className="text-right">
          {formatDate(last.date)} · <span className="font-medium text-foreground">{formatAmount(last.amount)}</span>
        </span>
      </p>
    </Card>
  )
}
