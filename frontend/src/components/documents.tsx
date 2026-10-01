import { useMemo } from "react"
import { Link } from "react-router-dom"
import { ChevronRight, Hourglass, Loader2 } from "lucide-react"
import { CategoryIcon } from "@/components/CategoryIcon"
import { useT } from "@/i18n"
import { area as messages } from "@/i18n/messages/area"
import type { Doc } from "@/lib/api"
import { docTypeLabel, formatAmount, formatDate } from "@/lib/format"

const fold = (text: string) => text.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "")

/** Whether a document matches every word typed, accents and case aside. */
export function matches(d: Doc, filter: string): boolean {
  const words = fold(filter).split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const hay = fold(`${d.title} ${d.issuer ?? ""} ${d.reference ?? ""} ${docTypeLabel(d.doc_type)} ${d.person ?? ""}`)
  return words.every((w) => hay.includes(w))
}

/** Documents by year, most recent first, as rows inside a card. */
export function DocumentsByYear({ docs }: { docs: Doc[] }) {
  const t = useT(messages)
  const years = useMemo(() => {
    const groups = new Map<string, Doc[]>()
    for (const d of docs) {
      const year = (d.issue_date ?? d.due_date ?? d.created_at).slice(0, 4)
      groups.set(year, [...(groups.get(year) ?? []), d])
    }
    return [...groups.entries()].sort((a, b) => b[0].localeCompare(a[0]))
  }, [docs])

  return years.map(([year, list]) => (
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
                  ) : d.status === "waiting" ? (
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <Hourglass className="size-3.5" /> {d.filename} · {t("waiting")}
                    </span>
                  ) : (
                    d.title
                  )}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {[
                    formatDate(d.issue_date ?? d.created_at),
                    d.issuer,
                    d.person,
                    d.superseded_by !== null ? t("oldVersion") : null,
                    d.status === "to_review" ? t("question") : null,
                  ]
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
}
