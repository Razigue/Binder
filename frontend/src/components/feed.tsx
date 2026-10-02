import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { WarningIcon, ClockCountdownIcon, QuestionIcon, FileMagnifyingGlassIcon, FileTextIcon, HourglassIcon, TrayIcon, LightbulbIcon, ListChecksIcon, EnvelopeIcon, NewspaperIcon, UsersIcon, CircleNotchIcon, EyeIcon, type Icon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { CategoryIcon } from "@/components/CategoryIcon"
import { useAgent } from "@/components/agent"
import { usePanels } from "@/components/panels"
import { useUpload } from "@/components/upload"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { api, previewUrl, type FeedAction, type FeedItem } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { formatAmount } from "@/lib/format"
import { cn } from "@/lib/utils"

// Icon of a card without area or category.
const KIND_ICON: Record<FeedItem["kind"], Icon> = {
  report: TrayIcon,
  briefing: NewspaperIcon,
  question: QuestionIcon,
  deadline: ClockCountdownIcon,
  expiry: ClockCountdownIcon,
  anomaly: WarningIcon,
  missing: FileMagnifyingGlassIcon,
  letter: EnvelopeIcon,
  suggestion: LightbulbIcon,
  household: UsersIcon,
  journey: ListChecksIcon,
  waiting: HourglassIcon,
}

const TONE_STYLE: Record<FeedItem["tone"], { dot: string; label: string }> = {
  urgent: { dot: "bg-red-500 ring-red-500/15", label: "text-red-600 dark:text-red-400" },
  soon: { dot: "bg-amber-500 ring-amber-500/15", label: "text-amber-700 dark:text-amber-400" },
  info: { dot: "bg-primary/60 ring-primary/10", label: "text-muted-foreground" },
}

// Identifies one action among a card's actions, to spot which button is running.
const actionKey = (action: FeedAction) => `${action.type}:${JSON.stringify(action.params)}`

/** Runs a card's action: on the server (with undo), or in the interface (open, ask, add…). */
export function useRunAction() {
  const navigate = useNavigate()
  const agent = useAgent()
  const upload = useUpload()
  const panels = usePanels()
  const invalidate = useInvalidateAll()
  const [runningKey, setRunningKey] = useState<string | null>(null)
  const server = useMutation({
    mutationFn: api.act,
    onSuccess: (result) => {
      invalidate()
      if (result.letter) panels.showLetter(result.letter)
    },
    onError: (e) => toast.error(e.message),
    onSettled: () => setRunningKey(null),
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
      case "journey":
        panels.showJourney(Number(p.journey_id))
        return
      case "pdf":
        window.location.assign(String(p.url))
        return
      default:
        setRunningKey(actionKey(action))
        server.mutate({ type: action.type, params: p })
    }
  }
  const isRunning = (action: FeedAction) => server.isPending && runningKey === actionKey(action)
  return { run, pending: server.isPending, isRunning }
}

export function FeedCard({ item }: { item: FeedItem }) {
  const t = useT(feed)
  const { run, pending, isRunning } = useRunAction()
  const [preview, setPreview] = useState(false)
  const Icon = KIND_ICON[item.kind]
  const tone = TONE_STYLE[item.tone]
  // A question is a judgment call about a document: let the user read it before answering.
  const previewable = item.kind === "question" && item.document_ids.length === 1

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
        {(previewable || item.actions.length > 0) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {previewable && (
              <Button size="sm" variant="outline" onClick={() => setPreview(true)}>
                <EyeIcon /> {t("seeDocument")}
              </Button>
            )}
            {item.actions.map((action, i) => {
              const running = isRunning(action)
              return (
                <Button
                  key={i}
                  size="sm"
                  variant={action.primary ? "default" : action.type === "dismiss" ? "ghost" : "outline"}
                  disabled={pending}
                  onClick={() => run(action)}
                >
                  {running ? <CircleNotchIcon className="animate-spin" /> : action.type === "open" && <FileTextIcon />}
                  {running ? t("working") : action.label}
                </Button>
              )
            })}
          </div>
        )}
      </div>
      {previewable && (
        <Dialog open={preview} onOpenChange={setPreview}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-base">{item.title}</DialogTitle>
              <DialogDescription className="sr-only">{item.title}</DialogDescription>
            </DialogHeader>
            {/* White backing on purpose: it is a picture of a paper page, in both themes. */}
            <img
              src={previewUrl(item.document_ids[0])}
              alt={item.title}
              className="w-full rounded bg-white shadow-sm dark:brightness-[0.88]"
            />
          </DialogContent>
        </Dialog>
      )}
    </li>
  )
}
