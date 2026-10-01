import { useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  AlertTriangle, CalendarClock, CircleHelp, Copy, FileSearch, FileText, Inbox, KeyRound, Lightbulb, Mail, Newspaper,
  Users, type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { CategoryIcon } from "@/components/CategoryIcon"
import { useAgent } from "@/components/agent"
import { usePanels } from "@/components/panels"
import { useUpload } from "@/components/upload"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { api, type FeedAction, type FeedItem } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { formatAmount } from "@/lib/format"
import { cn } from "@/lib/utils"

// Icon of a card without area or category.
const KIND_ICON: Record<FeedItem["kind"], LucideIcon> = {
  recovery: KeyRound,
  report: Inbox,
  briefing: Newspaper,
  question: CircleHelp,
  deadline: CalendarClock,
  expiry: CalendarClock,
  anomaly: AlertTriangle,
  missing: FileSearch,
  letter: Mail,
  suggestion: Lightbulb,
  household: Users,
}

const TONE_STYLE: Record<FeedItem["tone"], { dot: string; label: string }> = {
  urgent: { dot: "bg-red-500 ring-red-500/15", label: "text-red-600 dark:text-red-400" },
  soon: { dot: "bg-amber-500 ring-amber-500/15", label: "text-amber-700 dark:text-amber-400" },
  info: { dot: "bg-primary/60 ring-primary/10", label: "text-muted-foreground" },
}

/** Runs a card's action: on the server (with undo), or in the interface (open, ask, add…). */
export function useRunAction() {
  const navigate = useNavigate()
  const agent = useAgent()
  const upload = useUpload()
  const panels = usePanels()
  const invalidate = useInvalidateAll()
  const server = useMutation({
    mutationFn: api.act,
    onSuccess: (result) => {
      invalidate()
      if (result.letter) panels.showLetter(result.letter)
    },
    onError: (e) => toast.error(e.message),
  })
  const run = (action: FeedAction) => {
    const p = action.params
    switch (action.type) {
      case "open":
        navigate(String(p.url))
        return
      case "agent":
        agent.open(String(p.prompt))
        return
      case "upload":
        upload.open()
        return
      case "report":
        panels.showReport(String(p.batch))
        return
      case "pdf":
        window.location.assign(String(p.url))
        return
      default:
        server.mutate({ type: action.type, params: p })
    }
  }
  return { run, pending: server.isPending }
}

export function FeedCard({ item }: { item: FeedItem }) {
  const t = useT(feed)
  const { run, pending } = useRunAction()
  const Icon = KIND_ICON[item.kind]
  const tone = TONE_STYLE[item.tone]
  const code = typeof item.extra.code === "string" ? item.extra.code : null

  return (
    <li className="flex gap-4 px-5 py-4">
      <div className="relative">
        {item.area ? (
          <AreaIcon area={item.area} />
        ) : item.category && item.category !== "other" ? (
          <CategoryIcon category={item.category} />
        ) : (
          <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
            <Icon className="size-4" />
          </span>
        )}
        {item.tone !== "info" && (
          <span className={cn("absolute -top-0.5 -right-0.5 size-2.5 rounded-full ring-4", tone.dot)} aria-hidden />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium">{item.title}</p>
          {item.amount !== null && item.kind !== "briefing" && (
            <span className="shrink-0 text-sm font-medium tabular-nums">{formatAmount(item.amount)}</span>
          )}
        </div>
        {item.detail && (
          <p className={cn("mt-0.5 text-sm", item.kind === "deadline" ? tone.label : "text-muted-foreground")}>
            {item.tone === "urgent" && item.kind !== "deadline" && (
              <span className={cn("font-medium", tone.label)}>{t("tone.urgent")} · </span>
            )}
            {item.detail}
          </p>
        )}
        {code && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded-lg border bg-muted/50 px-3 py-1.5 font-sans text-base font-semibold tracking-wider select-all">
              {code}
            </code>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigator.clipboard.writeText(code).then(() => toast.success(t("codeCopied")))}
            >
              <Copy /> {t("copyCode")}
            </Button>
          </div>
        )}
        {item.actions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {item.actions.map((action, i) => (
              <Button
                key={i}
                size="sm"
                variant={action.primary ? "default" : action.type === "dismiss" ? "ghost" : "outline"}
                disabled={pending}
                onClick={() => run(action)}
              >
                {action.type === "open" && <FileText />}
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    </li>
  )
}
