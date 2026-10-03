import { useRef, useState } from "react"
import { flushSync } from "react-dom"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowUUpLeftIcon, CaretRightIcon, CheckIcon, ClockCountdownIcon, FileTextIcon, ShieldWarningIcon, WarningIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { CategoryIcon } from "@/components/CategoryIcon"
import { JourneyCard } from "@/components/journey"
import { FolderView } from "@/components/panels/FolderView"
import { LetterView } from "@/components/panels/LetterView"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { api, type ChatResponse, type Deadline, type Doc, type PendingAction } from "@/lib/api"
import { categoryLabel, daysLabel, formatAmount, formatDate } from "@/lib/format"
import { RichText } from "./RichText"
import { Steps } from "./steps"

export function AgentAnswer({ response, onNavigate }: { response: ChatResponse; onNavigate: () => void }) {
  const t = useT(messages)
  const docs = response.documents
  const confirmations = response.confirmations ?? []
  return (
    <div className="space-y-3">
      <Steps steps={response.tool_calls} stats={response.stats} />
      <p className="text-sm leading-relaxed break-words whitespace-pre-wrap">
        <RichText text={response.answer} docs={docs} onNavigate={onNavigate} />
      </p>
      {(response.warnings ?? []).map((warning) => (
        <p key={warning} className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
          <WarningIcon className="mt-0.5 size-3.5 shrink-0" /> {warning}
        </p>
      ))}
      {confirmations.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t("confirm.why")}</p>
          {confirmations.map((action) => (
            <Confirmation key={action.token} action={action} />
          ))}
        </div>
      )}
      {response.letters.map((letter, i) => (
        <LetterView key={letter.id ?? i} letter={letter} compact />
      ))}
      {response.folders.map((folder) => (
        <FolderView key={folder.key} folder={folder} />
      ))}
      {(response.journeys ?? []).map((journey) => (
        <JourneyCard key={journey.id} journey={journey} />
      ))}
      {response.changed && <Changed token={response.undo} />}
      {docs.length > 0 && <AnswerDocuments docs={docs} onNavigate={onNavigate} />}
      {response.deadlines.length > 0 && <AnswerDeadlines deadlines={response.deadlines} />}
      {response.engine === "rules" && (
        <p className="text-[0.6875rem] text-muted-foreground">{t("rulesEngine")}</p>
      )}
    </div>
  )
}

/** The documents an answer relies on; more than three fold under one line. */
function AnswerDocuments({ docs, onNavigate }: { docs: Doc[]; onNavigate: () => void }) {
  const t = useT(messages)
  const [expanded, setExpanded] = useState(docs.length <= 3)
  const list = useRef<HTMLUListElement>(null)
  // Opening the list replaces its button: focus moves to the first document instead of being lost.
  const expand = () => {
    flushSync(() => setExpanded(true))
    list.current?.querySelector("a")?.focus()
  }
  return (
    <div className="overflow-hidden rounded-lg border">
      {!expanded ? (
        <button
          type="button"
          onClick={expand}
          aria-expanded={false}
          className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-accent"
        >
          <span className="flex size-7 items-center justify-center rounded-md bg-accent text-primary">
            <FileTextIcon className="size-3.5" />
          </span>
          <span className="flex-1 text-left font-medium">{t("documents", { count: docs.length })}</span>
          <CaretRightIcon className="size-4 text-muted-foreground" />
        </button>
      ) : (
        <ul ref={list} className="divide-y">
          {docs.map((d) => (
            <li key={d.id}>
              <Link to={`/documents/${d.id}`} onClick={onNavigate} className="flex items-center gap-3 px-3 py-2 hover:bg-accent">
                <CategoryIcon category={d.category} size="sm" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{d.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {categoryLabel(d.category)} · {formatDate(d.issue_date)}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">{formatAmount(d.amount)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function AnswerDeadlines({ deadlines }: { deadlines: Deadline[] }) {
  return (
    <ul className="divide-y overflow-hidden rounded-lg border">
      {deadlines.map((d) => (
        <li key={d.id} className="flex items-center gap-3 px-3 py-2">
          <ClockCountdownIcon className="size-4 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{d.title}</span>
            <span className="block text-xs text-muted-foreground">
              {formatDate(d.due_date)} · {daysLabel(d.days_left)}
            </span>
          </span>
          <span className="text-xs text-muted-foreground">{formatAmount(d.amount)}</span>
        </li>
      ))}
    </ul>
  )
}

/** "Your documents have been updated", with a way back right after. */
function Changed({ token }: { token: string | null }) {
  const t = useT(messages)
  const invalidate = useInvalidateAll()
  const [undone, setUndone] = useState(false)
  const undo = useMutation({
    mutationFn: api.undo,
    onSuccess: () => {
      setUndone(true)
      void invalidate()
    },
  })
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <CheckIcon className="size-3.5 text-primary" /> {undone ? t("undone") : t("changed")}
      {token && !undone && (
        <Button variant="link" size="xs" className="h-auto px-1" onClick={() => undo.mutate(token)} disabled={undo.isPending}>
          <ArrowUUpLeftIcon /> {t("undo")}
        </Button>
      )}
    </p>
  )
}

/** A change the agent proposed after reading a document or a web page: made only once confirmed. */
function Confirmation({ action }: { action: PendingAction }) {
  const t = useT(messages)
  const invalidate = useInvalidateAll()
  const [skipped, setSkipped] = useState(false)
  const run = useMutation({
    mutationFn: () => api.confirmAction(action.token),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  })
  if (run.data) return <Changed token={run.data.undo} />
  if (skipped) return <p className="text-xs text-muted-foreground">{t("confirm.skipped")}</p>
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-300/60 bg-amber-50/60 px-3 py-2 text-sm dark:border-amber-500/30 dark:bg-amber-500/10">
      <ShieldWarningIcon className="size-4 shrink-0 text-amber-700 dark:text-amber-400" />
      <span className="min-w-0 flex-1 font-medium">{action.description}</span>
      <Button size="xs" onClick={() => run.mutate()} disabled={run.isPending}>
        {t("confirm.do")}
      </Button>
      <Button size="xs" variant="ghost" onClick={() => setSkipped(true)} disabled={run.isPending}>
        {t("confirm.skip")}
      </Button>
    </div>
  )
}
