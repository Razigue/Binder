import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { CheckCircleIcon, CircleDashedIcon, ArrowLeftIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
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
  return (
    <Card className="gap-5 p-5 sm:p-7">
      <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground">
        {step > 0 && (
          <Button variant="ghost" size="icon-sm" onClick={() => setStep(step - 1)} aria-label={t("previous")}>
            <ArrowLeftIcon />
          </Button>
        )}
        <span>{t("progress", { current: step + 1, total: QUESTIONS.length })}</span>
        <span className="ml-auto flex gap-1" aria-hidden>
          {QUESTIONS.map((q, i) => (
            <span key={q} className={cn("h-1.5 w-6 rounded-full", i <= step ? "bg-primary" : "bg-muted")} />
          ))}
        </span>
      </div>
      <div>
        <h2 className="text-xl font-semibold tracking-tight">{t(`${question}.question`)}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("why")}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {OPTIONS[question].map(([value, label]) => (
          <Button
            key={value}
            size="lg"
            variant={current === value ? "default" : "outline"}
            disabled={save.isPending}
            onClick={() => save.mutate({ [question]: value })}
            className="h-12 justify-start text-[15px]"
          >
            {t(label)}
          </Button>
        ))}
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
                <p className="text-sm text-muted-foreground">{p.why}</p>
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
