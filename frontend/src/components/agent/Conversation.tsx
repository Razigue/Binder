import { useEffect, useRef, useState, type DragEvent } from "react"
import { Link } from "react-router-dom"
import { ArrowCounterClockwiseIcon, ClockCounterClockwiseIcon, FileArrowUpIcon, PaperclipIcon, PencilSimpleIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { previewUrl, type Doc } from "@/lib/api"
import { categoryLabel } from "@/lib/format"
import { ActionButton, CopyButton, MessageActions, Thumbnail } from "./actions"
import { AgentAnswer } from "./Answer"
import { Composer } from "./Composer"
import type { Viewing } from "./context"
import { Progress } from "./steps"
import { isSubmit, plainText, type Previous, type Turn } from "./turns"
import { useAttachments } from "./useAttachments"

// Suggested prompts by what the agent does, in the UI language (the agent understands both).
const SUGGESTIONS = {
  // Only while a document is open on screen: the questions are about it.
  viewing: ["explainDoc", "todoDoc", "deadlineDoc"],
  ask: ["taxIncome", "electricity", "upcoming"],
  watch: ["alerts", "renew", "october"],
  act: ["letter", "folder", "reminder", "moving"],
} as const
const GROUPS = ["viewing", "ask", "watch", "act"] as const satisfies readonly (keyof typeof SUGGESTIONS)[]

const hasFiles = (e: DragEvent) => e.dataTransfer.types.includes("Files")

export function AgentConversation({
  turns,
  pending,
  onAsk,
  onStop,
  onNavigate,
  viewing,
  onIgnoreViewing,
  previous,
  onResume,
}: {
  turns: Turn[]
  pending: boolean
  onAsk: (question: string, attachments?: Doc[], at?: number) => void
  onStop: () => void
  onNavigate: () => void
  viewing: Viewing | null
  onIgnoreViewing: () => void
  previous: Previous | null
  onResume: (id: number) => void
}) {
  const t = useT(messages)
  const [editing, setEditing] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLTextAreaElement>(null)
  const attachments = useAttachments(() => input.current?.focus())
  const scroller = useRef<HTMLDivElement>(null)

  // Follows the conversation, unless the user scrolled up to read. A new conversation shows
  // from the top: the previous one to resume, then the suggestions.
  const pinned = useRef(true)
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    if (!turns.length) {
      pinned.current = true
      el.scrollTo({ top: 0 })
    } else if (pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
  }, [turns, pending])

  const ask = (question: string, docs?: Doc[], at?: number) => {
    pinned.current = true
    onAsk(question, docs, at)
  }

  const lastTurn = turns.at(-1)
  const announcement = pending
    ? t("thinking")
    : lastTurn?.stopped
      ? t("stopped")
      : lastTurn?.response && !lastTurn.error
        ? plainText(lastTurn.response.answer)
        : ""

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col"
      onDragEnter={(e) => {
        if (!hasFiles(e)) return
        e.preventDefault()
        setDragging(true)
      }}
      onDragOver={(e) => {
        if (!hasFiles(e)) return
        e.preventDefault()
        e.dataTransfer.dropEffect = "copy"
      }}
      onDragLeave={(e) => {
        if (!(e.relatedTarget instanceof Node && e.currentTarget.contains(e.relatedTarget))) setDragging(false)
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return
        e.preventDefault()
        e.stopPropagation()
        setDragging(false)
        attachments.add(e.dataTransfer.files)
      }}
    >
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
        }}
        className="flex-1 space-y-6 overflow-y-auto px-5 py-5 select-text"
      >
        {turns.length === 0 && (
          <Welcome viewing={viewing} previous={previous} onResume={onResume} onAsk={(question) => ask(question)} />
        )}

        {turns.map((turn, i) => (
          <div key={turn.id} className="space-y-3">
            {editing === i ? (
              <EditMessage
                initial={turn.question}
                onCancel={() => setEditing(null)}
                onSave={(question) => {
                  setEditing(null)
                  ask(question, turn.attachments, i)
                }}
              />
            ) : (
              <UserMessage turn={turn} canEdit={!pending} onEdit={() => setEditing(i)} onNavigate={onNavigate} />
            )}
            <TurnAnswer
              turn={turn}
              last={i === turns.length - 1}
              pending={pending}
              onRetry={() => onAsk(turn.question, turn.attachments, i)}
              onNavigate={onNavigate}
            />
          </div>
        ))}
      </div>
      {/* Screen readers hear the finished answer, not every streamed word. */}
      <p role="status" className="sr-only">
        {announcement}
      </p>

      <Composer
        inputRef={input}
        attachments={attachments}
        pending={pending}
        onStop={onStop}
        viewing={viewing}
        onIgnoreViewing={onIgnoreViewing}
        onSend={(question, docs) => ask(question, docs)}
      />

      {dragging && (
        <div className="pointer-events-none absolute inset-2 z-10 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-primary bg-background/90 text-center">
          <FileArrowUpIcon className="size-7 text-primary" />
          <p className="text-sm font-medium">{t("dropFiles")}</p>
          <p className="text-xs text-muted-foreground">{t("dropHint")}</p>
        </div>
      )}
    </div>
  )
}

