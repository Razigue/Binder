import { useDeferredValue, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { RobotIcon, MagnifyingGlassIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useAgent } from "@/components/agent"
import { DocumentsByYear } from "@/components/documents"
import { PageHeader } from "@/components/layout/AppLayout"
import { ImportButton } from "@/components/upload"
import { useT } from "@/i18n"
import { area as areaMessages } from "@/i18n/messages/area"
import { documents as messages } from "@/i18n/messages/documents"
import { AREAS, api, type Area } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Every document in one place: the search reads their content, not just their titles. */
export function DocumentsPage() {
  const t = useT(messages)
  const ta = useT(areaMessages)
  const agent = useAgent()
  const [text, setText] = useState("")
  const [area, setArea] = useState<Area | null>(null)
  const q = useDeferredValue(text.trim())
  const docs = useQuery({
    queryKey: ["documents", { q, limit: 500 }],
    queryFn: () => api.documents({ q: q || undefined, limit: 500 }),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => (query.state.data?.some((d) => d.status === "processing") ? 1500 : false),
  })
  const all = docs.data ?? []
  const shown = area ? all.filter((d) => d.area === area) : all
  const present = new Set(all.map((d) => d.area))

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} actions={<ImportButton />} />
      <div className="relative mb-3">
        <MagnifyingGlassIcon className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("search")}
          aria-label={t("search")}
          className="h-11 pl-10"
          autoFocus
        />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {[null, ...AREAS.filter((a) => present.has(a) || a === area)].map((a) => (
          <button
            key={a ?? "all"}
            onClick={() => setArea(a)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              area === a ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
          >
            {a ? ta(`area.${a}`) : t("all")}
          </button>
        ))}
        {docs.data && <span className="ml-auto text-xs text-muted-foreground">{t("count", { count: shown.length })}</span>}
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
            <p className="text-sm font-medium">{q || area ? t("noMatch") : t("empty")}</p>
            {!q && !area && <p className="text-sm text-muted-foreground">{t("emptyHint")}</p>}
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
