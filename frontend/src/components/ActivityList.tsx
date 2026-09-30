import { Link } from "react-router-dom"
import { Bot, FolderInput, Sparkles, User } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import type { Activity, Actor } from "@/lib/api"
import { cn } from "@/lib/utils"

const ACTORS: Record<Actor, { label: string; icon: typeof User; tone: string }> = {
  user: { label: "Vous", icon: User, tone: "bg-slate-100 text-slate-600" },
  binder: { label: "Binder", icon: Sparkles, tone: "bg-primary/10 text-primary" },
  agent: { label: "Agent", icon: Bot, tone: "bg-violet-50 text-violet-600" },
  watcher: { label: "Dossier surveillé", icon: FolderInput, tone: "bg-sky-50 text-sky-600" },
  demo: { label: "Démonstration", icon: Sparkles, tone: "bg-slate-100 text-slate-500" },
}

const DAY = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
const TIME = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" })

function dayLabel(date: Date): string {
  const today = new Date()
  const yesterday = new Date(today.getTime() - 86_400_000)
  if (date.toDateString() === today.toDateString()) return "Aujourd'hui"
  if (date.toDateString() === yesterday.toDateString()) return "Hier"
  const label = DAY.format(date)
  return label[0].toUpperCase() + label.slice(1)
}

/** Historique groupé par jour. `linkDocuments` ajoute un lien vers le document concerné. */
export function ActivityList({
  entries,
  loading,
  linkDocuments = true,
  empty = "Aucune activité pour l'instant.",
}: {
  entries?: Activity[]
  loading?: boolean
  linkDocuments?: boolean
  empty?: string
}) {
  if (loading)
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    )
  if (!entries?.length) return <p className="px-5 py-8 text-center text-sm text-muted-foreground">{empty}</p>

  const groups: { day: string; items: Activity[] }[] = []
  for (const entry of entries) {
    const day = dayLabel(new Date(entry.created_at))
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
              const actor = ACTORS[a.actor] ?? ACTORS.binder
              const Icon = actor.icon
              const body = (
                <>
                  <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", actor.tone)} title={actor.label}>
                    <Icon className="size-3.5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm">{a.summary}</span>
                    <span className="block text-xs text-muted-foreground">{actor.label}</span>
                  </span>
                  <time className="shrink-0 text-xs text-muted-foreground tabular-nums">{TIME.format(new Date(a.created_at))}</time>
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
