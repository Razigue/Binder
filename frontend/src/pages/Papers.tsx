import { useDeferredValue, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import { RobotIcon, MagnifyingGlassIcon, CheckIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useAgent } from "@/components/agent"
import { DocumentsByYear } from "@/components/documents"
import { EssentialsLink } from "@/components/essentials"
import { PageHeader } from "@/components/layout/AppLayout"
import { Timeline } from "@/components/timeline"
import { useDeadlines } from "@/hooks/queries"
import { useT } from "@/i18n"
import { papers as messages } from "@/i18n/messages/papers"
import { AREAS, api, type Area, type AreaSummary } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { currentLocale, formatDate, toIso } from "@/lib/format"
import { cn } from "@/lib/utils"

type Tab = "documents" | "calendar" | "archives"
const TABS: Tab[] = ["documents", "calendar", "archives"]

/** Every paper in one place: the seven life areas with their state in words, then the
 * documents (search reads their content), the calendar and the archives. */
export function PapersPage() {
  const t = useT(messages)
  const [params, setParams] = useSearchParams()
  const tab: Tab = TABS.includes(params.get("tab") as Tab) ? (params.get("tab") as Tab) : "documents"
  const initial = params.get("area")
  const [area, setArea] = useState<Area | null>(AREAS.includes(initial as Area) ? (initial as Area) : null)
  const setTab = (next: Tab) =>
    setParams((p) => {
      p.set("tab", next)
      return p
    })

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div role="tablist" aria-label={t("title")} className="mb-5 flex gap-1 border-b">
        {TABS.map((key, i) => (
          <button
            key={key}
            id={`papers-tab-${key}`}
            role="tab"
            aria-selected={tab === key}
            aria-controls="papers-panel"
            tabIndex={tab === key ? 0 : -1}
            onClick={() => setTab(key)}
            onKeyDown={(e) => {
              // Arrow keys move between tabs; Tab goes on to the panel.
              const next =
                e.key === "ArrowRight" ? (i + 1) % TABS.length
                : e.key === "ArrowLeft" ? (i - 1 + TABS.length) % TABS.length
                : e.key === "Home" ? 0
                : e.key === "End" ? TABS.length - 1
                : null
              if (next === null) return
              e.preventDefault()
              setTab(TABS[next])
              document.getElementById(`papers-tab-${TABS[next]}`)?.focus()
            }}
            className={cn(
              "-mb-px min-h-11 shrink-0 border-b-2 px-3 py-2 text-[0.9375rem] font-medium transition-colors",
              tab === key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t(`tab.${key}`)}
          </button>
        ))}
      </div>
      <div id="papers-panel" role="tabpanel" aria-labelledby={`papers-tab-${tab}`}>
        {tab === "calendar" ? (
          <CalendarTab />
        ) : (
          <DocumentsTab key={tab} archived={tab === "archives"} area={area} onArea={setArea} />
        )}
      </div>
    </>
  )
}

function AreaTiles({ selected, onSelect }: { selected: Area | null; onSelect: (area: Area | null) => void }) {
  const t = useT(messages)
  const areas = useQuery({ queryKey: ["areas"], queryFn: api.areas, refetchInterval: 30_000 })
  if (!areas.data)
    return (
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {AREAS.map((a) => (
          <Skeleton key={a} className="h-24 rounded-xl" />
        ))}
      </div>
    )
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {areas.data.map((a, i) => (
        <AreaTile key={a.area} index={i} summary={a} active={selected === a.area} onClick={() => onSelect(selected === a.area ? null : a.area)} />
      ))}
      {selected && (
        <button
          onClick={() => onSelect(null)}
          className="animate-rise flex min-h-24 items-center justify-center rounded-xl border border-dashed px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          {t("allAreas")}
        </button>
      )}
    </div>
  )
}

const TONE_TEXT: Record<string, string> = {
  urgent: "text-red-600 dark:text-red-400",
  soon: "text-amber-700 dark:text-amber-400",
  ok: "text-muted-foreground",
  empty: "text-muted-foreground",
}

function AreaTile({ summary, index, active, onClick }: { summary: AreaSummary; index: number; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{ "--i": index } as React.CSSProperties}
      className={cn(
        "animate-rise flex min-h-24 flex-col items-start gap-2 rounded-xl bg-card p-3.5 text-left ring-1 transition-[box-shadow,background-color] hover:bg-accent/40 hover:shadow-sm",
        active ? "ring-2 ring-primary" : "ring-foreground/10",
      )}
    >
      <span className="flex w-full items-center gap-2.5">
        <AreaIcon area={summary.area} size="sm" />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{summary.label}</span>
        {active && <CheckIcon className="animate-pop size-4 text-primary" weight="bold" />}
      </span>
      <span className={cn("line-clamp-2 text-xs leading-snug", TONE_TEXT[summary.tone] ?? TONE_TEXT.ok)}>
        {summary.state}
      </span>
    </button>
  )
}

