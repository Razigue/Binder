import { useState } from "react"
import { CaretRightIcon, CheckIcon, CircleNotchIcon, WarningCircleIcon } from "@phosphor-icons/react"
import { useT } from "@/i18n"
import type { Translate } from "@/i18n/core"
import { agent as messages } from "@/i18n/messages/agent"
import type { ChatStats, ToolCall } from "@/lib/api"
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"
import { RichText } from "./RichText"
import { toolArguments, type Turn } from "./turns"

type T = Translate<(typeof messages)["en"]>

/** What a tool call is doing, for the user ("Searching “EDF”"). */
function useStepLabel() {
  const t = useT(messages)
  return (step: ToolCall) => {
    const query = typeof step.arguments.query === "string" ? step.arguments.query.trim() : ""
    if (step.name === "search_documents") return query ? t("tool.search_documents", { query }) : t("tool.search_all")
    const key = `tool.${step.name}`
    return key in messages.en ? t(key as "tool.other") : t("tool.other")
  }
}

/** While the answer is prepared: the steps taken, then the text as it is written. */
export function Progress({ turn, onNavigate }: { turn: Turn; onNavigate: () => void }) {
  const t = useT(messages)
  const label = useStepLabel()
  return (
    <div className="space-y-2">
      {turn.steps.length > 0 && (
        <ul className="space-y-1">
          {turn.steps.map((step, i) => {
            const running = step.duration_ms == null && i === turn.steps.length - 1 && !turn.draft
            return (
              <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                <StepIcon step={step} running={running} />
                <span className="min-w-0 truncate">{label(step)}</span>
                <StepDuration step={step} />
              </li>
            )
          })}
        </ul>
      )}
      {turn.draft ? (
        <p className="text-sm leading-relaxed break-words whitespace-pre-wrap">
          <RichText text={turn.draft} docs={[]} onNavigate={onNavigate} />
        </p>
      ) : (
        turn.steps.length === 0 && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CircleNotchIcon className="size-3.5 animate-spin" /> {t(turn.loading ? "loadingModel" : "thinking")}
          </p>
        )
      )}
      {turn.stats && <StatsLine stats={turn.stats} />}
    </div>
  )
}

function StepIcon({ step, running }: { step: ToolCall; running: boolean }) {
  if (running) return <CircleNotchIcon className="size-3 shrink-0 animate-spin" />
  if (step.error) return <WarningCircleIcon className="size-3 shrink-0 text-destructive" />
  return <CheckIcon className="size-3 shrink-0 text-primary" />
}

/** How long a tool took ("120 ms", "1.4 s"), and whether it failed. */
function StepDuration({ step }: { step: ToolCall }) {
  const t = useT(messages)
  if (step.duration_ms == null) return null
  const ms = step.duration_ms
  const value = ms < 1000 ? t("stats.ms", { value: formatNumber(ms) }) : seconds(ms / 1000, t)
  return (
    <span className="shrink-0 tabular-nums">
      {step.error ? `${t("toolFailed")} · ${value}` : value}
    </span>
  )
}

function speed(stats: ChatStats, t: T) {
  if (stats.tokens_per_second == null) return null
  return t("stats.speed", { value: formatNumber(stats.tokens_per_second, { maximumFractionDigits: 1 }) })
}

function seconds(value: number, t: T) {
  return t("stats.seconds", { value: formatNumber(value, { maximumFractionDigits: 1 }) })
}

/** Speed of the model while it works: "qwen3:8b · 42 tok/s · 3.1 s". */
function StatsLine({ stats }: { stats: ChatStats }) {
  const t = useT(messages)
  const parts = [stats.model, speed(stats, t), seconds(stats.seconds, t)].filter(Boolean)
  return <p className="text-[0.6875rem] text-muted-foreground tabular-nums">{parts.join(" · ")}</p>
}

/** Steps and model stats of a finished answer, folded under a single line. */
export function Steps({ steps, stats }: { steps: ToolCall[]; stats?: ChatStats | null }) {
  const t = useT(messages)
  const label = useStepLabel()
  const [open, setOpen] = useState(false)
  if (!steps.length && !stats) return null
  const summary = [
    steps.length ? t("steps", { count: steps.length }) : t("details"),
    stats && speed(stats, t),
    stats && seconds(stats.seconds, t),
  ].filter(Boolean)
  return (
    <div className="text-xs text-muted-foreground">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded tabular-nums select-none hover:text-foreground"
      >
        <CaretRightIcon className={cn("size-3 transition-transform", open && "rotate-90")} />
        {summary.join(" · ")}
      </button>
      {open && (
        <div className="mt-1.5 space-y-2 pl-4">
          {steps.length > 0 && (
            <ul className="space-y-1.5">
              {steps.map((step, i) => (
                <li key={i} className="min-w-0">
                  <span className="flex items-center gap-2">
                    <StepIcon step={step} running={false} />
                    <span className="min-w-0 flex-1 truncate">{label(step)}</span>
                    <StepDuration step={step} />
                  </span>
                  <code className="mt-0.5 block pl-5 font-mono text-[0.6875rem] break-all">
                    {step.name}({toolArguments(step.arguments)})
                  </code>
                </li>
              ))}
            </ul>
          )}
          {stats && <StatsTable stats={stats} />}
        </div>
      )}
    </div>
  )
}

function StatsTable({ stats }: { stats: ChatStats }) {
  const t = useT(messages)
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 tabular-nums">
      <dt>{t("stats.model")}</dt>
      <dd className="text-foreground">{stats.model}</dd>
      <dt>{t("stats.turns")}</dt>
      <dd className="text-foreground">{formatNumber(stats.turns)}</dd>
      <dt>{t("stats.read")}</dt>
      <dd className="text-foreground">
        {formatNumber(stats.prompt_tokens)}
        {stats.prompt_tokens_per_second != null &&
          ` · ${t("stats.speed", { value: formatNumber(stats.prompt_tokens_per_second, { maximumFractionDigits: 0 }) })}`}
      </dd>
      <dt>{t("stats.written")}</dt>
      <dd className="text-foreground">
        {formatNumber(stats.output_tokens)}
        {stats.tokens_per_second != null && ` · ${speed(stats, t)}`}
      </dd>
      {stats.load_seconds != null && (
        <>
          <dt>{t("stats.load")}</dt>
          <dd className="text-foreground">{seconds(stats.load_seconds, t)}</dd>
        </>
      )}
      <dt>{t("stats.total")}</dt>
      <dd className="text-foreground">{seconds(stats.seconds, t)}</dd>
    </dl>
  )
}
