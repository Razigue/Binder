import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ClipboardEvent,
  type Dispatch,
  type DragEvent,
  type KeyboardEvent,
  type ReactNode,
  type Ref,
  type SetStateAction,
} from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowUpIcon, RobotIcon, ClockCountdownIcon, CameraIcon, CheckIcon, CaretRightIcon, CopyIcon, FileTextIcon, FileArrowUpIcon, CircleNotchIcon, WarningCircleIcon, PaperclipIcon, PencilSimpleIcon, ArrowCounterClockwiseIcon, SquareIcon, PencilSimpleLineIcon, ArrowUUpLeftIcon, XIcon, ShieldWarningIcon, WarningIcon } from "@phosphor-icons/react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { useInvalidateAll } from "@/hooks/queries"
import {
  api,
  previewUrl,
  type ChatMessage,
  type ChatResponse,
  type ChatStats,
  type Doc,
  type PendingAction,
  type ToolCall,
} from "@/lib/api"
import { useT } from "@/i18n"
import type { Translate } from "@/i18n/core"
import { agent as messages } from "@/i18n/messages/agent"
import { categoryLabel, daysLabel, formatAmount, formatDate, formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"
import { CategoryIcon } from "./CategoryIcon"
import { JourneyCard } from "./journey"
import { FolderView, LetterView } from "./panels"
import { ACCEPT } from "./upload"

// Suggested prompts by what the agent does, in the UI language (the agent understands both).
const SUGGESTIONS = {
  // Only while a document is open on screen: the questions are about it.
  viewing: ["explainDoc", "todoDoc", "deadlineDoc"],
  ask: ["taxIncome", "electricity", "upcoming"],
  watch: ["alerts", "renew", "october"],
  act: ["letter", "folder", "reminder", "moving"],
} as const
// Same limit as the backend (attachments per message).
const MAX_ATTACHMENTS = 10

interface Turn {
  id: number
  question: string
  /** Documents joined to the question, as uploaded (the answer carries their analysed version). */
  attachments: Doc[]
  response?: ChatResponse
  /** Tools started so far, shown while the answer is prepared. */
  steps: ToolCall[]
  /** Answer text as it is written (streamed). */
  draft: string
  /** Model token counts and speed so far. */
  stats?: ChatStats
  error?: string
  stopped?: boolean
}

/** A file attached in the composer, imported into Binder as soon as it is added. */
interface Draft {
  key: string
  file: File
  /** Local thumbnail of an image, until the document exists. */
  thumbnail?: string
  doc?: Doc
  error?: string
}

/** Document open on screen: questions that name no other document are about it. */
interface Viewing {
  id: number
  title: string
}

const AgentContext = createContext<{
  open: (question?: string) => void
  setViewing: Dispatch<SetStateAction<Viewing | null>>
} | null>(null)

export function useAgent() {
  const ctx = useContext(AgentContext)
  if (!ctx) throw new Error("useAgent must be used inside AgentProvider")
  return ctx
}

/** Tells the agent which document the page shows, while it is shown. */
export function useAgentViewing(doc: Viewing | undefined) {
  const { setViewing } = useAgent()
  const id = doc?.id
  const title = doc?.title
  useEffect(() => {
    if (id === undefined || title === undefined) return
    setViewing({ id, title })
    return () => setViewing((current) => (current?.id === id ? null : current))
  }, [id, title, setViewing])
}

/** Text of an answer as copied: without citation markers, links reduced to their label. */
function plainText(text: string) {
  return text
    .replace(/\s?\[#\d+\]/g, "")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .trim()
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const t = useT(messages)
  const [isOpen, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState(false)
  const [viewing, setViewing] = useState<Viewing | null>(null)
  // Document on screen the user unlinked from their questions, until another one is shown.
  const [ignored, setIgnored] = useState<number | null>(null)
  const about = viewing && viewing.id !== ignored ? viewing : null
  const controller = useRef<AbortController | null>(null)
  const nextId = useRef(0)
  const invalidate = useInvalidateAll()

  const update = (id: number, patch: Partial<Turn>) =>
    setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)))

  /** Sends a question; `at` replaces that turn and the following ones (edit, regenerate). */
  const ask = (question: string, attachments: Doc[] = [], at = turns.length) => {
    const q = question.trim()
    if ((!q && !attachments.length) || pending) return
    const kept = turns.slice(0, at)
    const history: ChatMessage[] = kept.flatMap((turn) =>
      turn.response
        ? [
            { role: "user", content: turn.question },
            {
              role: "assistant",
              content: turn.response.answer,
              documents: turn.response.documents.map((d) => d.id),
            },
          ]
        : [],
    )
    const id = ++nextId.current
    setTurns([...kept, { id, question: q, attachments, steps: [], draft: "" }])
    const abort = new AbortController()
    controller.current = abort
    setPending(true)
    const progress = (patch: (turn: Turn) => Partial<Turn>) =>
      setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, ...patch(turn) } : turn)))
    api
      .chatStream(
        q,
        history,
        attachments.map((d) => d.id),
        (event) => {
          if (event.type === "tool")
            progress((turn) => ({ steps: [...turn.steps, { name: event.name, arguments: event.arguments }] }))
          else if (event.type === "tool_done")
            progress((turn) => ({
              steps: turn.steps.map((step, i) =>
                i === turn.steps.length - 1 ? { ...step, duration_ms: event.duration_ms, error: event.error } : step,
              ),
            }))
          else if (event.type === "stats") progress(() => ({ stats: event.stats }))
          else if (event.type === "token") progress((turn) => ({ draft: turn.draft + event.text }))
          else if (event.type === "step") progress(() => ({ draft: "" }))
        },
        abort.signal,
        about?.id,
      )
      .then((response) => {
        update(id, { response })
        if (attachments.length || response.changed) invalidate()
      })
      .catch((err: Error) => update(id, abort.signal.aborted ? { stopped: true } : { error: err.message }))
      .finally(() => {
        if (controller.current !== abort) return
        controller.current = null
        setPending(false)
      })
  }

  const stop = () => {
    controller.current?.abort()
    controller.current = null
    setPending(false)
  }

  const reset = () => {
    stop()
    setTurns([])
  }

  const open = (question?: string) => {
    setOpen(true)
    if (question) ask(question)
  }

  // Ctrl K (Cmd K) opens the agent from anywhere, ready to type.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <AgentContext.Provider value={{ open, setViewing }}>
      {children}
      <Sheet open={isOpen} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-lg">
          <SheetHeader className="flex-row items-center gap-2 border-b px-5 py-3.5 pr-12">
            <SheetTitle className="flex flex-1 items-center gap-2.5 text-lg">
              <RobotIcon className="size-5 text-primary" />
              {t("title")}
            </SheetTitle>
            <SheetDescription className="sr-only">{t("description")}</SheetDescription>
            {turns.length > 0 && (
              <Button variant="ghost" size="icon-sm" onClick={reset} title={t("newChat")} aria-label={t("newChat")}>
                <PencilSimpleLineIcon />
              </Button>
            )}
          </SheetHeader>
          <AgentConversation
            turns={turns}
            pending={pending}
            onAsk={ask}
            onStop={stop}
            onNavigate={() => setOpen(false)}
            viewing={about}
            onIgnoreViewing={() => setIgnored(about?.id ?? null)}
          />
        </SheetContent>
      </Sheet>
    </AgentContext.Provider>
  )
}