/** An empty conversation: the previous one to resume, then suggested questions. */
function Welcome({
  viewing,
  previous,
  onResume,
  onAsk,
}: {
  viewing: Viewing | null
  previous: Previous | null
  onResume: (id: number) => void
  onAsk: (question: string) => void
}) {
  const t = useT(messages)
  const groups = GROUPS.filter((group) => group !== "viewing" || viewing)
  return (
    <>
      {previous && (
        <button
          type="button"
          onClick={() => void previous.id.then((id) => id !== null && onResume(id))}
          className="flex w-full items-center gap-2.5 rounded-lg border border-dashed px-3 py-2 text-left text-sm transition-colors select-none hover:bg-accent"
        >
          <ClockCounterClockwiseIcon className="size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block text-xs text-muted-foreground">{t("previous")}</span>
            <span className="block truncate">{previous.title || t("untitled")}</span>
          </span>
          <span className="shrink-0 text-xs font-medium text-primary">{t("resume")}</span>
        </button>
      )}
      <p className="text-sm font-medium">{t("prompt")}</p>
      {groups.map((group) => (
        <div key={group}>
          <p className="mb-2 truncate text-xs font-medium text-muted-foreground">
            {t(`group.${group}`, { title: viewing?.title ?? "" })}
          </p>
          <div className="flex flex-col items-start gap-1.5">
            {SUGGESTIONS[group].map((s) => (
              <button
                type="button"
                key={s}
                onClick={() => onAsk(t(`suggestion.${s}`))}
                className="inline-flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-left text-sm transition-colors select-none hover:bg-accent"
              >
                {t(`suggestion.${s}`)}
              </button>
            ))}
          </div>
        </div>
      ))}
      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <PaperclipIcon className="mt-0.5 size-3.5 shrink-0" /> {t("attachTip")}
      </p>
    </>
  )
}

/** The answer to a turn: written, being written, stopped or failed. */
function TurnAnswer({
  turn,
  last,
  pending,
  onRetry,
  onNavigate,
}: {
  turn: Turn
  last: boolean
  pending: boolean
  onRetry: () => void
  onNavigate: () => void
}) {
  const t = useT(messages)
  return (
    <div className="group/answer">
      {turn.error ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <span className="flex-1">{turn.error}</span>
          {!pending && (
            <Button variant="outline" size="xs" onClick={onRetry}>
              <ArrowCounterClockwiseIcon /> {t("retry")}
            </Button>
          )}
        </div>
      ) : turn.stopped ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground italic">
          {t("stopped")}
          {!pending && (
            <Button variant="ghost" size="xs" onClick={onRetry}>
              <ArrowCounterClockwiseIcon /> {t("retry")}
            </Button>
          )}
        </div>
      ) : turn.response ? (
        <>
          <AgentAnswer response={turn.response} onNavigate={onNavigate} />
          <MessageActions visible={last}>
            <CopyButton text={plainText(turn.response.answer)} />
            {last && !pending && (
              <ActionButton label={t("regenerate")} onClick={onRetry}>
                <ArrowCounterClockwiseIcon />
              </ActionButton>
            )}
          </MessageActions>
        </>
      ) : (
        <Progress turn={turn} onNavigate={onNavigate} />
      )}
    </div>
  )
}

function UserMessage({
  turn,
  canEdit,
  onEdit,
  onNavigate,
}: {
  turn: Turn
  canEdit: boolean
  onEdit: () => void
  onNavigate: () => void
}) {
  const t = useT(messages)
  // The attachments as analysed by the answer, when it is there.
  const docs = turn.attachments.map((a) => turn.response?.documents.find((d) => d.id === a.id) ?? a)
  return (
    <div className="group/answer flex flex-col items-end gap-1.5">
      {docs.length > 0 && (
        <div className="flex max-w-[85%] flex-wrap justify-end gap-1.5">
          {docs.map((d) => (
            <Link
              key={d.id}
              to={`/documents/${d.id}`}
              onClick={onNavigate}
              className="flex max-w-56 items-center gap-2 rounded-lg border bg-card p-1 pr-2.5 text-xs transition-colors select-none hover:bg-accent"
            >
              <Thumbnail src={previewUrl(d.id)} />
              <span className="min-w-0">
                <span className="block truncate font-medium">{d.title || d.filename}</span>
                <span className="block truncate text-muted-foreground">{categoryLabel(d.category)}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
      {turn.question ? (
        <p className="max-w-[85%] rounded-xl rounded-br-sm bg-accent px-3.5 py-2 text-sm break-words whitespace-pre-wrap">
          {turn.question}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{t("attachedOnly")}</p>
      )}
      <MessageActions>
        {turn.question && <CopyButton text={turn.question} />}
        {canEdit && (
          <ActionButton label={t("edit")} onClick={onEdit}>
            <PencilSimpleIcon />
          </ActionButton>
        )}
      </MessageActions>
    </div>
  )
}

function EditMessage({
  initial,
  onCancel,
  onSave,
}: {
  initial: string
  onCancel: () => void
  onSave: (question: string) => void
}) {
  const t = useT(messages)
  const [value, setValue] = useState(initial)
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }, [])
  return (
    <div className="rounded-xl border bg-card p-2 shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel()
          if (isSubmit(e) && value.trim()) {
            e.preventDefault()
            onSave(value)
          }
        }}
        rows={1}
        autoComplete="off"
        aria-label={t("edit")}
        className="field-sizing-content max-h-60 min-h-10 w-full resize-none bg-transparent px-1.5 py-1 text-sm outline-none"
      />
      <div className="flex justify-end gap-1.5">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          {t("cancel")}
        </Button>
        <Button size="sm" onClick={() => onSave(value)} disabled={!value.trim()}>
          {t("save")}
        </Button>
      </div>
    </div>
  )
}
