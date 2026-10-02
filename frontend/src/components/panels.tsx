import { createContext, useCallback, useContext, useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { PrinterIcon, EnvelopeSimpleIcon } from "@phosphor-icons/react"
import { WarningCircleIcon, CheckCircleIcon, CopyIcon, DownloadSimpleIcon, FileTextIcon, FolderOpenIcon, InfoIcon, CircleNotchIcon, EnvelopeIcon, PencilSimpleIcon, ScalesIcon, PaperPlaneTiltIcon, GlobeIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { CategoryIcon } from "@/components/CategoryIcon"
import { GlossaryText } from "@/components/glossary"
import { JourneyDialog } from "@/components/journey"
import { QuestionsDialog, type QuestionsRequest } from "@/components/questions"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { api, folderExportUrl, letterPdfUrl, type Folder, type ImportReport, type LegalCheck, type LegalPoint, type LegalSource, type Letter } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

interface Panels {
  showLetter: (letter: Letter) => void
  showReport: (batch: string) => void
  showJourney: (id: number) => void
  /** The question panel: every question, or those about these documents. */
  showQuestions: (documentIds?: number[]) => void
}

const PanelsContext = createContext<Panels | null>(null)

export function usePanels() {
  const ctx = useContext(PanelsContext)
  if (!ctx) throw new Error("usePanels must be used inside PanelsProvider")
  return ctx
}

/** Letter, import report and journey, opened from anywhere (feed, agent, upload, Prepare). */
export function PanelsProvider({ children }: { children: ReactNode }) {
  const t = useT(feed)
  const [letter, setLetter] = useState<Letter | null>(null)
  const [batch, setBatch] = useState<string | null>(null)
  const [journeyId, setJourneyId] = useState<number | null>(null)
  const showLetter = useCallback((l: Letter) => setLetter(l), [])
  const showReport = useCallback((b: string) => setBatch(b), [])
  const showJourney = useCallback((id: number) => setJourneyId(id), [])
  const [asking, setAsking] = useState<QuestionsRequest | null>(null)
  const showQuestions = useCallback((documentIds?: number[]) => setAsking({ documentIds }), [])
  const invalidate = useInvalidateAll()

  return (
    <PanelsContext.Provider value={{ showLetter, showReport, showJourney, showQuestions }}>
      {children}
      <QuestionsDialog request={asking} onClose={() => setAsking(null)} />
      <JourneyDialog id={journeyId} onClose={() => setJourneyId(null)} />
      <Dialog open={letter !== null} onOpenChange={(open) => !open && setLetter(null)}>
        <DialogContent className="max-h-[90vh] gap-4 overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg">{letter && t("letterTitle", { recipient: letter.recipient })}</DialogTitle>
            <DialogDescription className="sr-only">{letter?.subject}</DialogDescription>
          </DialogHeader>
          {letter && <LetterView key={letter.id ?? letter.subject} letter={letter} />}
        </DialogContent>
      </Dialog>
      <Dialog
        open={batch !== null}
        onOpenChange={(open) => {
          if (open || batch === null) return
          api.reportSeen(batch).finally(invalidate)
          setBatch(null)
        }}
      >
        <DialogContent className="max-h-[90vh] gap-4 overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg">{t("reportTitle")}</DialogTitle>
            <DialogDescription className="sr-only">{t("reportTitle")}</DialogDescription>
          </DialogHeader>
          {batch && <ReportView batch={batch} onNavigate={() => setBatch(null)} />}
        </DialogContent>
      </Dialog>
    </PanelsContext.Provider>
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

/** Prints the letter's text alone (the PDF cannot be printed from inside the app). */
function printLetter(body: string) {
  const sheet = document.createElement("div")
  sheet.className = "print-only"
  sheet.textContent = body
  document.body.appendChild(sheet)
  const done = () => {
    sheet.remove()
    window.removeEventListener("afterprint", done)
  }
  window.addEventListener("afterprint", done)
  window.print()
}

export function LetterView({ letter: initial, compact = false }: { letter: Letter; compact?: boolean }) {
  const t = useT(feed)
  const [letter, setLetter] = useState(initial)
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(initial.body)
  const invalidate = useInvalidateAll()
  const blanks = (body.match(/\[[^\]\n]{2,80}\]/g) ?? []).length

  const save = useMutation({
    mutationFn: () => api.editLetter(letter.id!, body),
    onSuccess: (l) => {
      setLetter(l)
      setEditing(false)
    },
    onError: (e) => toast.error(e.message),
  })
  // The user accepts the wording the official source gives: the letter is saved with it.
  const applyCorrection = useMutation({
    mutationFn: (point: LegalPoint) => api.editLetter(letter.id!, body.replace(point.claim, point.correction)),
    onSuccess: (l) => {
      setLetter(l)
      setBody(l.body)
    },
    onError: (e) => toast.error(e.message),
  })
  const [posting, setPosting] = useState(false)
  const sent = useMutation({
    mutationFn: () => api.letterSent(letter.id!),
    onSuccess: (l) => {
      setLetter(l)
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })

  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <EnvelopeIcon className="size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{letter.subject}</span>
        {letter.id !== null && !editing && (
          <Button variant="ghost" size="icon-sm" onClick={() => setEditing(true)} aria-label={t("letterEdit")} title={t("letterEdit")}>
            <PencilSimpleIcon />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => navigator.clipboard.writeText(body).then(() => toast.success(t("letterCopy")))}
          aria-label={t("letterCopy")}
          title={t("letterCopy")}
        >
          <CopyIcon />
        </Button>
      </div>
      {editing ? (
        <div className="space-y-2 p-3">
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} className="min-h-80 text-xs leading-relaxed" />
          <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
            {t("letterSave")}
          </Button>
        </div>
      ) : (
        <pre
          className={cn(
            "overflow-y-auto px-3 py-2.5 font-sans text-xs leading-relaxed whitespace-pre-wrap select-text",
            compact ? "max-h-72" : "max-h-[50vh]",
          )}
        >
          {body}
        </pre>
      )}
      <div className="space-y-2 border-t px-3 py-2.5">
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
          onApply={letter.id !== null && !editing ? (point) => applyCorrection.mutate(point) : undefined}
        />
        {letter.registered && <p className="text-xs text-muted-foreground">{t("letterRegistered")}</p>}
        {letter.sent_on && letter.follow_up_on && (
          <p className="text-xs text-muted-foreground">
            {t("letterSentOn", { date: formatDate(letter.sent_on), followUp: formatDate(letter.follow_up_on) })}
          </p>
        )}
        {letter.id !== null && (
          <div className="flex flex-wrap gap-2 pt-1">
            {/* Printing and posting first: most letters still go on paper. */}
            <Button onClick={() => printLetter(body)}>
              <PrinterIcon /> {t("letterPrint")}
            </Button>
            {!letter.sent_on && (
              <Button variant="outline" onClick={() => setPosting(!posting)} aria-expanded={posting}>
                <EnvelopeSimpleIcon /> {t("letterPost")}
              </Button>
            )}
            <Button variant="ghost" render={<a href={letterPdfUrl(letter.id)} download />} nativeButton={false}>
              <DownloadSimpleIcon /> {t("letterPdf")}
            </Button>
          </div>
        )}
        {posting && !letter.sent_on && (
          <div className="rounded-lg bg-muted/50 p-3 text-sm">
            <ol className="list-decimal space-y-1 pl-5">
              <li>{t("postPrint")}</li>
              <li>{t("postSign")}</li>
              <li>
                {letter.recipient_address ? t("postEnvelopeTo") : t("postEnvelope")}
                {letter.recipient_address && (
                  <span className="mt-1 block whitespace-pre-line text-muted-foreground">
                    {`${letter.recipient}\n${letter.recipient_address}`}
                  </span>
                )}
              </li>
              <li>{letter.registered ? t("postRegistered") : t("postStamp")}</li>
            </ol>
            <Button size="sm" className="mt-3" onClick={() => sent.mutate()} disabled={sent.isPending}>
              <PaperPlaneTiltIcon /> {t("letterSent")}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

export function FolderView({ folder }: { folder: Folder }) {
  const t = useT(feed)
  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <FolderOpenIcon className="size-4 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{folder.title}</span>
        <span className="text-xs text-muted-foreground">{t("folderReady", { ready: folder.ready, total: folder.total })}</span>
      </div>
      <ul className="divide-y">
        {folder.pieces.map((p) => (
          <li key={p.key} className="flex items-start gap-2 px-3 py-2 text-sm">
            <span
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                p.status === "ok" ? "bg-emerald-500" : p.status === "missing" ? "bg-red-500" : "bg-amber-500",
              )}
            />
            <span className="min-w-0 flex-1">
              <span className="block">{p.label}</span>
              {p.status !== "ok" && <span className="block text-xs text-muted-foreground">{p.note || p.hint}</span>}
            </span>
            <span className="text-xs text-muted-foreground">{t(`piece.${p.status}`)}</span>
          </li>
        ))}
      </ul>
      <div className="border-t px-3 py-2">
        <Button size="sm" variant="outline" render={<a href={folderExportUrl(folder.key)} download />} nativeButton={false}>
          <DownloadSimpleIcon /> {t("folderDownload")}
        </Button>
      </div>
    </div>
  )
}

export function ReportView({ batch, onNavigate }: { batch: string; onNavigate?: () => void }) {
  const t = useT(feed)
  const navigate = useNavigate()
  const invalidate = useInvalidateAll()
  const report = useQuery({
    queryKey: ["report", batch],
    queryFn: () => api.report(batch),
    retry: false,
    // Until every document of the import is read (and while the first one is still uploading).
    refetchInterval: (q) => (!q.state.data || q.state.data.processing ? 1500 : false),
  })
  const answer = useMutation({
    mutationFn: (p: { document_id: number; choice: string }) => api.act({ type: "answer", params: p }),
    onSuccess: () => {
      invalidate()
      report.refetch()
    },
    onError: (e) => toast.error(e.message),
  })
  const data: ImportReport | undefined = report.data
  if (!data)
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <CircleNotchIcon className="size-4 animate-spin" /> {t("reportAnalysing", { count: 1 })}
      </p>
    )
  const open = (id: number) => {
    onNavigate?.()
    navigate(`/documents/${id}`)
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {data.processing ? (
          <span className="flex items-center gap-2">
            <CircleNotchIcon className="size-4 animate-spin" /> {t("reportAnalysing", { count: data.processing })}
          </span>
        ) : (
          data.summary
        )}
      </p>
      <ul className="divide-y rounded-lg border">
        {data.items.map(({ document: d, brief, facts, events, question }) => (
          <li key={d.id} className="space-y-2 px-4 py-3">
            <div className="flex items-start gap-3">
              {d.area ? <AreaIcon area={d.area} size="sm" /> : <CategoryIcon category={d.category} size="sm" />}
              <div className="min-w-0 flex-1">
                <button onClick={() => open(d.id)} className="block max-w-full truncate text-left text-sm font-medium hover:underline">
                  {d.status === "processing" || d.status === "waiting" ? d.filename : d.title}
                </button>
                {d.status === "processing" ? (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CircleNotchIcon className="size-3 animate-spin" /> {t("reportAnalysing", { count: 1 })}
                  </p>
                ) : (
                  <>
                  {brief && (
                    <p className="mt-0.5 text-sm">
                      <GlossaryText text={brief} />
                    </p>
                  )}
                  <ul className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                    {facts.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                    {events.map((e) => (
                      <li key={e} className="flex items-start gap-1 text-foreground">
                        <InfoIcon className="mt-0.5 size-3 shrink-0 text-primary" /> {e}
                      </li>
                    ))}
                  </ul>
                  </>
                )}
              </div>
              <FileTextIcon className="hidden size-4 text-muted-foreground sm:block" />
            </div>
            {question && (
              <div className="ml-10 rounded-lg bg-amber-50/70 p-3 dark:bg-amber-500/10">
                <p className="text-sm font-medium">{question.title}</p>
                <p className="text-xs text-muted-foreground">{question.detail}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {question.choices.map((c) => (
                    <Button
                      key={c.id}
                      size="xs"
                      variant={c.primary ? "default" : "outline"}
                      disabled={answer.isPending}
                      onClick={() =>
                        c.id === "open" ? open(d.id) : answer.mutate({ document_id: d.id, choice: c.id })
                      }
                    >
                      {c.label}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
      {!data.items.length && <p className="text-sm text-muted-foreground">{t("reportEmpty")}</p>}
    </div>
  )
}