function AgentConversation({
  turns,
  pending,
  onAsk,
  onStop,
  onNavigate,
  viewing,
  onIgnoreViewing,
}: {
  turns: Turn[]
  pending: boolean
  onAsk: (question: string, attachments?: Doc[], at?: number) => void
  onStop: () => void
  onNavigate: () => void
  viewing: Viewing | null
  onIgnoreViewing: () => void
}) {
  const t = useT(messages)
  const [editing, setEditing] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const composer = useRef<ComposerHandle>(null)
  const scroller = useRef<HTMLDivElement>(null)

  // Follows the conversation, unless the user scrolled up to read.
  const pinned = useRef(true)
  useEffect(() => {
    const el = scroller.current
    if (el && pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
  }, [turns, pending])

  const groups = (Object.keys(SUGGESTIONS) as (keyof typeof SUGGESTIONS)[]).filter(
    (group) => group !== "viewing" || viewing,
  )
  const hasFiles = (e: DragEvent) => e.dataTransfer.types.includes("Files")

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
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return
        e.preventDefault()
        e.stopPropagation()
        setDragging(false)
        composer.current?.addFiles(e.dataTransfer.files)
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
          <>
            <p className="text-sm font-medium">{t("prompt")}</p>
            {groups.map((group) => (
              <div key={group}>
                <p className="mb-2 truncate text-xs font-medium text-muted-foreground">
                  {t(`group.${group}`, { title: viewing?.title ?? "" })}
                </p>
                <div className="flex flex-col items-start gap-1.5">
                  {SUGGESTIONS[group].map((s) => (
                    <button
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
        )}

        {turns.map((turn, i) => {
          const last = i === turns.length - 1
          const docs = turn.attachments.map((a) => turn.response?.documents.find((d) => d.id === a.id) ?? a)
          return (
            <div key={turn.id} className="space-y-3">
              {editing === i ? (
                <EditMessage
                  initial={turn.question}
                  onCancel={() => setEditing(null)}
                  onSave={(question) => {
                    setEditing(null)
                    pinned.current = true
                    onAsk(question, turn.attachments, i)
                  }}
                />
              ) : (
                <UserMessage
                  turn={turn}
                  docs={docs}
                  canEdit={!pending}
                  onEdit={() => setEditing(i)}
                  onNavigate={onNavigate}
                />
              )}
              <div className="group/answer">
                {turn.error ? (
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                    <span className="flex-1">{turn.error}</span>
                    {!pending && (
                      <Button variant="outline" size="xs" onClick={() => onAsk(turn.question, turn.attachments, i)}>
                        <ArrowCounterClockwiseIcon /> {t("retry")}
                      </Button>
                    )}
                  </div>
                ) : turn.stopped ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground italic">
                    {t("stopped")}
                    {!pending && (
                      <Button variant="ghost" size="xs" onClick={() => onAsk(turn.question, turn.attachments, i)}>
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
                        <ActionButton
                          label={t("regenerate")}
                          onClick={() => onAsk(turn.question, turn.attachments, i)}
                        >
                          <ArrowCounterClockwiseIcon />
                        </ActionButton>
                      )}
                    </MessageActions>
                  </>
                ) : (
                  <Progress turn={turn} onNavigate={onNavigate} />
                )}
              </div>
            </div>
          )
        })}
      </div>

      <Composer
        ref={composer}
        pending={pending}
        onStop={onStop}
        viewing={viewing}
        onIgnoreViewing={onIgnoreViewing}
        onSend={(question, attachments) => {
          pinned.current = true
          onAsk(question, attachments)
        }}
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

function UserMessage({
  turn,
  docs,
  canEdit,
  onEdit,
  onNavigate,
}: {
  turn: Turn
  docs: Doc[]
  canEdit: boolean
  onEdit: () => void
  onNavigate: () => void
}) {
  const t = useT(messages)
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

/** Enter sends, Shift+Enter goes to the line; nothing is sent while an IME is composing. */
function isSubmit(e: KeyboardEvent) {
  return e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing
}

function MessageActions({ children, visible = false }: { children: ReactNode; visible?: boolean }) {
  return (
    <div
      className={cn(
        "mt-1 flex gap-0.5 transition-opacity select-none group-hover/answer:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100",
        visible ? "opacity-100" : "opacity-0",
      )}
    >
      {children}
    </div>
  )
}

function ActionButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      onClick={onClick}
      title={label}
      aria-label={label}
      className="text-muted-foreground"
    >
      {children}
    </Button>
  )
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const t = useT(messages)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])
  return (
    <ActionButton
      label={copied ? t("copied") : (label ?? t("copy"))}
      onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
    </ActionButton>
  )
}

function Thumbnail({ src, className }: { src?: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <span
      className={cn(
        "flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted text-muted-foreground",
        className,
      )}
    >
      {src && !failed ? (
        <img src={src} alt="" onError={() => setFailed(true)} className="size-full object-cover" />
      ) : (
        <FileTextIcon className="size-4" />
      )}
    </span>
  )
}

/** Same formats as the import dialog (the type of a dropped file is sometimes empty). */
function accepted(file: File) {
  return ACCEPT.split(",").includes(file.type) || /\.(pdf|jpe?g|png)$/i.test(file.name)
}

interface ComposerHandle {
  addFiles: (files: FileList | File[]) => void
}

function Composer({
  ref,
  pending,
  onSend,
  onStop,
  viewing,
  onIgnoreViewing,
}: {
  ref: Ref<ComposerHandle>
  pending: boolean
  onSend: (question: string, attachments: Doc[]) => void
  onStop: () => void
  viewing: Viewing | null
  onIgnoreViewing: () => void
}) {
  const t = useT(messages)
  const [text, setText] = useState("")
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [camera, setCamera] = useState(false)
  const input = useRef<HTMLTextAreaElement>(null)
  const filePicker = useRef<HTMLInputElement>(null)
  const photoPicker = useRef<HTMLInputElement>(null)
  const invalidate = useInvalidateAll()

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files).filter(accepted)
      if (!list.length) return
      const fresh: Draft[] = list.map((file, i) => ({
        key: `${Date.now()}-${i}-${file.name}`,
        file,
        thumbnail: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
      }))
      setDrafts((prev) => [...prev, ...fresh].slice(0, MAX_ATTACHMENTS))
      for (const draft of fresh) {
        api
          .upload(draft.file)
          .then((doc) => setDrafts((prev) => prev.map((d) => (d.key === draft.key ? { ...d, doc } : d))))
          .catch((err: Error) =>
            setDrafts((prev) => prev.map((d) => (d.key === draft.key ? { ...d, error: err.message } : d))),
          )
          .finally(invalidate)
      }
      input.current?.focus()
    },
    [invalidate],
  )

  useImperativeHandle(ref, () => ({ addFiles }), [addFiles])

  const remove = (draft: Draft) => {
    if (draft.thumbnail) URL.revokeObjectURL(draft.thumbnail)
    setDrafts((prev) => prev.filter((d) => d.key !== draft.key))
  }

  const uploading = drafts.some((d) => !d.doc && !d.error)
  const ready = drafts.flatMap((d) => (d.doc ? [d.doc] : []))
  const canSend = !pending && !uploading && (text.trim() !== "" || ready.length > 0)

  const submit = () => {
    if (!canSend) return
    onSend(text, ready)
    for (const d of drafts) if (d.thumbnail) URL.revokeObjectURL(d.thumbnail)
    setText("")
    setDrafts([])
  }

  const onPaste = (e: ClipboardEvent) => {
    if (!e.clipboardData.files.length) return
    e.preventDefault()
    addFiles(e.clipboardData.files)
  }

  const takePhoto = () => {
    // Without camera access from the page (some webviews), the system picker may offer the camera.
    if (typeof navigator.mediaDevices?.getUserMedia === "function") setCamera(true)
    else photoPicker.current?.click()
  }

  return (
    <div className="border-t p-3">
      <div className="rounded-xl border bg-card shadow-xs transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30">
        {viewing && (
          <div className="flex px-2.5 pt-2.5">
            <span
              className="inline-flex max-w-full items-center gap-1.5 rounded-md border bg-background py-0.5 pr-0.5 pl-2 text-xs text-muted-foreground"
              title={t("viewingHint")}
            >
              <FileTextIcon className="size-3.5 shrink-0" />
              <span className="truncate">{t("viewing", { title: viewing.title })}</span>
              <button
                onClick={onIgnoreViewing}
                aria-label={t("ignoreViewing")}
                title={t("ignoreViewing")}
                className="flex size-5 shrink-0 items-center justify-center rounded-full hover:bg-muted hover:text-foreground"
              >
                <XIcon className="size-3" />
              </button>
            </span>
          </div>
        )}
        {drafts.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-2.5 pt-2.5">
            {drafts.map((d) => (
              <div
                key={d.key}
                className={cn(
                  "group/draft relative flex max-w-48 items-center gap-2 rounded-lg border bg-background p-1 pr-6 text-xs",
                  d.error && "border-destructive/40",
                )}
                title={d.error}
              >
                <span className="relative">
                  <Thumbnail src={d.thumbnail ?? (d.doc ? previewUrl(d.doc.id) : undefined)} />
                  {!d.doc && !d.error && (
                    <span className="absolute inset-0 flex items-center justify-center rounded-md bg-background/60">
                      <CircleNotchIcon className="size-3.5 animate-spin" />
                    </span>
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">{d.file.name}</span>
                  <span className={cn("block truncate", d.error ? "text-destructive" : "text-muted-foreground")}>
                    {d.error ?? (d.doc ? t("ready") : t("uploading"))}
                  </span>
                </span>
                <button
                  onClick={() => remove(d)}
                  aria-label={t("remove", { name: d.file.name })}
                  className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <XIcon className="size-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (!isSubmit(e)) return
            e.preventDefault()
            submit()
          }}
          onPaste={onPaste}
          placeholder={t("inputPlaceholder")}
          aria-label={t("inputPlaceholder")}
          rows={1}
          autoComplete="off"
          autoFocus
          className="field-sizing-content block max-h-48 min-h-11 w-full resize-none bg-transparent px-3.5 pt-3 pb-1 text-sm outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center gap-1 px-2 pb-2">
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={drafts.length >= MAX_ATTACHMENTS}
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("attach")}
                  title={t("attach")}
                  className="text-muted-foreground"
                />
              }
            >
              <PaperclipIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" side="top" className="w-52">
              <DropdownMenuItem onClick={() => filePicker.current?.click()}>
                <FileArrowUpIcon /> {t("attachFile")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={takePhoto}>
                <CameraIcon /> {t("takePhoto")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="flex-1 truncate px-1 text-[11px] text-muted-foreground max-sm:hidden">
            {t("keyboardHint")}
          </span>
          {pending ? (
            <Button size="icon-sm" onClick={onStop} aria-label={t("stop")} title={t("stop")} className="ml-auto rounded-full">
              <SquareIcon className="size-3 fill-current" />
            </Button>
          ) : (
            <Button
              size="icon-sm"
              onClick={submit}
              disabled={!canSend}
              aria-label={t("send")}
              title={t("send")}
              className="ml-auto rounded-full"
            >
              {uploading ? <CircleNotchIcon className="animate-spin" /> : <ArrowUpIcon />}
            </Button>
          )}
        </div>
      </div>
      <input
        ref={filePicker}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files ?? [])
          e.target.value = ""
        }}
      />
      <input
        ref={photoPicker}
        type="file"
        accept="image/jpeg,image/png"
        capture="environment"
        hidden
        onChange={(e) => {
          addFiles(e.target.files ?? [])
          e.target.value = ""
        }}
      />
      <CameraDialog
        open={camera}
        onOpenChange={setCamera}
        onCapture={(file) => addFiles([file])}
        onFallback={() => photoPicker.current?.click()}
      />
    </div>
  )
}

