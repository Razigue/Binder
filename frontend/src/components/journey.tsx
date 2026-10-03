import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { CircleIcon, CheckCircleIcon, NotePencilIcon, FileTextIcon, FolderPlusIcon, ListChecksIcon, CircleNotchIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { usePanels } from "@/components/panels/context"
import { FolderView } from "@/components/panels/FolderView"
import { keys, useInvalidateAll, useJourney } from "@/hooks/queries"
import { useT } from "@/i18n"
import { journey as messages } from "@/i18n/messages/journey"
import { api, type Folder, type Journey, type JourneyKindInfo, type JourneyStep, type Letter, type StepAction } from "@/lib/api"
import { formatAmount, formatDate, parseDate, urgency, urgencyStyles } from "@/lib/format"
import { cn } from "@/lib/utils"

type JourneyField = "new_address" | "child" | "person"

function daysFromToday(iso: string): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((parseDate(iso).getTime() - today.getTime()) / 86_400_000)
}

/** The checklist of a journey in a dialog, opened from anywhere (feed, Prepare, agent). */
export function JourneyDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data } = useJourney(id)
  const t = useT(messages)
  return (
    <Dialog open={id !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] gap-4 overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-lg">{data?.title ?? t("group")}</DialogTitle>
          <DialogDescription>{data?.description ?? ""}</DialogDescription>
        </DialogHeader>
        {id !== null && <JourneyView id={id} onNavigate={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function JourneyView({ id, onNavigate }: { id: number; onNavigate: () => void }) {
  const t = useT(messages)
  const { data } = useJourney(id)
  const qc = useQueryClient()
  const invalidate = useInvalidateAll()
  const saved = (j: Journey) => {
    qc.setQueryData(keys.journey(id), j)
    invalidate()
  }
  const toggle = useMutation({
    mutationFn: (s: { key: string; done: boolean }) => api.journeyStep(id, s.key, s.done),
    onSuccess: saved,
    onError: (e) => toast.error(e.message),
  })
  const edit = useMutation({
    mutationFn: (body: { event_date?: string; closed?: boolean }) => api.updateJourney(id, body),
    onSuccess: saved,
    onError: (e) => toast.error(e.message),
  })

  if (!data)
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  return (
    <div className="space-y-4">
      <EventDate journey={data} pending={edit.isPending} onSave={(event_date) => edit.mutate({ event_date })} />
      <div className="space-y-1.5">
        <Progress
          value={data.total ? (data.done / data.total) * 100 : 0}
          aria-label={t("progress", { done: data.done, total: data.total })}
        />
        <p className="text-xs text-muted-foreground">
          {data.done === data.total ? t("allDone") : t("progress", { done: data.done, total: data.total })}
        </p>
      </div>
      <ul className="divide-y rounded-lg border">
        {data.steps.map((step) => (
          <StepRow
            key={step.key}
            step={step}
            pending={toggle.isPending}
            onToggle={() => toggle.mutate({ key: step.key, done: !step.done })}
            onNavigate={onNavigate}
          />
        ))}
      </ul>
      <Button variant="ghost" size="sm" disabled={edit.isPending} onClick={() => edit.mutate({ closed: !data.closed })}>
        {data.closed ? t("reopen") : t("close")}
      </Button>
    </div>
  )
}

function EventDate({ journey, pending, onSave }: { journey: Journey; pending: boolean; onSave: (date: string) => void }) {
  const t = useT(messages)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(journey.event_date)
  if (editing)
    return (
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!value) return
          onSave(value)
          setEditing(false)
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="journey-date">{journey.event_label}</Label>
          <Input id="journey-date" type="date" value={value} onChange={(e) => setValue(e.target.value)} className="w-44" />
        </div>
        <Button type="submit" size="sm" disabled={pending || !value}>
          {t("saveDate")}
        </Button>
      </form>
    )
  return (
    <p className="text-sm">
      <span className="text-muted-foreground">{t("eventLabel", { label: journey.event_label })} </span>
      <span className="font-medium">{formatDate(journey.event_date, "long")}</span>{" "}
      <Button variant="link" size="sm" className="h-auto px-1" onClick={() => setEditing(true)}>
        {t("changeDate")}
      </Button>
    </p>
  )
}

function StepRow({
  step,
  pending,
  onToggle,
  onNavigate,
}: {
  step: JourneyStep
  pending: boolean
  onToggle: () => void
  onNavigate: () => void
}) {
  const t = useT(messages)
  const panels = usePanels()
  const navigate = useNavigate()
  const invalidate = useInvalidateAll()
  const [folder, setFolder] = useState<Folder | null>(null)
  const act = useMutation({
    mutationFn: async (action: StepAction): Promise<{ letter?: Letter; folder?: Folder }> => {
      if (action.type === "letter") return { letter: await api.writeLetter(action.params) }
      if (action.type === "folder") return { folder: await api.prepareFolder(action.params.kind) }
      return {}
    },
    onSuccess: (result) => {
      invalidate()
      if (result.letter) panels.showLetter(result.letter)
      if (result.folder) setFolder(result.folder)
    },
    onError: (e) => toast.error(e.message),
  })
  const run = (action: StepAction) => {
    if (action.type === "open") {
      onNavigate()
      navigate(action.params.url)
    } else act.mutate(action)
  }
  const open = (docId: number) => {
    onNavigate()
    navigate(`/documents/${docId}`)
  }
  const days = step.due ? daysFromToday(step.due) : null
  const tone = days !== null && !step.done ? urgency(days) : null
  const when = step.done
    ? step.auto
      ? t("autoDone")
      : t("done")
    : days === null
      ? ""
      : days < 0
        ? t("late", { count: -days })
        : days === 0
          ? t("today")
          : t("by", { date: formatDate(step.due) })

  return (
    <li className="flex gap-3 px-4 py-3">
      <button
        type="button"
        onClick={onToggle}
        disabled={pending || step.auto}
        role="checkbox"
        aria-checked={step.done}
        aria-label={step.title}
        title={step.done ? t("markUndone") : t("markDone")}
        className="-mx-0.5 -mb-0.5 h-fit shrink-0 rounded-full p-0.5 text-muted-foreground transition-colors hover:text-primary disabled:cursor-default"
      >
        {step.done ? <CheckCircleIcon className="size-5 text-primary" /> : <CircleIcon className="size-5" />}
      </button>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-start justify-between gap-3">
          <p className={cn("text-sm font-medium", step.done && "text-muted-foreground line-through")}>{step.title}</p>
          {step.amount !== null && <span className="shrink-0 text-sm font-medium tabular-nums">{formatAmount(step.amount)}</span>}
        </div>
        {when && (
          <p
            className={cn(
              "text-xs font-medium",
              tone && tone !== "later" ? urgencyStyles[tone].text : "text-muted-foreground",
            )}
          >
            {when}
          </p>
        )}
        {!step.done && <p className="text-xs text-muted-foreground">{step.detail}</p>}
        {(step.document_ids.length > 0 || (step.action && !step.done)) && (
          <div className="flex flex-wrap gap-2 pt-1">
            {step.action && !step.done && (
              <Button size="xs" variant="outline" disabled={act.isPending} onClick={() => step.action && run(step.action)}>
                {act.isPending ? (
                  <CircleNotchIcon className="animate-spin" />
                ) : step.action.type === "folder" ? (
                  <FolderPlusIcon />
                ) : (
                  <NotePencilIcon />
                )}
                {step.action.label}
              </Button>
            )}
            {step.document_ids.slice(0, 2).map((docId) => (
              <Button key={docId} size="xs" variant="ghost" onClick={() => open(docId)}>
                <FileTextIcon /> {t("seeDocument")}
              </Button>
            ))}
          </div>
        )}
        {folder && (
          <div className="pt-2">
            <FolderView folder={folder} />
          </div>
        )}
      </div>
    </li>
  )
}

/** Starting a journey: its date and what Binder should know (new address, relative…). */
export function JourneyStart({ info, onStarted }: { info: JourneyKindInfo; onStarted: (j: Journey) => void }) {
  const t = useT(messages)
  const [date, setDate] = useState(info.default_date ?? "")
  const [details, setDetails] = useState<Record<string, string>>({})
  const invalidate = useInvalidateAll()
  const start = useMutation({
    mutationFn: () => api.startJourney({ kind: info.kind, event_date: date, details }),
    onSuccess: (j) => {
      invalidate()
      onStarted(j)
    },
    onError: (e) => toast.error(e.message),
  })
  if (start.isPending)
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <CircleNotchIcon className="size-4 animate-spin" /> {t("working")}
      </p>
    )
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (date) start.mutate()
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="journey-start-date">{info.event_label}</Label>
        <Input id="journey-start-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-44" autoFocus />
      </div>
      {Object.entries(info.fields).map(([key, label]) => (
        <div key={key} className="space-y-2">
          <Label htmlFor={`journey-${key}`}>
            {label} <span className="font-normal text-muted-foreground">({t("optional")})</span>
          </Label>
          {key === "new_address" ? (
            <Textarea
              id={`journey-${key}`}
              rows={2}
              value={details[key] ?? ""}
              placeholder={t(`field.${key as JourneyField}`)}
              onChange={(e) => setDetails({ ...details, [key]: e.target.value })}
            />
          ) : (
            <Input
              id={`journey-${key}`}
              value={details[key] ?? ""}
              placeholder={t(`field.${key as JourneyField}`)}
              onChange={(e) => setDetails({ ...details, [key]: e.target.value })}
            />
          )}
        </div>
      ))}
      <p className="text-xs text-muted-foreground">{t("startHint")}</p>
      <Button type="submit" disabled={!date}>
        {t("start")}
      </Button>
    </form>
  )
}

/** A journey in a few words, with the way to its steps (agent answers, Prepare). */
export function JourneyCard({ journey }: { journey: Journey }) {
  const t = useT(messages)
  const panels = usePanels()
  const next = journey.steps.find((s) => !s.done)
  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <ListChecksIcon className="size-4 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{journey.title}</span>
        <span className="text-xs text-muted-foreground">{t("progress", { done: journey.done, total: journey.total })}</span>
      </div>
      <div className="space-y-2 px-3 py-2.5">
        <p className="text-sm text-muted-foreground">{next ? t("nextStep", { step: next.title }) : t("allDone")}</p>
        <Button size="sm" variant="outline" onClick={() => panels.showJourney(journey.id)}>
          <ListChecksIcon /> {t("seeSteps")}
        </Button>
      </div>
    </div>
  )
}
