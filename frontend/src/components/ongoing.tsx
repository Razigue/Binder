import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { CaretRightIcon, CheckCircleIcon, NotePencilIcon, ListChecksIcon, EnvelopeIcon, XIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { usePanels } from "@/components/panels"
import { useDeleteLetter, useInvalidateAll, useJourneys, useLetters, useUpdateJourney } from "@/hooks/queries"
import { useT } from "@/i18n"
import { journey as journeyMessages } from "@/i18n/messages/journey"
import { prepare as messages } from "@/i18n/messages/prepare"
import { api, type Journey, type Letter } from "@/lib/api"
import { formatDate, toIso } from "@/lib/format"
import { cn } from "@/lib/utils"

type LetterState = "draft" | "sent" | "noAnswer" | "answered"

function letterState(letter: Letter): LetterState {
  if (letter.answered) return "answered"
  if (!letter.sent_on) return "draft"
  return letter.follow_up_on && letter.follow_up_on <= toIso(new Date()) ? "noAnswer" : "sent"
}

// Overdue follow-ups first, then drafts to send, then letters awaiting their answer.
const LETTER_ORDER: Record<LetterState, number> = { noAnswer: 0, draft: 1, sent: 2, answered: 3 }

/** What Binder is following for the user: journeys under way, letters still waiting for something. */
export function useOngoing() {
  const journeys = (useJourneys().data ?? []).filter((j) => !j.closed)
  const letters = (useLetters().data ?? [])
    .filter((l) => l.id !== null && letterState(l) !== "answered")
    .sort((a, b) => LETTER_ORDER[letterState(a)] - LETTER_ORDER[letterState(b)])
  return { journeys, letters, count: journeys.length + letters.length }
}

/** The "In progress" card, on top of Life events. */
export function Ongoing() {
  const t = useT(messages)
  const panels = usePanels()
  const { journeys, letters, count } = useOngoing()
  if (!count) return null
  const rows = [
    ...journeys.map((j) => <JourneyRow key={`j${j.id}`} journey={j} onOpen={() => panels.showJourney(j.id)} />),
    ...letters.map((l) => <LetterRow key={`l${l.id}`} letter={l} />),
  ]
  return (
    <Card className="gap-0 p-0">
      <div className="px-5 pt-4 pb-3">
        <h2 className="font-semibold">{t("ongoing")}</h2>
      </div>
      <ul className="divide-y border-t">{rows}</ul>
    </Card>
  )
}

function JourneyRow({ journey, onOpen }: { journey: Journey; onOpen: () => void }) {
  const t = useT(messages)
  const tj = useT(journeyMessages)
  const [confirming, setConfirming] = useState(false)
  const close = useUpdateJourney()
  const next = journey.steps.find((s) => !s.done)
  return (
    <li className="group/row relative">
      <button onClick={onOpen} className="flex w-full items-center gap-3 px-5 py-3 pr-11 text-left transition-colors hover:bg-muted/40">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <ListChecksIcon className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="truncate text-sm font-medium">{journey.title}</span>
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {tj("progress", { done: journey.done, total: journey.total })}
            </span>
          </span>
          <Progress value={journey.total ? (journey.done / journey.total) * 100 : 0} className="mt-1.5" aria-hidden />
          <span className="mt-1 block truncate text-xs text-muted-foreground">
            {next ? tj("nextStep", { step: next.title }) : tj("allDone")}
          </span>
        </span>
        <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" />
      </button>
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute top-2.5 right-2 opacity-0 transition-opacity group-hover/row:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
        aria-label={t("removeTask")}
        title={t("removeTask")}
        onClick={(e) => {
          e.stopPropagation()
          setConfirming(true)
        }}
      >
        <XIcon />
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("removeJourney", { title: journey.title })}
        description={t("removeJourneyHint")}
        confirmLabel={t("removeTask")}
        onConfirm={async () => {
          await close.mutateAsync({ id: journey.id, closed: true })
          toast.success(t("taskRemoved"))
        }}
      />
    </li>
  )
}

function LetterRow({ letter }: { letter: Letter }) {
  const t = useT(messages)
  const panels = usePanels()
  const invalidate = useInvalidateAll()
  const [confirming, setConfirming] = useState(false)
  const state = letterState(letter)
  const answered = useMutation({
    mutationFn: () => api.letterAnswered(letter.id!),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  })
  const followUp = useMutation({
    mutationFn: () => api.letterFollowUp(letter.id!),
    onSuccess: (l) => {
      invalidate()
      panels.showLetter(l)
    },
    onError: (e) => toast.error(e.message),
  })
  const remove = useDeleteLetter()
  const detail =
    state === "draft"
      ? t("status.draft")
      : state === "noAnswer"
        ? t("status.noAnswer", { date: formatDate(letter.sent_on) })
        : t("status.sent", { date: formatDate(letter.sent_on), followUp: formatDate(letter.follow_up_on) })
  const pending = answered.isPending || followUp.isPending || remove.isPending
  return (
    <li className="group/row relative flex gap-3 px-5 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
        <EnvelopeIcon className="size-4" />
      </span>
      <div className="min-w-0 flex-1 pr-7">
        <button
          onClick={() => panels.showLetter(letter)}
          className="block max-w-full truncate text-left text-sm font-medium hover:underline"
        >
          {letter.subject}
        </button>
        <p className="truncate text-xs text-muted-foreground">{letter.recipient}</p>
        <p
          className={cn(
            "mt-0.5 text-xs",
            state === "noAnswer" ? "font-medium text-amber-700 dark:text-amber-400" : "text-muted-foreground",
          )}
        >
          {detail}
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {state === "noAnswer" && (
            <Button size="xs" disabled={pending} onClick={() => followUp.mutate()}>
              <NotePencilIcon /> {t("followUp")}
            </Button>
          )}
          {state === "draft" ? (
            <Button size="xs" variant="outline" onClick={() => panels.showLetter(letter)}>
              {t("seeLetter")}
            </Button>
          ) : (
            <Button size="xs" variant="outline" disabled={pending} onClick={() => answered.mutate()}>
              <CheckCircleIcon /> {t("markAnswered")}
            </Button>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute top-2.5 right-2 opacity-0 transition-opacity group-hover/row:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
        disabled={pending}
        aria-label={t("removeTask")}
        title={t("removeTask")}
        onClick={() => setConfirming(true)}
      >
        <XIcon />
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("removeLetter")}
        description={t("removeLetterHint", { subject: letter.subject })}
        confirmLabel={t("removeTask")}
        onConfirm={async () => {
          await remove.mutateAsync(letter.id!)
          toast.success(t("taskRemoved"))
        }}
      />
    </li>
  )
}

/** Letters that got their answer, kept for the record. */
export function FinishedLetters() {
  const t = useT(messages)
  const panels = usePanels()
  const done = (useLetters().data ?? []).filter((l) => l.answered)
  if (!done.length) return null
  return (
    <section>
      <h2 className="mb-3 font-semibold">{t("finished")}</h2>
      <Card className="gap-0 p-0">
        <ul className="divide-y">
          {done.map((l) => (
            <li key={l.id}>
              <button
                onClick={() => panels.showLetter(l)}
                className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-muted/40"
              >
                <EnvelopeIcon className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{l.subject}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {l.recipient} · {t("status.answered")}
                  </span>
                </span>
                <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" />
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </section>
  )
}