function CameraDialog({
  open,
  onOpenChange,
  onCapture,
  onFallback,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCapture: (file: File) => void
  onFallback: () => void
}) {
  const t = useT(messages)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-4 sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("cameraTitle")}</DialogTitle>
          <DialogDescription>{t("cameraDescription")}</DialogDescription>
        </DialogHeader>
        {/* Mounted while the dialog is shown: the camera is released when it closes. */}
        <CameraView
          onClose={() => onOpenChange(false)}
          onCapture={(file) => {
            onCapture(file)
            onOpenChange(false)
          }}
          onFallback={() => {
            onOpenChange(false)
            onFallback()
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function CameraView({
  onClose,
  onCapture,
  onFallback,
}: {
  onClose: () => void
  onCapture: (file: File) => void
  onFallback: () => void
}) {
  const t = useT(messages)
  const video = useRef<HTMLVideoElement>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active: MediaStream | null = null
    let cancelled = false
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } } })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((track) => track.stop())
        active = s
        setStream(s)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      active?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  useEffect(() => {
    if (video.current) video.current.srcObject = stream
  }, [stream])

  const capture = () => {
    const v = video.current
    if (!v || !v.videoWidth) return
    const canvas = document.createElement("canvas")
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    canvas.getContext("2d")?.drawImage(v, 0, 0)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-")
        onCapture(new File([blob], `photo-${stamp}.jpg`, { type: "image/jpeg" }))
      },
      "image/jpeg",
      0.92,
    )
  }

  if (failed)
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-10 text-center text-sm text-muted-foreground">
        <CameraIcon className="size-6" />
        {t("cameraUnavailable")}
        <Button variant="outline" size="sm" onClick={onFallback}>
          {t("chooseImage")}
        </Button>
      </div>
    )

  return (
    <>
      <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-black">
        <video ref={video} autoPlay playsInline muted className="size-full object-contain" />
        {!stream && <CircleNotchIcon className="absolute size-6 animate-spin text-white/70" />}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button onClick={capture} disabled={!stream}>
          <CameraIcon /> {t("capture")}
        </Button>
      </div>
    </>
  )
}

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
function Progress({ turn, onNavigate }: { turn: Turn; onNavigate: () => void }) {
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
            <CircleNotchIcon className="size-3.5 animate-spin" /> {t("thinking")}
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
  const value =
    ms < 1000
      ? t("stats.ms", { value: formatNumber(ms) })
      : t("stats.seconds", { value: formatNumber(ms / 1000, { maximumFractionDigits: 1 }) })
  return (
    <span className="shrink-0 tabular-nums opacity-70">
      {step.error ? `${t("toolFailed")} · ${value}` : value}
    </span>
  )
}

