import { Link } from "react-router-dom"
import { VaultIcon, RobotIcon, FlaskIcon, TrayArrowDownIcon, EnvelopeIcon, UserIcon } from "@phosphor-icons/react"
import { Skeleton } from "@/components/ui/skeleton"
import { useT } from "@/i18n"
import type { Translate } from "@/i18n/core"
import { activity } from "@/i18n/messages/activity"
import type { Activity, Actor } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { cn } from "@/lib/utils"

const ACTORS: Record<Actor, { icon: typeof UserIcon; tone: string }> = {
  user: { icon: UserIcon, tone: "bg-slate-100 text-slate-600 dark:bg-slate-500/20 dark:text-slate-300" },
  binder: { icon: VaultIcon, tone: "bg-primary/10 text-primary" },
  agent: { icon: RobotIcon, tone: "bg-primary/10 text-primary" },
  watcher: { icon: TrayArrowDownIcon, tone: "bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300" },
  mail: { icon: EnvelopeIcon, tone: "bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300" },
  demo: { icon: FlaskIcon, tone: "bg-slate-100 text-slate-500 dark:bg-slate-500/20 dark:text-slate-300" },
}

function dayLabel(iso: string, t: Translate<(typeof activity)["en"]>): string {
  const date = new Date(iso)
  const today = new Date()
  const yesterday = new Date(today.getTime() - 86_400_000)
  if (date.toDateString() === today.toDateString()) return t("today")
  if (date.toDateString() === yesterday.toDateString()) return t("yesterday")
  const label = formatDateTime(iso, { weekday: "long", day: "numeric", month: "long", year: "numeric" })
  return label[0].toUpperCase() + label.slice(1)
}

/** Activity log grouped by day. `linkDocuments` links each entry to its document. */
export function ActivityList({
  entries,
  loading,
  linkDocuments = true,
  empty,
}: {
  entries?: Activity[]
  loading?: boolean
  linkDocuments?: boolean
  empty?: string
}) {
  const t = useT(activity)
  if (loading)
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    )
  if (!entries?.length) return <p className="px-5 py-8 text-center text-sm text-muted-foreground">{empty ?? t("empty")}</p>

  const groups: { day: string; items: Activity[] }[] = []
  for (const entry of entries) {
    const day = dayLabel(entry.created_at, t)
    const last = groups.at(-1)
    if (last?.day === day) last.items.push(entry)
    else groups.push({ day, items: [entry] })
  }

  return (
    <div>
      {groups.map((g) => (
        <section key={g.day}>
          <h3 className="border-b bg-muted/40 px-5 py-1.5 text-xs font-medium text-muted-foreground">{g.day}</h3>
          <ul className="divide-y">
            {g.items.map((a) => {
              const actorKey: Actor = a.actor in ACTORS ? a.actor : "binder"
              const actor = ACTORS[actorKey]
              const actorLabel = t(`actor.${actorKey}`)
              const Icon = actor.icon
              const body = (
                <>
                  <span
                    className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", actor.tone)}
                    title={actorLabel}
                  >
                    <Icon className="size-3.5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm">{a.summary}</span>
                    <span className="block text-xs text-muted-foreground">{actorLabel}</span>
                  </span>
                  <time className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {formatDateTime(a.created_at, { hour: "2-digit", minute: "2-digit" })}
                  </time>
                </>
              )
              const linkable = linkDocuments && a.document_id !== null && !["purge"].includes(a.action)
              return (
                <li key={a.id}>
                  {linkable ? (
                    <Link to={`/documents/${a.document_id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-muted/40">
                      {body}
                    </Link>
                  ) : (
                    <div className="flex items-center gap-3 px-5 py-2.5">{body}</div>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
