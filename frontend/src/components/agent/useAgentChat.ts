import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { keys, useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { api, type ChatMessage, type Doc } from "@/lib/api"
import type { Viewing } from "./context"
import { concerns, plainText, stored, type Previous, type Turn } from "./turns"

/** The conversation with the agent: its turns, the answer being written, the saved
 * conversations it moves between, and the document on screen it is about. */
export function useAgentChat() {
  const t = useT(messages)
  const [showHistory, setShowHistory] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState(false)
  const [viewing, setViewing] = useState<Viewing | null>(null)
  // Document on screen the user unlinked from their questions, until another one is shown.
  const [ignored, setIgnored] = useState<number | null>(null)
  const about = viewing && viewing.id !== ignored ? viewing : null
  // Saved conversation shown (null until its first answer is saved) and the document it is about.
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [linked, setLinked] = useState<number | null>(null)
  // Conversation left for a new one, offered to resume while the new one is empty.
  const [previous, setPrevious] = useState<Previous | null>(null)
  // Saves run one after the other: the first one creates the conversation the next ones update.
  const saving = useRef<Promise<number | null>>(Promise.resolve(null))
  const saved = useRef<Turn[] | null>(null)
  const generation = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const nextId = useRef(0)
  const invalidate = useInvalidateAll()
  const qc = useQueryClient()

  const update = (id: number, patch: Partial<Turn>) =>
    setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)))

  // Saved after each answer (not while it is written).
  useEffect(() => {
    if (pending || !turns.length || saved.current === turns) return
    saved.current = turns
    const gen = generation.current
    const body = turns.map(stored)
    saving.current = saving.current.then((id) =>
      (id === null
        ? api.createConversation({ document_id: linked, turns: body })
        : api.updateConversation(id, { turns: body })
      )
        .then((c) => {
          if (generation.current === gen) setConversationId(c.id)
          void qc.invalidateQueries({ queryKey: keys.conversations })
          return c.id
        })
        .catch(() => id),
    )
  }, [turns, pending, linked, qc])

  const stop = () => {
    controller.current?.abort()
    controller.current = null
    setPending(false)
  }

  /** Leaves the conversation shown (it stays in the history) for an empty one. */
  const begin = (
    next: { id: number; turns: Turn[]; linked: number | null } | null = null,
    leaving: Previous | null = turns[0] ? { id: saving.current, title: plainText(turns[0].question) } : null,
  ) => {
    stop()
    generation.current += 1
    saving.current = saving.current.then(() => next?.id ?? null)
    saved.current = next?.turns ?? null
    setTurns(next?.turns ?? [])
    setConversationId(next?.id ?? null)
    setLinked(next?.linked ?? null)
    setPrevious(next ? null : leaving)
    setShowHistory(false)
  }

  const resume = async (id: number) => {
    if (id === conversationId) return setShowHistory(false)
    try {
      const c = await api.conversation<Turn>(id)
      const restored = c.messages.map((turn) => ({ ...turn, id: ++nextId.current }))
      begin({ id: c.id, turns: restored, linked: c.document_id })
    } catch {
      toast.error(t("loadFailed"))
    }
  }

  /** A document comes on screen. One the conversation is not about starts a new conversation, so
   * questions about it do not carry the previous one (still in the history). */
  const view = (doc: Viewing) => {
    setViewing(doc)
    const changed = doc.id !== viewing?.id && doc.id !== ignored
    if (changed && !pending && turns.length && !concerns(turns, linked, doc.id)) begin()
  }

  const leave = (id: number) => setViewing((current) => (current?.id === id ? null : current))

  /** Sends a question; `at` replaces that turn and the following ones (edit, regenerate);
   * `fresh` starts a new conversation with it. */
  const ask = (question: string, attachments: Doc[] = [], at = turns.length, fresh = false) => {
    const q = question.trim()
    if ((!q && !attachments.length) || pending) return
    if (fresh && turns.length) begin()
    const kept = fresh ? [] : turns.slice(0, at)
    if (!kept.length) {
      setLinked(about?.id ?? null)
      setPrevious(null)
    }
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
          if (event.type === "loading") progress(() => ({ loading: true }))
          else if (event.type === "tool")
            progress((turn) => ({
              loading: false,
              steps: [...turn.steps, { name: event.name, arguments: event.arguments }],
            }))
          else if (event.type === "tool_done")
            progress((turn) => ({
              steps: turn.steps.map((step, i) =>
                i === turn.steps.length - 1 ? { ...step, duration_ms: event.duration_ms, error: event.error } : step,
              ),
            }))
          else if (event.type === "stats") progress(() => ({ loading: false, stats: event.stats }))
          else if (event.type === "token") progress((turn) => ({ loading: false, draft: turn.draft + event.text }))
          else if (event.type === "step") progress(() => ({ draft: "" }))
        },
        abort.signal,
        about?.id,
      )
      .then((response) => {
        update(id, { response })
        if (attachments.length || response.changed) void invalidate()
      })
      .catch((err: Error) => update(id, abort.signal.aborted ? { stopped: true } : { error: err.message }))
      .finally(() => {
        if (controller.current !== abort) return
        controller.current = null
        setPending(false)
      })
  }

  return {
    turns,
    pending,
    conversationId,
    previous,
    /** The document on screen questions are about, unless the user unlinked it. */
    about,
    showHistory,
    setShowHistory,
    ask,
    stop,
    begin,
    resume,
    view,
    leave,
    ignoreViewing: () => setIgnored(about?.id ?? null),
  }
}

export type AgentChat = ReturnType<typeof useAgentChat>
