import { useState } from "react"
import {
  TruckIcon, BriefcaseIcon, BabyIcon, ArmchairIcon, FlowerLotusIcon, EnvelopeOpenIcon, ProhibitIcon, ScalesIcon,
  ListChecksIcon, NotePencilIcon, FolderPlusIcon, RobotIcon, DeviceMobileIcon, UploadSimpleIcon, CaretRightIcon, type Icon,
} from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useAgent } from "@/components/agent"
import { PageHeader } from "@/components/layout/AppLayout"
import { FinishedLetters, Ongoing } from "@/components/ongoing"
import { PrepareDialog, type Task } from "@/components/prepare"
import { usePanels } from "@/components/panels"
import { useUpload } from "@/components/upload"
import { useJourneyKinds, useJourneys } from "@/hooks/queries"
import { useT } from "@/i18n"
import { prepare as prepareMessages } from "@/i18n/messages/prepare"
import { procedures as messages } from "@/i18n/messages/procedures"
import type { FolderKind, JourneyKind, LetterKind } from "@/lib/api"

type AskKey = "ask.job" | "ask.retirement" | "ask.death" | "ask.unclear" | "ask.subscriptions"

/** What one tap on a sub-action does. */
type Step =
  | { type: "journey"; journey: JourneyKind }
  | { type: "letter"; letter: LetterKind | null }
  | { type: "folder"; folder: FolderKind | null }
  | { type: "ask"; prompt: AskKey }
  | { type: "scan" }
  | { type: "file" }

const EVENTS = [
  "moving", "job", "child", "retirement", "death", "unclear_letter", "stop_subscription", "dispute",
] as const
type Event = (typeof EVENTS)[number]

const EVENT_ICON: Record<Event, Icon> = {
  moving: TruckIcon,
  job: BriefcaseIcon,
  child: BabyIcon,
  retirement: ArmchairIcon,
  death: FlowerLotusIcon,
  unclear_letter: EnvelopeOpenIcon,
  stop_subscription: ProhibitIcon,
  dispute: ScalesIcon,
}

// The existing letters, files and checklists, grouped by what the user is going through.
const EVENT_STEPS: Record<Event, Step[]> = {
  moving: [
    { type: "journey", journey: "moving" },
    { type: "letter", letter: "address_change" },
    { type: "letter", letter: "termination" },
    { type: "folder", folder: "rental" },
  ],
  job: [
    { type: "ask", prompt: "ask.job" },
    { type: "folder", folder: null },
    { type: "letter", letter: "address_change" },
  ],
  child: [
    { type: "journey", journey: "birth" },
    { type: "folder", folder: "caf" },
    { type: "folder", folder: "school" },
  ],
  retirement: [
    { type: "folder", folder: "retirement" },
    { type: "ask", prompt: "ask.retirement" },
  ],
  death: [
    { type: "journey", journey: "death" },
    { type: "letter", letter: "termination" },
    { type: "ask", prompt: "ask.death" },
  ],
  unclear_letter: [{ type: "scan" }, { type: "file" }, { type: "ask", prompt: "ask.unclear" }],
  stop_subscription: [
    { type: "letter", letter: "termination" },
    { type: "ask", prompt: "ask.subscriptions" },
  ],
  dispute: [
    { type: "letter", letter: "complaint" },
    { type: "letter", letter: "appeal" },
    { type: "letter", letter: "payment_plan" },
    { type: "letter", letter: "formal_notice" },
  ],
}

// Everything else Binder prepares, below the life events.
const OTHERS: Step[] = [
  { type: "journey", journey: "tax_return" },
  { type: "folder", folder: "identity_renewal" },
  { type: "folder", folder: "mortgage" },
  { type: "letter", letter: "request" },
  { type: "letter", letter: null },
  { type: "folder", folder: null },
]

/** Life events: what to do when you move, start a job, have a child… Each one gathers the
 * checklists, letters and files Binder prepares, and what it is following stays on top. */
