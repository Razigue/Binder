import type { KeyboardEvent } from "react"
import type { ChatResponse, ChatStats, Doc, ToolCall } from "@/lib/api"

export interface Turn {
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
  /** The model is being loaded into memory, until it starts working. */
  loading?: boolean
  error?: string
  stopped?: boolean
}

/** A conversation left for a new one, offered to resume while the new one is empty. */
export interface Previous {
  /** Resolves once its last answer is saved. */
  id: Promise<number | null>
  title: string
}

/** Text of an answer as copied: without citation markers, links reduced to their label. */
export function plainText(text: string) {
  return text
    .replace(/\s?\[#\d+\]/g, "")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .trim()
}

/** Turn as saved with its conversation: what was shown, without the live progress nor the undo
 * and confirmation tokens, which expire. */
export function stored({ id, question, attachments, response, error, stopped }: Turn): Turn {
  return {
    id,
    question,
    attachments,
    steps: [],
    draft: "",
    error,
    stopped,
    response: response && { ...response, undo: null, confirmations: [] },
  }
}

/** The conversation already deals with this document: linked to it, attached or shown. */
export function concerns(turns: Turn[], linked: number | null, docId: number) {
  return (
    linked === docId ||
    turns.some(
      (turn) =>
        turn.attachments.some((d) => d.id === docId) ||
        turn.response?.documents.some((d) => d.id === docId),
    )
  )
}

/** Enter sends, Shift+Enter goes to the line; nothing is sent while an IME is composing. */
export function isSubmit(e: KeyboardEvent) {
  return e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing
}

/** Arguments of a tool call as the model wrote them, kept short. */
export function toolArguments(args: Record<string, unknown>) {
  return Object.entries(args)
    .map(([key, value]) => {
      const text = JSON.stringify(value) ?? "null"
      return `${key}=${text.length > 80 ? `${text.slice(0, 79)}…` : text}`
    })
    .join(", ")
}
