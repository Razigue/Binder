import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowSquareOutIcon, CheckCircleIcon, CircleNotchIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { DocumentPage } from "@/components/DocumentPage"
import { useDocument, useInvalidateAll, useQuestions } from "@/hooks/queries"
import { useT } from "@/i18n"
import { questions as messages } from "@/i18n/messages/questions"
import { api, type FeedAction, type FeedItem } from "@/lib/api"

/** What the panel goes through: every question (a sorting session), or one question per
 * document of a card ("See one by one", "Open"). */
export interface QuestionsRequest {
  documentIds?: number[]
}

/** One question per screen, the document next to it with the place Binder read highlighted,
 * the answers in the same panel. On a phone, the document on top and the answers below. */
export function QuestionsDialog({ request, onClose }: { request: QuestionsRequest | null; onClose: () => void }) {
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex h-[92vh] max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        {request && <QuestionsSession key={JSON.stringify(request)} initial={request} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function QuestionsSession({ initial, onClose }: { initial: QuestionsRequest; onClose: () => void }) {
  const t = useT(messages)
  const [request, setRequest] = useState(initial)
  const ids = request.documentIds
  const list = useQuestions(ids)
  // Answered or put off during this session: the next one comes up without waiting.
  const [settled, setSettled] = useState<ReadonlySet<string>>(() => new Set())
  // How many there were when the session began, for "3 of 7".
  const [total, setTotal] = useState<number | null>(null)
  if (list.data && total === null) setTotal(list.data.length)
  const remaining = (list.data ?? []).filter((q) => !settled.has(q.key))
  const current = remaining[0]
  const done = total !== null ? total - remaining.length : 0

  const next = (key: string) => setSettled((s) => new Set([...s, key]))

  if (!list.data)
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
        <DialogTitle className="sr-only">{t("title")}</DialogTitle>
        <DialogDescription className="sr-only">{t("loading")}</DialogDescription>
        <CircleNotchIcon className="size-4 animate-spin" /> {t("loading")}
      </div>
    )
  if (!current)
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <CheckCircleIcon className="animate-pop size-10 text-emerald-600 dark:text-emerald-400" weight="fill" />
        <DialogTitle className="text-lg">{t("doneTitle")}</DialogTitle>
        <DialogDescription className="max-w-sm">{t("doneHint")}</DialogDescription>
        <Button onClick={onClose} className="mt-2">
          {t("close")}
        </Button>
      </div>
    )
  return (
    <QuestionScreen
      key={current.key}
      item={current}
      position={{ current: done + 1, total: Math.max(total ?? 0, done + 1) }}
      onSettled={() => next(current.key)}
      onDetail={(documentIds) => {
        setTotal(null)
        setSettled(new Set())
        setRequest({ documentIds })
      }}
      onNavigate={onClose}
    />
  )
}

function QuestionScreen({
  item,
  position,
  onSettled,
  onDetail,
  onNavigate,
}: {
  item: FeedItem
  position: { current: number; total: number }
  onSettled: () => void
  onDetail: (documentIds: number[]) => void
  onNavigate: () => void
}) {
  const t = useT(messages)
  // Each question replaces the last one and the answer pressed with it: focus goes to the new question.
  const title = useRef<HTMLHeadingElement>(null)
  useEffect(() => title.current?.focus(), [])
  const invalidate = useInvalidateAll()
  const [shown, setShown] = useState(0)
  const docId = item.document_ids[shown] ?? item.document_ids[0]
  const doc = useDocument(docId ?? null)
  const field = typeof item.extra.field === "string" ? item.extra.field : null
  const answer = useMutation({
    mutationFn: (action: FeedAction) => api.act(action),
    onSuccess: () => {
      onSettled()
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })
  const run = (action: FeedAction) => {
    // "See one by one" on a grouped question: one screen per document.
    if (action.type === "ask") {
      if (item.document_ids.length > 1) onDetail(item.document_ids)
      return
    }
    answer.mutate(action)
  }
  const answers = item.actions.filter((a) => a.type !== "ask" || item.document_ids.length > 1)

  return (
    <div className="flex min-h-0 flex-1 flex-col md:grid md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <div className="flex min-h-0 flex-1 flex-col border-b md:border-r md:border-b-0">
        {doc.data ? (
          <DocumentPage doc={doc.data} active={field} className="min-h-0 flex-1" />
        ) : (
          <Skeleton className="m-4 flex-1" />
        )}
        {item.document_ids.length > 1 && (
          <div className="flex gap-1.5 overflow-x-auto border-t px-3 py-2">
            {item.document_ids.map((id, i) => (
              <button
                type="button"
                key={id}
                onClick={() => setShown(i)}
                aria-pressed={i === shown}
                aria-label={t("documentN", { n: i + 1, total: item.document_ids.length })}
                className={
                  i === shown
                    ? "rounded-full bg-primary px-2.5 py-0.5 text-xs font-medium text-primary-foreground"
                    : "rounded-full border px-2.5 py-0.5 text-xs font-medium hover:bg-accent"
                }
              >
                {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>
      {/* The next question fades in: the pile goes down, one answer at a time. */}
      <div className="animate-step flex shrink-0 flex-col gap-4 overflow-y-auto p-5 md:p-6">
        <p className="text-xs font-medium text-muted-foreground">
          {t("progress", { current: position.current, total: position.total })}
        </p>
        <div>
          <DialogTitle ref={title} tabIndex={-1} className="text-lg leading-snug outline-none">
            {item.title}
          </DialogTitle>
          <DialogDescription className="mt-1.5">{item.detail}</DialogDescription>
          {field && item.extra.question === "confirm" && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">{t("readHere")}</p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          {answers.map((action, i) => (
            <Button
              key={i}
              size="lg"
              variant={action.primary ? "default" : "outline"}
              disabled={answer.isPending}
              onClick={() => run(action)}
              className="h-11 justify-start"
            >
              {answer.isPending && answer.variables === action && <CircleNotchIcon className="animate-spin" />}
              {action.label}
            </Button>
          ))}
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
          <Button variant="ghost" onClick={onSettled} disabled={answer.isPending}>
            {t("skip")}
          </Button>
          {docId !== undefined && (
            <Button
              variant="link"
              className="ml-auto"
              render={<Link to={`/documents/${docId}`} onClick={onNavigate} />}
              nativeButton={false}
            >
              <ArrowSquareOutIcon /> {t("openDocument")}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