function speed(stats: ChatStats, t: Translate<(typeof messages)["en"]>) {
  if (stats.tokens_per_second == null) return null
  return t("stats.speed", { value: formatNumber(stats.tokens_per_second, { maximumFractionDigits: 1 }) })
}

function seconds(value: number, t: Translate<(typeof messages)["en"]>) {
  return t("stats.seconds", { value: formatNumber(value, { maximumFractionDigits: 1 }) })
}

/** Speed of the model while it works: "qwen3:8b · 42 tok/s · 3.1 s". */
function StatsLine({ stats }: { stats: ChatStats }) {
  const t = useT(messages)
  const parts = [stats.model, speed(stats, t), seconds(stats.seconds, t)].filter(Boolean)
  return <p className="text-[11px] text-muted-foreground tabular-nums">{parts.join(" · ")}</p>
}

/** Steps and model stats of a finished answer, folded under a single line. */
function Steps({ steps, stats }: { steps: ToolCall[]; stats?: ChatStats | null }) {
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
                  <code className="mt-0.5 block pl-5 font-mono text-[11px] break-all opacity-70">
                    {step.name}({toolArguments(step.arguments)})
                  </code>
                </li>
              ))}
            </ul>
          )}
          {stats && (
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
              <dt>{t("stats.total")}</dt>
              <dd className="text-foreground">{seconds(stats.seconds, t)}</dd>
            </dl>
          )}
        </div>
      )}
    </div>
  )
}

