import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowsOutIcon, CheckCircleIcon, CopyIcon, DownloadSimpleIcon, EnvelopeIcon, GlobeIcon, MailboxIcon, PaperPlaneTiltIcon, PencilSimpleIcon, PrinterIcon, ScalesIcon, WarningCircleIcon, XCircleIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Glossed } from "@/components/glossary"
import { Viewer } from "@/components/viewer"
import { useDeleteLetter, useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { viewer } from "@/i18n/messages/viewer"
import { api, letterPdfUrl, type LegalCheck, type LegalPoint, type LegalSource, type Letter } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { A4, BLANK, letterBlocks, printLetter } from "@/lib/letters"
import { cn } from "@/lib/utils"
import { usePanels } from "./context"

/** A letter: in the letter panel as an A4 sheet with zoom, and the "Cancel the letter" button
 * (`onCancelled` closes the panel); `compact` in the agent, with "Enlarge" to open the panel. */
export function LetterView({
  letter: initial,
  compact = false,
  onCancelled,
}: {
  letter: Letter
  compact?: boolean
  onCancelled?: () => void
}) {
  const t = useT(feed)
  const tv = useT(viewer)
  const panels = usePanels()
  const [letter, setLetter] = useState(initial)
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(initial.body)
  const [cancelling, setCancelling] = useState(false)
  const [discarding, setDiscarding] = useState(false)
  const remove = useDeleteLetter()
  // "Send by post" open: the steps, then "I sent it".
  const [posting, setPosting] = useState(false)
  const invalidate = useInvalidateAll()
  const blanks = (body.match(BLANK) ?? []).length
  // Only a saved letter can be edited, sent or cancelled.
  const id = letter.id

  const save = useMutation({
    mutationFn: (saved: number) => api.editLetter(saved, body),
    onSuccess: (l) => {
      setLetter(l)
      setEditing(false)
    },
    onError: (e) => toast.error(e.message),
  })
  // The user accepts the wording the official source gives: the letter is saved with it.
  const applyCorrection = useMutation({
    mutationFn: ({ saved, point }: { saved: number; point: LegalPoint }) =>
      api.editLetter(saved, body.replace(point.claim, point.correction)),
    onSuccess: (l) => {
      setLetter(l)
      setBody(l.body)
    },
    onError: (e) => toast.error(e.message),
  })
  const sent = useMutation({
    mutationFn: api.letterSent,
    onSuccess: (l) => {
      setLetter(l)
      void invalidate()
    },
    onError: (e) => toast.error(e.message),
  })

  // Leaving the editor: unsaved changes are only dropped once the user confirms.
  const stopEditing = () => (body !== letter.body ? setDiscarding(true) : setEditing(false))

  return (
    <div className={cn("overflow-hidden rounded-lg border", !compact && "flex min-h-0 flex-1 flex-col")}>
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <EnvelopeIcon className="size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{letter.subject}</span>
        {compact && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => panels.showLetter({ ...letter, body })}
            aria-label={tv("enlarge")}
            title={tv("enlarge")}
          >
            <ArrowsOutIcon />
          </Button>
        )}
        {id !== null && !editing && (
          <Button variant="ghost" size="icon-sm" onClick={() => setEditing(true)} aria-label={t("letterEdit")} title={t("letterEdit")}>
            <PencilSimpleIcon />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => void navigator.clipboard.writeText(body).then(() => toast.success(t("letterCopy")))}
          aria-label={t("letterCopy")}
          title={t("letterCopy")}
        >
          <CopyIcon />
        </Button>
      </div>
      {editing && id !== null ? (
        <div className={cn("flex flex-col gap-2 p-3", !compact && "min-h-0 flex-1")}>
          <Textarea
            value={body}
            aria-label={t("letterEdit")}
            onChange={(e) => setBody(e.target.value)}
            className={cn("leading-relaxed", compact ? "min-h-80 text-xs" : "min-h-0 flex-1 resize-none text-sm")}
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={() => save.mutate(id)} disabled={save.isPending}>
              {t("letterSave")}
            </Button>
            <Button size="sm" variant="ghost" onClick={stopEditing} disabled={save.isPending}>
              {t("letterEditCancel")}
            </Button>
          </div>
        </div>
      ) : compact ? (
        <pre className="max-h-72 overflow-y-auto px-3 py-2.5 font-sans text-xs leading-relaxed whitespace-pre-wrap select-text">
          {body}
        </pre>
      ) : (
        <Viewer aspect={A4} pan={false} className="min-h-[40%] flex-1">
          <LetterSheet body={body} />
        </Viewer>
      )}
      <div className={cn("space-y-2 border-t px-3 py-2.5", !compact && "max-h-[45%] shrink-0 overflow-y-auto")}>
        <p className={cn("flex items-center gap-1.5 text-xs", blanks ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>
          {blanks ? <WarningCircleIcon className="size-3.5" /> : <CheckCircleIcon className="size-3.5 text-primary" />}
          {blanks ? t("letterBlanks", { count: blanks }) : t("letterComplete")}
        </p>
        {letter.sources.length > 0 && (
          <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <GlobeIcon className="size-3.5 text-primary" />
            {t("letterAdapted")} <SourceLinks sources={letter.sources} />
          </p>
        )}
        <LegalCheckNote
          check={letter.verification}
          body={body}
          onApply={id !== null && !editing ? (point) => applyCorrection.mutate({ saved: id, point }) : undefined}
        />
        {letter.registered && (
          <p className="text-xs text-muted-foreground">
            <Glossed text={t("letterRegistered")} />
          </p>
        )}
        {letter.sent_on && letter.follow_up_on && (
          <p className="text-xs text-muted-foreground">
            {t("letterSentOn", { date: formatDate(letter.sent_on), followUp: formatDate(letter.follow_up_on) })}
          </p>
        )}
        {id !== null && (
          <>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" onClick={() => printLetter(body, letter.subject)}>
                <PrinterIcon /> {t("letterPrint")}
              </Button>
              {!letter.sent_on && (
                <Button size="sm" variant="outline" onClick={() => setPosting((p) => !p)} aria-expanded={posting}>
                  <MailboxIcon /> {t("letterPost")}
                </Button>
              )}
              <Button size="sm" variant="ghost" render={<a href={letterPdfUrl(id)} download />} nativeButton={false}>
                <DownloadSimpleIcon /> {t("letterPdf")}
              </Button>
              {onCancelled && (
                <Button size="sm" variant="destructive" className="sm:ml-auto" onClick={() => setCancelling(true)} disabled={remove.isPending}>
                  <XCircleIcon /> {t("letterCancel")}
                </Button>
              )}
            </div>
            {posting && !letter.sent_on && (
              <div className="rounded-md bg-muted/60 px-3 py-2.5 text-sm">
                <ol className="list-decimal space-y-1 pl-5">
                  <li>{t("post.print")}</li>
                  <li>{t("post.envelope", { recipient: letter.recipient })}</li>
                  <li>
                    <Glossed text={letter.registered ? t("post.registered") : t("post.stamp")} />
                  </li>
                  <li>{t("post.tell")}</li>
                </ol>
                <Button size="sm" className="mt-2.5" onClick={() => sent.mutate(id)} disabled={sent.isPending}>
                  <PaperPlaneTiltIcon /> {t("letterSent")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
      {id !== null && onCancelled && (
        <ConfirmDialog
          open={cancelling}
          onOpenChange={setCancelling}
          title={t("letterCancelTitle")}
          description={t("letterCancelHint", { subject: letter.subject })}
          confirmLabel={t("letterCancelConfirm")}
          cancelLabel={t("letterKeep")}
          onConfirm={async () => {
            // The backend answers with an "Undo" toast.
            await remove.mutateAsync(id)
            onCancelled()
          }}
        />
      )}
      <ConfirmDialog
        open={discarding}
        onOpenChange={setDiscarding}
        title={t("letterDiscardTitle")}
        description={t("letterDiscardHint")}
        confirmLabel={t("letterDiscardConfirm")}
        cancelLabel={t("letterKeepEditing")}
        onConfirm={() => {
          setBody(letter.body)
          setEditing(false)
        }}
      />
    </div>
  )
}

function SourceLinks({ sources }: { sources: LegalSource[] }) {
  return sources.map((s, i) => (
    <span key={s.url}>
      {i > 0 && ", "}
      <a href={s.url} target="_blank" rel="noreferrer" title={s.title} className="underline underline-offset-2 hover:text-foreground">
        {new URL(s.url).hostname.replace(/^www\./, "")}
      </a>
    </span>
  ))
}

/** Whether the law quoted by a letter was checked online. A point the official source
 * contradicts is shown with the source's own sentence; the user applies the proposed wording. */
function LegalCheckNote({
  check,
  body,
  onApply,
}: {
  check: LegalCheck | null
  body: string
  onApply?: (point: LegalPoint) => void
}) {
  const t = useT(feed)
  if (!check || check.status === "none") return null
  const date = formatDate(check.checked_on)
  // Applied, or rewritten by the user: the point is no longer in the letter.
  const open = check.points.filter((p) => p.status !== "confirmed" && body.includes(p.claim))
  const confirmed = check.points.filter((p) => p.status === "confirmed" || !body.includes(p.claim))
  const sources = [...new Map(confirmed.flatMap((p) => p.sources.slice(0, 1)).map((s) => [s.url, s])).values()]
  return (
    <div className="space-y-2 text-xs">
      {confirmed.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-1.5 text-muted-foreground">
          <ScalesIcon className="size-3.5 text-primary" />
          {open.length ? t("letterLawSomeVerified", { count: confirmed.length, date }) : t("letterLawVerified", { date })}
          {sources.length > 0 && (
            <span>
              ({t("letterLawSources")} <SourceLinks sources={sources} />)
            </span>
          )}
        </p>
      )}
      {open.map((point) => (
        <div key={point.claim} className="space-y-1 rounded-md border border-amber-300/60 bg-amber-50 px-2.5 py-2 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <p className="flex items-start gap-1.5 font-medium">
            <WarningCircleIcon className="mt-px size-3.5 shrink-0" />
            {point.status === "outdated" ? t("letterLawContradicted") : t("letterLawUnchecked")}
          </p>
          <p className="pl-5 italic">{t("letterLawQuote", { text: point.claim })}</p>
          {point.status === "outdated" && point.evidence && (
            <p className="pl-5">
              {t("letterLawSourceSays")} <SourceLinks sources={point.sources.slice(0, 1)} />
              {" — "}
              {t("letterLawQuote", { text: point.evidence })}
            </p>
          )}
          {point.status !== "outdated" && point.sources.length > 0 && (
            <p className="pl-5">
              {t("letterLawSources")} <SourceLinks sources={point.sources} />
            </p>
          )}
          {point.status === "outdated" && point.correction && onApply && (
            <div className="space-y-1 pl-5">
              <p>
                {t("letterLawProposed")} {t("letterLawQuote", { text: point.correction })}
              </p>
              <Button size="xs" variant="outline" onClick={() => onApply(point)}>
                {t("letterLawApply")}
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/** The letter as a sheet of A4 paper. Sizes are in container units, so the text scales with
 * the sheet when zooming; the details left in [brackets] stand out. */
function LetterSheet({ body }: { body: string }) {
  return (
    <div className="@container">
      {/* White on purpose: it is a sheet of paper, in both themes. */}
      <div className="aspect-[210/297] rounded bg-white p-[9.5cqw] text-[length:1.75cqw] leading-[1.45] text-gray-900 shadow-sm select-text dark:brightness-[0.88]">
        {letterBlocks(body).map((block, i) => (
          <p
            key={i}
            className={cn("mb-[0.85em]", block.style === "right" && "ml-[52%]", block.style === "subject" && "font-semibold")}
          >
            {block.lines.map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {line.split(/(\[[^\]\n]{2,80}\])/).map((part, k) =>
                  k % 2 ? (
                    <mark key={k} className="rounded-sm bg-amber-200 px-[0.15em] text-inherit">
                      {part}
                    </mark>
                  ) : (
                    part
                  ),
                )}
              </span>
            ))}
          </p>
        ))}
      </div>
    </div>
  )
}
