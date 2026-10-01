import { useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { CalendarClock, ChevronRight, Loader2, Search, TrendingUp } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { FeedCard } from "@/components/feed"
import { PageHeader } from "@/components/layout/AppLayout"
import { ImportButton } from "@/components/upload"
import { useT } from "@/i18n"
import { area as messages } from "@/i18n/messages/area"
import { AREAS, api, type Area, type Doc } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { daysLabel, docTypeLabel, formatAmount, formatDate, formatNumber, urgency, urgencyStyles } from "@/lib/format"
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
        <div className="space-y-6">
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
          <div className="grid items-start gap-6 lg:grid-cols-2">
            <Upcoming deadlines={data.deadlines} />
            {data.subscriptions.length > 0 && (
              <Card className="gap-0 p-0">
                <div className="flex items-baseline justify-between px-5 pt-4 pb-3">
                  <h2 className="font-semibold">{t("subscriptions")}</h2>
                  <span className="text-xs text-muted-foreground">
                    {t("yearly", { amount: formatAmount(data.yearly_cost) })}
                  </span>
                </div>
                <ul className="divide-y border-t">
                  {data.subscriptions.map((s) => (
                    <li key={s.key} className="flex items-center gap-3 px-5 py-3">
                      <CategoryIcon category={s.category} size="sm" />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{s.label}</span>
                      {s.increase && (
                        <span className="flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400">
                          <TrendingUp className="size-3.5" />
                          {t("increase", {
                            pct: formatNumber(s.change_pct / 100, { style: "percent", maximumFractionDigits: 0 }),
                          })}
                        </span>
                      )}
                      <span className="text-sm tabular-nums">{formatAmount(s.last_amount)}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
          <Documents docs={data.documents} members={data.members.map((m) => m.name)} person={person} onPerson={setPerson} filter={filter} onFilter={setFilter} area={area} />
        </div>
      )}
    </>
  )
}

function Upcoming({ deadlines }: { deadlines: { id: number; title: string; due_date: string; amount: number | null; days_left: number; document_id: number | null }[] }) {
  const t = useT(messages)
  return (
    <Card className="gap-0 p-0">
      <h2 className="px-5 pt-4 pb-3 font-semibold">{t("upcoming")}</h2>
      {deadlines.length === 0 ? (
        <p className="border-t px-5 py-4 text-sm text-muted-foreground">{t("noUpcoming")}</p>
      ) : (
        <ul className="divide-y border-t">
          {deadlines.map((d) => {
            const row = (
              <>
                <CalendarClock className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{d.title}</span>
                  <span className={cn("block text-xs", urgencyStyles[urgency(d.days_left)].text)}>
                    {formatDate(d.due_date)} · {daysLabel(d.days_left)}
                  </span>
                </span>
                <span className="text-sm tabular-nums">{formatAmount(d.amount)}</span>
              </>
            )
            return (
              <li key={d.id}>
                {d.document_id ? (
                  <Link to={`/documents/${d.document_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/40">
                    {row}
                  </Link>
                ) : (
                  <div className="flex items-center gap-3 px-5 py-3">{row}</div>
                )}
              </li>
            )
          })}
        </ul>
      )}
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
  const shown = useMemo(() => {
    const words = filter.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").split(/\s+/).filter(Boolean)
    return docs.filter((d) => {
      if (person && !(d.person && (d.person === person || person.split(" ").includes(d.person)))) return false
      const hay = `${d.title} ${d.issuer ?? ""} ${d.reference ?? ""} ${docTypeLabel(d.doc_type)} ${d.person ?? ""}`
        .toLowerCase()
        .normalize("NFD")
        .replace(/\p{M}/gu, "")
      return words.every((w) => hay.includes(w))
    })
  }, [docs, filter, person])
  // By year, most recent first.
  const years = useMemo(() => {
    const groups = new Map<string, Doc[]>()
    for (const d of shown) {
      const year = (d.issue_date ?? d.due_date ?? d.created_at).slice(0, 4)
      groups.set(year, [...(groups.get(year) ?? []), d])
    }
    return [...groups.entries()].sort((a, b) => b[0].localeCompare(a[0]))
  }, [shown])

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">
          {t("documents")} <span className="font-normal text-muted-foreground">· {t("count", { count: docs.length })}</span>
        </h2>
        {docs.length > 6 && (
          <div className="relative w-full sm:w-64">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
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
          years.map(([year, list]) => (
            <div key={year}>
              <p className="border-b bg-muted/30 px-5 py-1.5 text-xs font-medium text-muted-foreground">{year}</p>
              <ul className="divide-y">
                {list.map((d) => (
                  <li key={d.id}>
                    <Link
                      to={`/documents/${d.id}`}
                      className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3 hover:bg-muted/40"
                    >
                      <CategoryIcon category={d.category} />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">
                          {d.status === "processing" ? (
                            <span className="flex items-center gap-1.5 text-muted-foreground">
                              <Loader2 className="size-3.5 animate-spin" /> {t("analysing")}
                            </span>
                          ) : (
                            d.title
                          )}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {[formatDate(d.issue_date ?? d.created_at), d.person, d.superseded_by !== null ? t("oldVersion") : null, d.status === "to_review" ? t("question") : null]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      <span className="text-sm tabular-nums">{d.amount !== null ? formatAmount(d.amount) : ""}</span>
                      <ChevronRight className="size-4 text-muted-foreground" />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </Card>
    </section>
  )
}
