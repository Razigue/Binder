import { useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { MagnifyingGlassIcon, TrendUpIcon } from "@phosphor-icons/react"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { DocumentsByYear, matches } from "@/components/documents"
import { Timeline } from "@/components/timeline"
import { Upcoming } from "@/components/upcoming"
import { FeedCard } from "@/components/feed"
import { PrepareCard } from "@/components/prepare"
import { PageHeader } from "@/components/layout/AppLayout"
import { ImportButton } from "@/components/upload"
import { useT } from "@/i18n"
import { area as messages } from "@/i18n/messages/area"
import { AREAS, api, type Area, type Doc, type Subscription } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { formatAmount, formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

export function AreaPage() {
  const t = useT(messages)
  const param = useParams().area as Area
  const area = AREAS.includes(param) ? param : "housing"
  const detail = useQuery({ queryKey: ["area", area], queryFn: () => api.area(area) })
  const data = detail.data
  const [person, setPerson] = useState<string | null>(null)
  const [filter, setFilter] = useState("")

  return (
    <>
      <PageHeader title={t(`area.${area}`)} subtitle={t(`hint.${area}`)} actions={<ImportButton />} />
      {!data ? (
        <Card className="gap-3 p-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </Card>
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]">
          <div className="min-w-0 space-y-6">
            {/* The area sends unpaid deadlines up to three months ahead, overdue ones included. */}
            <Timeline deadlines={data.deadlines} back={14} ahead={90} />
            {data.items.length > 0 && (
              <section>
                <h2 className="mb-3 font-semibold">{t("toDo")}</h2>
                <Card className="gap-0 p-0">
                  <ul className="divide-y">
                    {data.items.map((item) => (
                      <FeedCard key={item.key} item={item} />
                    ))}
                  </ul>
                </Card>
              </section>
            )}
            <Documents docs={data.documents} members={data.members.map((m) => m.name)} person={person} onPerson={setPerson} filter={filter} onFilter={setFilter} area={area} />
          </div>
          <aside className="grid items-start gap-6 md:grid-cols-2 xl:grid-cols-1">
            <Upcoming deadlines={data.deadlines} />
            {data.subscriptions.length > 0 && <Subscriptions subscriptions={data.subscriptions} yearlyCost={data.yearly_cost} />}
            <PrepareCard area={area} />
          </aside>
        </div>
      )}
    </>
  )
}

function Subscriptions({ subscriptions, yearlyCost }: { subscriptions: Subscription[]; yearlyCost: number }) {
  const t = useT(messages)
  return (
    <Card className="gap-0 p-0">
      <div className="flex items-baseline justify-between gap-3 px-5 pt-4 pb-3">
        <h2 className="font-semibold">{t("subscriptions")}</h2>
        <span className="text-xs text-muted-foreground">{t("yearly", { amount: formatAmount(yearlyCost) })}</span>
      </div>
      <ul className="divide-y border-t">
        {subscriptions.map((s) => (
          <li key={s.key} className="flex items-center gap-3 px-5 py-3">
            <CategoryIcon category={s.category} size="sm" />
            <span className="min-w-0 flex-1 truncate text-sm font-medium">{s.label}</span>
            {s.increase && (
              <span className="flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400">
                <TrendUpIcon className="size-3.5" />
                {t("increase", { pct: formatNumber(s.change_pct / 100, { style: "percent", maximumFractionDigits: 0 }) })}
              </span>
            )}
            <span className="text-sm tabular-nums">{formatAmount(s.last_amount)}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function Documents({
  docs,
  members,
  person,
  onPerson,
  filter,
  onFilter,
  area,
}: {
  docs: Doc[]
  members: string[]
  person: string | null
  onPerson: (p: string | null) => void
  filter: string
  onFilter: (f: string) => void
  area: Area
}) {
  const t = useT(messages)
  const shown = useMemo(
    () =>
      docs.filter((d) => {
        if (person && !(d.person && (d.person === person || person.split(" ").includes(d.person)))) return false
        return matches(d, filter)
      }),
    [docs, filter, person],
  )
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">
          {t("documents")} <span className="font-normal text-muted-foreground">· {t("count", { count: docs.length })}</span>
        </h2>
        {docs.length > 6 && (
          <div className="relative w-full sm:w-64">
            <MagnifyingGlassIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={filter} onChange={(e) => onFilter(e.target.value)} placeholder={t("filter")} className="pl-9" />
          </div>
        )}
      </div>
      {members.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {[null, ...members].map((m) => (
            <button
              key={m ?? "all"}
              onClick={() => onPerson(m)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                person === m ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
            >
              {m ?? t("everyone")}
            </button>
          ))}
        </div>
      )}
      <Card className="gap-0 p-0">
        {docs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-5 py-10 text-center">
            <AreaIcon area={area} />
            <p className="text-sm font-medium">{t("empty")}</p>
            <p className="text-sm text-muted-foreground">{t("emptyHint")}</p>
          </div>
        ) : shown.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">{t("noMatch")}</p>
        ) : (
          <DocumentsByYear docs={shown} />
        )}
      </Card>
    </section>
  )
}
