import { useState } from "react"
import { Link } from "react-router-dom"
import { useQueries } from "@tanstack/react-query"
import { WarningIcon, ClockCountdownIcon, QuestionIcon, FileMagnifyingGlassIcon, FileTextIcon, HourglassIcon, TrayIcon, LightbulbIcon, ListChecksIcon, EnvelopeIcon, NewspaperIcon, UsersIcon, CircleNotchIcon, EyeIcon, ArrowSquareOutIcon, HandCoinsIcon, type Icon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { DocumentPage } from "@/components/DocumentPage"
import { usePanels } from "@/components/panels/context"
import { queries } from "@/hooks/queries"
import { useRunAction } from "@/hooks/useRunAction"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { viewer } from "@/i18n/messages/viewer"
import type { FeedAction, FeedItem } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { formatAmount, formatDate } from "@/lib/format"
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
  questions: QuestionIcon,
  right: HandCoinsIcon,
}

const TONE_STYLE: Record<FeedItem["tone"], { dot: string; label: string }> = {
  urgent: { dot: "bg-red-500 ring-red-500/15", label: "text-red-600 dark:text-red-400" },
  soon: { dot: "bg-amber-500 ring-amber-500/15", label: "text-amber-700 dark:text-amber-400" },
  info: { dot: "bg-primary/60 ring-primary/10", label: "text-muted-foreground" },
}

// Answers that close a card without doing anything: quiet, at the end of the row.
const QUIET = ["dismiss", "mark_seen"]

const actionRank = (action: FeedAction) => (action.primary ? 0 : QUIET.includes(action.type) ? 2 : 1)

export function FeedCard({ item }: { item: FeedItem }) {
  const t = useT(feed)
  const { run, pending, isRunning } = useRunAction()
  const panels = usePanels()
  const [preview, setPreview] = useState(false)
  const Icon = KIND_ICON[item.kind]
  const tone = TONE_STYLE[item.tone]
  // A question opens its own panel next to the document: no separate preview then.
  const asks = item.actions.some((a) => a.type === "ask")
  // Any other card tied to a document can be read on the spot, without leaving To do.
  const previewable = item.document_ids.length > 0 && !asks
  const actions = item.actions
    // The preview already leads to the document page: a secondary "Open" would say it twice.
    .filter((a) => !(previewable && a.type === "open" && !a.primary && String(a.params.url).startsWith("/documents/")))
    // What to do first, then the other ways, then "not needed" set apart at the end.
    .map((action, index) => ({ action, index }))
    .sort((a, b) => actionRank(a.action) - actionRank(b.action) || a.index - b.index)
    .map(({ action }) => action)

  const button = (action: FeedAction, i: number) => {
    const running = isRunning(action)
    const quiet = QUIET.includes(action.type)
    return (
      <Button
        key={i}
        size="sm"
        variant={action.primary ? "default" : quiet ? "ghost" : "outline"}
        // Set apart at the end of the row, its text lined up with the card's edge.
        className={cn(quiet && "-mr-3 ml-auto text-muted-foreground")}
        disabled={pending}
        onClick={() => run(action)}
      >
        {running ? (
          <CircleNotchIcon className="animate-spin" />
        ) : action.type === "open" ? (
          <FileTextIcon />
        ) : (
          action.type === "link" && <ArrowSquareOutIcon />
        )}
        {running ? t("working") : action.label}
      </Button>
    )
  }
  const lead = actions.filter((a) => a.primary)

  return (
    <li className="px-4 py-4 sm:px-5">
      <div className="flex gap-3 sm:gap-4">
        <div className="relative shrink-0">
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
            <p className="text-sm font-medium text-pretty">{item.title}</p>
            {item.amount !== null && item.kind !== "briefing" && (
              <span className="shrink-0 text-sm font-medium tabular-nums">{formatAmount(item.amount)}</span>
            )}
          </div>
          {item.detail && (
            <p className={cn("mt-0.5 max-w-[70ch] text-sm text-pretty", item.kind === "deadline" ? tone.label : "text-muted-foreground")}>
              {item.tone === "urgent" && item.kind !== "deadline" && (
                <span className={cn("font-medium", tone.label)}>{t("tone.urgent")} · </span>
              )}
              {/* The amber dot, in words for screen readers. */}
              {item.tone === "soon" && item.kind !== "deadline" && <span className="sr-only">{t("tone.soon")} · </span>}
              {item.detail}
            </p>
          )}
        </div>
      </div>
      {/* Under the text from sm; full width on a phone, where the icon column would cramp it. */}
      {(previewable || actions.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2 sm:pl-13">
          {lead.map(button)}
          {previewable && (
            <Button
              size="sm"
              variant="outline"
              // A question is answered looking at the document: the question panel.
              onClick={() => (item.kind === "question" ? panels.showQuestions(item.document_ids) : setPreview(true))}
            >
              <EyeIcon /> {t("seeDocuments", { count: item.document_ids.length })}
            </Button>
          )}
          {actions.filter((a) => !a.primary).map((a, i) => button(a, lead.length + i))}
        </div>
      )}
      {previewable && (
        <Dialog open={preview} onOpenChange={setPreview}>
          <DialogContent className="flex h-[92vh] max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
            {preview && <DocumentsPreview title={item.title} ids={item.document_ids} onNavigate={() => setPreview(false)} />}
          </DialogContent>
        </Dialog>
      )}
    </li>
  )
}

/** The documents of a card, one at a time, large, with zoom; a chip per document when several. */
function DocumentsPreview({ title, ids, onNavigate }: { title: string; ids: number[]; onNavigate: () => void }) {
  const tv = useT(viewer)
  const [shown, setShown] = useState(0)
  const docs = useQueries({ queries: ids.map((id) => queries.document(id)) })
  const doc = docs[shown]?.data
  return (
    <>
      <DialogHeader className="border-b px-5 py-3.5 pr-12">
        <DialogTitle className="truncate text-base">{title}</DialogTitle>
        <DialogDescription className="sr-only">{title}</DialogDescription>
      </DialogHeader>
      {ids.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto border-b px-3 py-2">
          {ids.map((id, i) => (
            <Button
              key={id}
              size="xs"
              variant={i === shown ? "secondary" : "ghost"}
              aria-pressed={i === shown}
              onClick={() => setShown(i)}
              className="max-w-72"
            >
              <span className="truncate">{docs[i]?.data?.title ?? "…"}</span>
              {/* Two bills of the same sender share a title: the date tells them apart. */}
              {docs[i]?.data?.issue_date && (
                <span className="shrink-0 text-muted-foreground">{formatDate(docs[i].data.issue_date)}</span>
              )}
            </Button>
          ))}
        </div>
      )}
      {doc ? <DocumentPage key={doc.id} doc={doc} active={null} className="min-h-0 flex-1" /> : <Skeleton className="m-4 flex-1" />}
      {doc && (
        <div className="flex justify-end border-t px-3 py-2">
          <Button size="sm" variant="outline" render={<Link to={`/documents/${doc.id}`} onClick={onNavigate} />} nativeButton={false}>
            <ArrowSquareOutIcon /> {tv("open")}
          </Button>
        </div>
      )}
    </>
  )
}