export function ProceduresPage() {
  const t = useT(messages)
  const agent = useAgent()
  const [event, setEvent] = useState<Event | null>(null)
  const run = useRunStep()

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="space-y-8">
        <Ongoing />
        <section>
          <h2 className="mb-3 font-semibold">{t("events")}</h2>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {EVENTS.map((e, i) => {
              const Icon = EVENT_ICON[e]
              return (
                <li key={e} className="animate-rise" style={{ "--i": i } as React.CSSProperties}>
                  <button
                    onClick={() => setEvent(e)}
                    className="group flex h-full min-h-20 w-full items-center gap-3 rounded-xl bg-card px-4 py-3.5 text-left ring-1 ring-foreground/10 transition-[background-color,box-shadow] outline-none hover:bg-accent/40 hover:shadow-sm focus-visible:ring-3 focus-visible:ring-ring"
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                      <Icon className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[0.9375rem] font-medium">{t(`event.${e}`)}</span>
                      <span className="block text-sm text-muted-foreground">{t(`event.${e}Hint`)}</span>
                    </span>
                    <CaretRightIcon className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
        <section>
          <h2 className="mb-3 font-semibold">{t("others")}</h2>
          <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {OTHERS.map((step, i) => (
              <StepRow key={i} step={step} onClick={() => run.start(step)} />
            ))}
          </ul>
        </section>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-card px-5 py-4 ring-1 ring-foreground/10">
          <p className="text-sm text-muted-foreground">{t("otherwise")}</p>
          <Button variant="outline" onClick={() => agent.open()}>
            <RobotIcon /> {t("askAgent")}
          </Button>
        </div>
        <FinishedLetters />
      </div>
      <Dialog open={event !== null} onOpenChange={(open) => !open && setEvent(null)}>
        <DialogContent className="max-h-[90vh] gap-4 overflow-y-auto sm:max-w-lg">
          {event && (
            <>
              <DialogHeader>
                <DialogTitle className="text-lg">{t(`event.${event}`)}</DialogTitle>
                <DialogDescription>{t(`event.${event}Intro`)}</DialogDescription>
              </DialogHeader>
              <ul className="space-y-2">
                {EVENT_STEPS[event].map((step, i) => (
                  <StepRow
                    key={i}
                    step={step}
                    onClick={() => {
                      setEvent(null)
                      run.start(step)
                    }}
                  />
                ))}
              </ul>
            </>
          )}
        </DialogContent>
      </Dialog>
      <PrepareDialog task={run.task} onClose={run.close} />
    </>
  )
}

/** Starts a sub-action: a checklist (or opens the one under way), a letter, a file, a question
 * to Binder, or adding the paper itself. */
function useRunStep() {
  const t = useT(messages)
  const agent = useAgent()
  const upload = useUpload()
  const panels = usePanels()
  const kinds = useJourneyKinds().data ?? []
  const active = (useJourneys().data ?? []).filter((j) => !j.closed)
  const [task, setTask] = useState<Task | null>(null)
  const start = (step: Step) => {
    switch (step.type) {
      case "journey": {
        const ongoing = active.find((j) => j.kind === step.journey)
        if (ongoing) return panels.showJourney(ongoing.id)
        const info = kinds.find((k) => k.kind === step.journey)
        if (info) setTask({ type: "journey", info })
        return
      }
      case "letter":
        return setTask({ type: "letter", kind: step.letter })
      case "folder":
        return setTask({ type: "folder", kind: step.folder })
      case "ask":
        return agent.open(t(step.prompt))
      case "scan":
        return upload.scanWithPhone()
      case "file":
        return upload.open()
    }
  }
  return { task, start, close: () => setTask(null) }
}

const STEP_ICON: Record<Step["type"], Icon> = {
  journey: ListChecksIcon,
  letter: NotePencilIcon,
  folder: FolderPlusIcon,
  ask: RobotIcon,
  scan: DeviceMobileIcon,
  file: UploadSimpleIcon,
}

function StepRow({ step, onClick }: { step: Step; onClick: () => void }) {
  const t = useT(messages)
  const tp = useT(prepareMessages)
  const kinds = useJourneyKinds().data ?? []
  const active = (useJourneys().data ?? []).filter((j) => !j.closed)
  const Icon = STEP_ICON[step.type]
  let title = ""
  let hint = ""
  if (step.type === "journey") {
    const ongoing = active.find((j) => j.kind === step.journey)
    title = kinds.find((k) => k.kind === step.journey)?.title ?? t(`journey.${step.journey}`)
    hint = ongoing ? t("journeyOngoing", { done: ongoing.done, total: ongoing.total }) : t("journeyHint")
  } else if (step.type === "letter") {
    const kind = step.letter ?? "custom"
    title = tp(`letter.${kind}`)
    hint = tp(`letter.${kind}Hint`)
  } else if (step.type === "folder") {
    title = tp(`folder.${step.folder ?? "custom"}`)
    hint = tp(`folder.${step.folder ?? "custom"}Hint`)
  } else if (step.type === "ask") {
    title = t(`${step.prompt}Title`)
    hint = t("askHint")
  } else {
    title = t(`step.${step.type}`)
    hint = t(`step.${step.type}Hint`)
  }
  return (
    <li>
      <button
        onClick={onClick}
        className="group flex min-h-14 w-full items-center gap-3 rounded-xl bg-card px-4 py-3 text-left ring-1 ring-foreground/10 transition-colors outline-none hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{title}</span>
          <span className="block text-xs text-muted-foreground">{hint}</span>
        </span>
        <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" />
      </button>
    </li>
  )
}