function DocumentsTab({ archived, area, onArea }: { archived: boolean; area: Area | null; onArea: (a: Area | null) => void }) {
  const t = useT(messages)
  const agent = useAgent()
  const [text, setText] = useState("")
  const [person, setPerson] = useState<string | null>(null)
  const q = useDeferredValue(text.trim())
  const docs = useQuery({
    queryKey: ["documents", { q, archived, limit: 500 }],
    queryFn: () => api.documents({ q: q || undefined, archived: archived || undefined, limit: 500 }),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => (query.state.data?.some((d) => d.status === "processing") ? 1500 : false),
  })
  const all = docs.data ?? []
  const inArea = area ? all.filter((d) => d.area === area) : all
  const people = useMemo(() => [...new Set(inArea.map((d) => d.person).filter((p): p is string => !!p))].sort(), [inArea])
  const shown = person ? inArea.filter((d) => d.person === person) : inArea

  return (
    <>
      {!archived && <AreaTiles selected={area} onSelect={onArea} />}
      {!archived && <EssentialsLink />}
      <div className="relative mb-3">
        <MagnifyingGlassIcon className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={archived ? t("searchArchives") : t("search")}
          aria-label={archived ? t("searchArchives") : t("search")}
          className="h-11 pl-10"
        />
      </div>
      {archived && <p className="mb-3 text-sm text-muted-foreground">{t("archivesHint")}</p>}
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {people.length > 1 &&
          [null, ...people].map((p) => (
            <button
              key={p ?? "everyone"}
              onClick={() => setPerson(p)}
              aria-pressed={person === p}
              className={cn(
                "min-h-9 rounded-full border px-3 py-1 text-sm font-medium transition-colors",
                person === p ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
            >
              {p ?? t("everyone")}
            </button>
          ))}
        {docs.data && (
          <span role="status" className="ml-auto text-xs text-muted-foreground">
            {t("count", { count: shown.length })}
          </span>
        )}
      </div>
      <Card className="gap-0 p-0">
        {!docs.data ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-5 py-10 text-center">
            <p className="text-sm font-medium">{q || area || person ? t("noMatch") : archived ? t("archivesEmpty") : t("empty")}</p>
            {!q && !area && !person && (
              <p className="text-sm text-muted-foreground">{archived ? t("archivesEmptyHint") : t("emptyHint")}</p>
            )}
          </div>
        ) : (
          <DocumentsByYear docs={shown} />
        )}
      </Card>
      {/* A search is often a question in disguise: the agent can answer it. */}
      {q && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => agent.open(q)}>
            <RobotIcon /> {t("askInstead", { query: q })}
          </Button>
        </div>
      )}
    </>
  )
}

const BACK = 14
const AHEAD = 120

/** The deadlines on a timeline, then the administrative year: what comes back every year. */
function CalendarTab() {
  const t = useT(messages)
  const [day] = useState(() => new Date())
  const horizon = useMemo(
    () => ({
      start: toIso(new Date(day.getTime() - BACK * 86_400_000)),
      end: toIso(new Date(day.getTime() + AHEAD * 86_400_000)),
      include_done: true,
    }),
    [day],
  )
  const deadlines = useDeadlines(horizon)
  const year = useQuery({ queryKey: ["calendar"], queryFn: api.calendar, staleTime: 300_000 })
  const now = day.getMonth() + 1
  // From this month on, then the months of next year.
  const months = [...Array(12).keys()].map((i) => ((now - 1 + i) % 12) + 1)
  const upcoming = (deadlines.data ?? []).filter((d) => !d.done && d.days_left >= 0)
  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-1 font-semibold">{t("calendar.deadlines")}</h2>
        <p className="mb-3 text-sm text-muted-foreground">{t("calendar.deadlinesHint")}</p>
        <Timeline deadlines={deadlines.data ?? []} back={BACK} ahead={AHEAD} loading={deadlines.isPending} />
        {deadlines.data && (
          <Card className="mt-3 gap-0 p-0">
            {upcoming.length === 0 ? (
              <p className="px-5 py-6 text-center text-sm text-muted-foreground">{t("calendar.none")}</p>
            ) : (
              <ul className="divide-y">
                {upcoming.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                    <span className="w-28 shrink-0 text-muted-foreground tabular-nums">{formatDate(d.due_date)}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">{d.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </section>
      {year.data && year.data.length > 0 && (
        <section>
          <h2 className="mb-1 font-semibold">{t("calendar.year")}</h2>
          <p className="mb-3 text-sm text-muted-foreground">{t("calendar.yearHint")}</p>
          <Card className="gap-0 p-0">
            <ul className="divide-y">
              {months.flatMap((m) =>
                year.data
                  .filter((e) => e.month === m)
                  .map((e) => (
                    <li
                      key={e.key}
                      aria-current={m === now ? "date" : undefined}
                      className={cn("flex gap-4 px-5 py-3 text-sm", m === now && "bg-accent/50")}
                    >
                      <span className="w-24 shrink-0 font-medium capitalize">
                        {monthName(m)}
                        {m === now && <span className="block text-xs font-normal text-muted-foreground">{t("calendar.thisMonth")}</span>}
                      </span>
                      <span className="min-w-0 flex-1">
                        {e.text}
                        {e.concerns_you && <span className="ml-2 text-xs font-medium text-primary">{t("calendar.concernsYou")}</span>}
                      </span>
                    </li>
                  )),
              )}
            </ul>
          </Card>
        </section>
      )}
    </div>
  )
}

function monthName(month: number) {
  return new Date(2000, month - 1, 1).toLocaleDateString(currentLocale(), { month: "long" })
}
