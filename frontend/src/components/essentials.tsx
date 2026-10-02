import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { CheckCircleIcon, CircleDashedIcon, ArrowLeftIcon, CaretRightIcon, ListChecksIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Glossed } from "@/components/glossary"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useT } from "@/i18n"
import { essentials as messages } from "@/i18n/messages/essentials"
import { api, type Profile } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { cn } from "@/lib/utils"

type Question = "situation" | "housing" | "vehicle"
const QUESTIONS: Question[] = ["situation", "housing", "vehicle"]
// Each answer and its label.
const OPTIONS = {
  situation: [
    ["student", "situation.student"],
    ["employee", "situation.employee"],
    ["self_employed", "situation.self_employed"],
    ["job_seeker", "situation.job_seeker"],
    ["retired", "situation.retired"],
  ],
  housing: [
    ["tenant", "housing.tenant"],
    ["owner", "housing.owner"],
    ["hosted", "housing.hosted"],
  ],
  vehicle: [
    ["yes", "vehicle.yes"],
    ["no", "vehicle.no"],
  ],
} as const

/** Whether the three questions of the first launch were answered. */
export function answered(profile: Profile | undefined) {
  return !!profile && QUESTIONS.every((q) => !!profile[q])
}

/** "Tell me about yourself": three taps, one question per screen, saved in the profile. */
export function AboutYou({ onDone }: { onDone: () => void }) {
  const t = useT(messages)
  const qc = useQueryClient()
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile })
  const [step, setStep] = useState(0)
  const save = useMutation({
    mutationFn: async (answer: Partial<Profile>) => api.saveProfile({ ...(await api.profile()), ...answer }),
    onSuccess: (saved) => {
      qc.setQueryData(["profile"], saved)
      void qc.invalidateQueries({ queryKey: ["essentials"] })
      if (step < QUESTIONS.length - 1) setStep(step + 1)
      else onDone()
    },
    onError: (e) => toast.error(e.message),
  })
  const question = QUESTIONS[step]
  const current = profile.data?.[question]
  // The answer pressed goes away with its question: focus moves to the next question instead.
  const heading = useRef<HTMLHeadingElement>(null)
  const first = useRef(true)
  useEffect(() => {
    if (first.current) first.current = false
    else heading.current?.focus()
  }, [step])
  return (
    <Card className="gap-5 p-5 sm:p-7">
      <div className="flex min-h-8 items-center gap-3 text-xs font-medium text-muted-foreground">
        {step > 0 && (
          <Button variant="ghost" size="icon-sm" onClick={() => setStep(step - 1)} aria-label={t("previous")}>
            <ArrowLeftIcon />
          </Button>
        )}
        <span>{t("progress", { current: step + 1, total: QUESTIONS.length })}</span>
        <span className="ml-auto flex gap-1" aria-hidden>
          {QUESTIONS.map((q, i) => (
            <span key={q} className={cn("h-1.5 w-6 rounded-full transition-colors duration-300", i <= step ? "bg-primary" : "bg-muted")} />
          ))}
        </span>
      </div>
      {/* The next question fades in, so the change of question is seen. */}
      <div key={step} className="animate-step flex flex-col gap-5">
        <div>
          <h2 ref={heading} tabIndex={-1} className="text-xl font-semibold tracking-tight outline-none">
            {t(`${question}.question`)}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("why")}</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {OPTIONS[question].map(([value, label]) => (
            <Button
              key={value}
              size="lg"
              variant={current === value ? "default" : "outline"}
              aria-pressed={current === value}
              disabled={save.isPending}
              onClick={() => save.mutate({ [question]: value })}
              className="h-12 justify-start text-[0.9375rem]"
            >
              {t(label)}
            </Button>
          ))}
        </div>
      </div>
      <button onClick={onDone} className="self-start text-sm text-muted-foreground underline-offset-2 hover:underline">
        {t("skip")}
      </button>
    </Card>
  )
}

/** The papers you should have for your situation: why, how long to keep them, and which ones
 * Binder already holds. */
export function EssentialsList({ onChange }: { onChange?: () => void }) {
  const t = useT(messages)
  const papers = useQuery({ queryKey: ["essentials"], queryFn: api.essentials })
  if (!papers.data)
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  const present = papers.data.filter((p) => p.present).length
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-muted-foreground">{t("count", { present, total: papers.data.length })}</p>
        {onChange && (
          <button onClick={onChange} className="text-sm font-medium text-primary hover:underline">
            {t("change")}
          </button>
        )}
      </div>
      <Card className="gap-0 p-0">
        <ul className="divide-y">
          {papers.data.map((p) => (
            <li key={p.key} className="flex items-start gap-3 px-4 py-3 sm:px-5">
              <AreaIcon area={p.area} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {p.document_id ? (
                    <Link to={`/documents/${p.document_id}`} className="hover:underline">
                      {p.title}
                    </Link>
                  ) : (
                    p.title
                  )}
                </p>
                <p className="text-sm text-muted-foreground">
                  <Glossed text={p.why} />
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{t("keep", { keep: p.keep })}</p>
              </div>
              {p.present ? (
                <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                  <CheckCircleIcon className="size-4" weight="fill" /> {t("present")}
                </span>
              ) : (
                <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-muted-foreground">
                  <CircleDashedIcon className="size-4" /> {t("missing")}
                </span>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

/** The way back to the papers to have once the welcome screen is gone: a row on My papers that
 * opens the list (and the three questions, to change the answers) in a side panel. */
export function EssentialsLink() {
  const t = useT(messages)
  const papers = useQuery({ queryKey: ["essentials"], queryFn: api.essentials })
  const [open, setOpen] = useState(false)
  const [asking, setAsking] = useState(false)
  if (!papers.data?.length) return null
  const present = papers.data.filter((p) => p.present).length
  return (
    <>
      <button
        onClick={() => {
          setAsking(false)
          setOpen(true)
        }}
        className="mb-6 flex min-h-12 w-full items-center gap-3 rounded-xl bg-card px-4 py-3 text-left ring-1 ring-foreground/10 transition-shadow hover:shadow-sm"
      >
        <ListChecksIcon className="size-5 shrink-0 text-primary" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold">{t("papersLink")}</span>
          <span className="block text-xs text-muted-foreground">
            {t("papersLinkHint", { present, total: papers.data.length })}
          </span>
        </span>
        <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" />
      </button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex flex-col gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
          <SheetHeader className="border-b px-5 py-3.5 pr-12">
            <SheetTitle className="text-lg">{asking ? t("title") : t("papersTitle")}</SheetTitle>
            <SheetDescription>{asking ? t("subtitle") : t("papersSubtitle")}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
            {asking ? (
              <AboutYou onDone={() => setAsking(false)} />
            ) : (
              <EssentialsList onChange={() => setAsking(true)} />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
