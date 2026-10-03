import { useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { PencilSimpleIcon, TrashIcon } from "@phosphor-icons/react"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { keys, useConversations } from "@/hooks/queries"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { api, type ConversationSummary } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { ActionButton } from "./actions"

/** Saved conversations, newest first: open one, rename it, delete it (undoable a moment). */
export function ConversationHistory({
  current,
  onOpen,
  onDeleted,
}: {
  current: number | null
  onOpen: (id: number) => void
  onDeleted: (id: number) => void
}) {
  const t = useT(messages)
  const qc = useQueryClient()
  const { data, isPending, isError } = useConversations()
  const [renaming, setRenaming] = useState<number | null>(null)
  // Escape leaves the name as it was (the field still loses focus).
  const cancelled = useRef(false)
  const refresh = () => qc.invalidateQueries({ queryKey: keys.conversations })

  const rename = (c: ConversationSummary, title: string) => {
    setRenaming(null)
    if (cancelled.current || title.trim() === c.title) return
    api.updateConversation(c.id, { title }).then(refresh, (err: Error) => toast.error(err.message))
  }

  const remove = async (c: ConversationSummary) => {
    try {
      const full = await api.conversation(c.id)
      await api.deleteConversation(c.id)
      onDeleted(c.id)
      void refresh()
      toast.success(t("conversationDeleted"), {
        duration: 15000,
        action: {
          label: t("undoDelete"),
          onClick: () =>
            api
              .createConversation({ document_id: full.document_id, title: full.title, turns: full.messages })
              .then(refresh, (err: Error) => toast.error(err.message)),
        },
      })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3">
      {isPending ? (
        <div className="space-y-2 px-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError ? (
        <p role="alert" className="px-2 py-4 text-sm text-destructive">
          {t("historyFailed")}
        </p>
      ) : !data?.length ? (
        <p className="px-2 py-4 text-sm text-muted-foreground">{t("historyEmpty")}</p>
      ) : (
        <ul className="space-y-0.5">
          {data.map((c) => (
            <li key={c.id} className="group/row relative flex items-center gap-1 rounded-lg hover:bg-accent">
              {renaming === c.id ? (
                <Input
                  autoFocus
                  defaultValue={c.title}
                  aria-label={t("conversationName")}
                  className="m-1.5"
                  onFocus={() => (cancelled.current = false)}
                  onBlur={(e) => rename(c, e.currentTarget.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      e.stopPropagation()
                      cancelled.current = true
                    }
                    if (e.key === "Enter" || e.key === "Escape") e.currentTarget.blur()
                  }}
                />
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => onOpen(c.id)}
                    aria-current={c.id === current || undefined}
                    className="min-w-0 flex-1 px-3 py-2 text-left select-none"
                  >
                    <span className="block truncate text-sm font-medium">{c.title || t("untitled")}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {[
                        c.id === current ? t("current") : formatDateTime(c.updated_at),
                        c.document_title,
                        t("exchanges", { count: c.turns }),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </button>
                  <div className="flex shrink-0 gap-0.5 pr-1.5 opacity-0 transition-opacity group-hover/row:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100">
                    <ActionButton label={t("rename")} onClick={() => setRenaming(c.id)}>
                      <PencilSimpleIcon />
                    </ActionButton>
                    <ActionButton label={t("deleteConversation")} onClick={() => void remove(c)}>
                      <TrashIcon />
                    </ActionButton>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