/** Arguments of a tool call as the model wrote them, kept short. */
function toolArguments(args: Record<string, unknown>) {
  return Object.entries(args)
    .map(([key, value]) => {
      const text = JSON.stringify(value) ?? "null"
      return `${key}=${text.length > 80 ? `${text.slice(0, 79)}…` : text}`
    })
    .join(", ")
}

/** Minimal rendering of the agent's text: links [text](url), citations [#id] and **bold**. */
function RichText({ text, docs, onNavigate }: { text: string; docs: Doc[]; onNavigate: () => void }) {
  const t = useT(messages)
  const parts = text.split(/(\[[^\]]+\]\([^)]+\)|\s?\[#\d+\]|\*\*[^*\n]+\*\*)/g)
  const order = [...new Set([...text.matchAll(/\[#(\d+)\]/g)].map((m) => Number(m[1])))]
  return (
    <>
      {parts.map((part, i) => {
        const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
        // Internal links only ("/documents/3"): the text comes from the model, which a booby-trapped
        // document can influence (javascript:, external site…).
        if (link && /^\/(?![/\\])/.test(link[2]))
          return (
            <a key={i} href={link[2]} className="font-medium text-primary underline underline-offset-2">
              {link[1]}
            </a>
          )
        const bold = part.match(/^\*\*([^*\n]+)\*\*$/)
        if (bold)
          return (
            <strong key={i} className="font-semibold">
              {bold[1]}
            </strong>
          )
        const cite = part.match(/^\s?\[#(\d+)\]$/)
        if (cite) {
          const id = Number(cite[1])
          const doc = docs.find((d) => d.id === id)
          return (
            <Link
              key={i}
              to={`/documents/${id}`}
              onClick={onNavigate}
              title={doc ? t("sourceOf", { title: doc.title }) : t("source")}
              className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-primary/10 px-1 align-super text-[10px] font-semibold text-primary select-none hover:bg-primary/20"
            >
              {order.indexOf(id) + 1}
            </Link>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

/** "Your documents have been updated", with a way back right after. */
function Changed({ token }: { token: string | null }) {
  const t = useT(messages)
  const invalidate = useInvalidateAll()
  const [undone, setUndone] = useState(false)
  const undo = useMutation({
    mutationFn: () => api.undo(token!),
    onSuccess: () => {
      setUndone(true)
      invalidate()
    },
  })
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <CheckIcon className="size-3.5 text-primary" /> {undone ? t("undone") : t("changed")}
      {token && !undone && (
        <Button variant="link" size="xs" className="h-auto px-1" onClick={() => undo.mutate()} disabled={undo.isPending}>
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

function AgentAnswer({ response, onNavigate }: { response: ChatResponse; onNavigate: () => void }) {
  const t = useT(messages)
  const [expanded, setExpanded] = useState(response.documents.length <= 3)
  const docs = response.documents
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
      {(response.confirmations ?? []).length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t("confirm.why")}</p>
          {(response.confirmations ?? []).map((action) => (
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
      {docs.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          {!expanded ? (
            <button onClick={() => setExpanded(true)} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-accent">
              <span className="flex size-7 items-center justify-center rounded-md bg-accent text-primary">
                <FileTextIcon className="size-3.5" />
              </span>
              <span className="flex-1 text-left font-medium">{t("documents", { count: docs.length })}</span>
              <CaretRightIcon className="size-4 text-muted-foreground" />
            </button>
          ) : (
            <ul className="divide-y">
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
      )}
      {response.deadlines.length > 0 && (
        <ul className="divide-y overflow-hidden rounded-lg border">
          {response.deadlines.map((d) => (
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
      )}
      {response.engine === "rules" && (
        <p className="text-[11px] text-muted-foreground">{t("rulesEngine")}</p>
      )}
    </div>
  )
}
