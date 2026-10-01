import { Link } from "react-router-dom"
import { ChevronRight } from "lucide-react"
import { Card } from "@/components/ui/card"
import { CategoryIcon } from "@/components/CategoryIcon"
import { useExpirations } from "@/hooks/queries"
import { useT } from "@/i18n"
import { expirations } from "@/i18n/messages/expirations"
import type { Expiration } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

const PILLS: Record<Expiration["state"], string> = {
  expired: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300",
  renew: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  valid: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
}

/** Identity papers, certificates, roadworthiness test: validity and when to renew. */
export function ExpirationSection() {
  const t = useT(expirations)
  const { data, isPending } = useExpirations()
  if (isPending || !data?.length) return null

  const label = (e: Expiration) => {
    if (e.state === "expired") return t("expired")
    if (e.state === "renew") return t("renew", { count: e.days_left })
    return t("valid", { date: formatDate(e.renew_from) })
  }

  return (
    <section className="mb-6">
      <h2 className="mb-3 font-semibold">{t("title")}</h2>
      <Card className="gap-0 p-0">
        <ul className="divide-y">
          {data.map((e) => (
            <li key={e.document.id}>
              <Link to={`/documents/${e.document.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/40">
                <CategoryIcon category={e.document.category} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{e.document.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {t("validUntil", { date: formatDate(e.expiry_date, "long") })}
                  </span>
                </span>
                <span className={cn("hidden rounded-full px-2.5 py-1 text-xs font-medium sm:block", PILLS[e.state])}>
                  {label(e)}
                </span>
                <ChevronRight className="size-4 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </section>
  )
}
