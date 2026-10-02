import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"
import { CalendarDotsIcon, CheckIcon, EnvelopeIcon, CaretLeftIcon, CaretRightIcon, CopyIcon, DownloadSimpleIcon, FolderIcon, ClockCounterClockwiseIcon, HourglassIcon, CircleNotchIcon, DotsThreeIcon, PencilSimpleIcon, ArrowsClockwiseIcon, TrashIcon, XIcon } from "@phosphor-icons/react"
import { ArchiveIcon, ArrowUUpLeftIcon } from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { CategoryIcon } from "@/components/CategoryIcon"
import { StatusBadge } from "@/components/DocumentList"
import { ActivityList } from "@/components/ActivityList"
import {
  useActivity, useArchiveDocument, useDeleteDocument, useDocument, useFeed, useInvalidateAll, useUpdateDocument,
} from "@/hooks/queries"
import { useAgent, useAgentViewing } from "@/components/agent"
import { FeedCard } from "@/components/feed"
import { useT } from "@/i18n"
import { area as areaMessages } from "@/i18n/messages/area"
import { common } from "@/i18n/messages/common"
import { documentDetail } from "@/i18n/messages/documentDetail"
import {
  api, CATEGORIES, DOC_TYPES, fileUrl, previewUrl, type Category, type DocDetail, type DocPatch,
} from "@/lib/api"
import {
  categoryLabel,
  docTypeLabel,
  doubtLabel,
  fieldLabel,
  formatAmount,
  formatDate,
  formatNumber,
  parseDate,
} from "@/lib/format"
import { cn } from "@/lib/utils"

const selectClass = "h-8 w-full rounded-md border bg-background px-2 text-sm"

export function DocumentDetailPage() {
  const t = useT(documentDetail)
  const ta = useT(areaMessages)
  const id = Number(useParams().id)
  const { data: doc, isPending, isError } = useDocument(id)
  useAgentViewing(doc)
  // Field hovered in the panel: its source is highlighted on the page.
  const [active, setActive] = useState<string | null>(null)

  if (isError)
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        {t("notFound")}{" "}
        <Link to="/" className="text-primary underline">
          {t("backToDocuments")}
        </Link>
      </div>
    )

  return (
    <>
      <div className="mb-5 flex items-center justify-between gap-4 text-sm">
        <nav className="flex min-w-0 items-center gap-2 text-muted-foreground">
          <Link to={doc?.area ? `/area/${doc.area}` : "/"} className="hover:text-foreground">
            {doc?.area ? ta(`area.${doc.area}`) : t("breadcrumb")}
          </Link>
          <CaretRightIcon className="size-3.5" />
          <span className="truncate font-medium text-foreground">{doc?.title ?? "…"}</span>
        </nav>
      </div>
      {isPending || !doc ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <Skeleton className="aspect-[3/4] w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <Preview doc={doc} active={active} />
          <InfoPanel doc={doc} onActive={setActive} />
        </div>
      )}
    </>
  )
}

function Preview({ doc, active }: { doc: DocDetail; active: string | null }) {
  const t = useT(documentDetail)
  const [page, setPage] = useState(0)
  const [zoom, setZoom] = useState(false)
  const pages = Math.max(doc.page_count, 1)
  const sources = useQuery({
    queryKey: ["sources", doc.id, doc.amount, doc.due_date, doc.issue_date, doc.expiry_date, doc.reference, doc.issuer],
    queryFn: () => api.sources(doc.id),
    enabled: doc.status !== "processing",
    staleTime: Infinity,
  })
  const boxes = (sources.data ?? []).flatMap((s) =>
    s.boxes.filter((b) => b.page === page).map((b) => ({ ...b, field: s.field })),
  )
  // The active field's page comes into view.
  useEffect(() => {
    const target = sources.data?.find((s) => s.field === active)?.boxes[0]
    if (target && target.page !== page) setPage(target.page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])
  return (
    <Card className="gap-0 overflow-hidden p-0">
      <div className={cn("bg-muted/50 p-4", zoom ? "overflow-auto" : "")}>
        {/* White backing on purpose: it is a picture of a paper page, in both themes. */}
        <div className={cn("relative mx-auto", zoom ? "w-max" : "w-full")}>
          <img
            src={previewUrl(doc.id, page)}
            alt={t("previewAlt", { title: doc.title, page: page + 1 })}
            onClick={() => setZoom((z) => !z)}
            className={cn("block rounded bg-white shadow-sm dark:brightness-[0.88]", zoom ? "max-w-none cursor-zoom-out" : "w-full cursor-zoom-in")}
          />
          {boxes.map((b, i) => (
            <span
              key={i}
              title={`${fieldLabel(b.field)} · ${t("sourceHint")}`}
              className={cn(
                "pointer-events-none absolute rounded-sm transition-colors",
                b.field === active ? "bg-amber-300/40 ring-2 ring-amber-500" : "bg-primary/5 ring-1 ring-primary/25",
              )}
              style={{
                left: `${b.x0 * 100 - 0.4}%`,
                top: `${b.y0 * 100 - 0.3}%`,
                width: `${(b.x1 - b.x0) * 100 + 0.8}%`,
                height: `${(b.y1 - b.y0) * 100 + 0.6}%`,
              }}
            />
          ))}
        </div>
      </div>
      <div className="flex items-center justify-center gap-3 border-t py-2 text-sm">
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          aria-label={t("previousPage")}
        >
          <CaretLeftIcon />
        </Button>
        <span className="tabular-nums">
          {page + 1} / {pages}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={page >= pages - 1}
          onClick={() => setPage((p) => p + 1)}
          aria-label={t("nextPage")}
        >
          <CaretRightIcon />
        </Button>
      </div>
    </Card>
  )
}

type Draft = Required<Omit<DocPatch, "validated" | "keep_forever">>

function toDraft(doc: DocDetail): Draft {
  return {
    title: doc.title,
    category: doc.category,
    issuer: doc.issuer,
    amount: doc.amount,
    issue_date: doc.issue_date,
    due_date: doc.due_date,
    expiry_date: doc.expiry_date,
    reference: doc.reference,
    doc_type: doc.doc_type,
    person: doc.person,
  }
}

function InfoPanel({ doc, onActive }: { doc: DocDetail; onActive: (field: string | null) => void }) {
  const t = useT(documentDetail)
  const agent = useAgent()
  const feed = useFeed()
  const question = feed.data?.items.find((i) => i.kind === "question" && i.document_ids.includes(doc.id))
  const tc = useT(common)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Draft>(() => toDraft(doc))
  const update = useUpdateDocument(doc.id)
  const remove = useDeleteDocument()
  const archiving = useArchiveDocument()
  const invalidate = useInvalidateAll()
  const reanalyze = useMutation({ mutationFn: () => api.reanalyze(doc.id), onSuccess: invalidate })
  const navigate = useNavigate()

  useEffect(() => {
    if (!editing) setDraft(toDraft(doc))
  }, [doc, editing])

  const processing = doc.status === "processing"
  const waiting = doc.status === "waiting"
  const missing = new Set(doc.missing_fields)
  // Doubts of the reading ("unverified:due_date"), by field: highlighted, value kept.
  const doubts = new Map(
    doc.missing_fields.filter((f) => f.includes(":")).map((f) => [f.split(":")[1], doubtLabel(f)]),
  )
  const dueSoon = doc.due_date ? (parseDate(doc.due_date).getTime() - Date.now()) / 86_400_000 < 15 : false

  const save = (validated = false) =>
    update.mutate(
      { ...draft, validated },
      {
        onSuccess: () => {
          setEditing(false)
          toast.success(validated ? t("validated") : t("saved"))
        },
        onError: (e) => toast.error(e.message),
      },
    )

  const rows: { key: keyof Draft; type: "text" | "number" | "date" | "docType"; display: string }[] = [
    { key: "amount", type: "number", display: formatAmount(doc.amount) },
    { key: "issue_date", type: "date", display: formatDate(doc.issue_date) },
    { key: "due_date", type: "date", display: formatDate(doc.due_date) },
    { key: "expiry_date", type: "date", display: formatDate(doc.expiry_date) },
    { key: "reference", type: "text", display: doc.reference ?? "—" },
    { key: "issuer", type: "text", display: doc.issuer ?? "—" },
    { key: "person", type: "text", display: doc.person ?? "—" },
    { key: "doc_type", type: "docType", display: docTypeLabel(doc.doc_type) },
  ]
  // Breakdown read from the document, shown when it says more than the main amount.
  const details: { key: string; display: string }[] = [
    { key: "amount_ht", value: doc.amount_ht },
    { key: "amount_tva", value: doc.amount_tva },
    { key: "amount_ttc", value: doc.amount_ttc !== doc.amount ? doc.amount_ttc : null },
    { key: "amount_due", value: doc.amount_due !== doc.amount ? doc.amount_due : null },
  ]
    .filter((d) => d.value != null)
    .map((d) => ({ key: d.key, display: formatAmount(d.value ?? null) }))
  if (doc.period_start && doc.period_end)
    details.push({ key: "period", display: `${formatDate(doc.period_start)} – ${formatDate(doc.period_end)}` })
  if (doc.iban) details.push({ key: "iban", display: doc.iban })
  if (doc.siret) details.push({ key: "siret", display: doc.siret })
  const year = (doc.issue_date ?? doc.due_date ?? doc.created_at).slice(0, 4)
  // Keep a legacy value that is not a known type selectable, so that saving does not drop it.
  const docTypes: string[] =
    draft.doc_type && !(DOC_TYPES as readonly string[]).includes(draft.doc_type) ? [...DOC_TYPES, draft.doc_type] : [...DOC_TYPES]

  return (
    <Card className="gap-0 p-0">
      <div className="flex items-start gap-4 border-b p-5">
        <CategoryIcon category={doc.category} size="lg" />
        <div className="min-w-0 flex-1">
          {editing ? (
            <Input
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              aria-label={fieldLabel("title")}
              className="h-9 text-base font-semibold"
            />
          ) : (
            <h1 className="text-lg font-semibold">{processing ? t("processing") : doc.title}</h1>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {editing ? (
              <select
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value as Category })}
                aria-label={fieldLabel("category")}
                className="h-8 rounded-md border bg-background px-2 text-sm"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel(c)}
                  </option>
                ))}
              </select>
            ) : (
              <span>{categoryLabel(doc.category)}</span>
            )}
            <StatusBadge doc={doc} />
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("moreActions")} />}>
            <DotsThreeIcon />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => reanalyze.mutate()}>
              <ArrowsClockwiseIcon /> {t("reanalyze")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => agent.open(t("letterAbout", { title: doc.title, id: doc.id }))}>
              <EnvelopeIcon /> {t("writeLetter")}
            </DropdownMenuItem>
            <DropdownMenuItem render={<a href={fileUrl(doc.id)} target="_blank" rel="noreferrer" />}>
              <DownloadSimpleIcon /> {t("openOriginal")}
            </DropdownMenuItem>
            {doc.archived_at === null && (
              <DropdownMenuItem onClick={() => archiving.archive.mutate(doc.id)}>
                <ArchiveIcon /> {t("archive")}
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() =>
                remove.mutate(doc.id, { onSuccess: () => navigate(doc.area ? `/papers?area=${doc.area}` : "/papers") })
              }
            >
              <TrashIcon /> {t("trash")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {question && (
        <ul className="border-b bg-amber-50/50 dark:bg-amber-500/5">
          <FeedCard item={question} />
        </ul>
      )}
      <OrganizeNotices doc={doc} />
      {waiting && (
        <div className="flex items-start gap-3 border-b px-5 py-4">
          <HourglassIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">{t("waiting")}</p>
            <p className="text-sm text-muted-foreground">{t("waitingHint")}</p>
          </div>
        </div>
      )}
      {!processing && !waiting && <InShort doc={doc} />}

      <div className="p-5">
        <h2 className="mb-2 font-semibold">{t("extracted")}</h2>
        {processing || reanalyze.isPending ? (
          <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <CircleNotchIcon className="size-4 animate-spin" /> {t("reading")}
          </p>
        ) : (
          <dl className="divide-y text-sm">
            {rows.map((row) => {
              const isMissing = missing.has(row.key)
              const doubt = doubts.get(row.key)
              const highlight = row.key === "due_date" && doc.due_date && dueSoon
              const label = fieldLabel(row.key)
              return (
                <div
                  key={row.key}
                  onMouseEnter={() => onActive(row.key)}
                  onMouseLeave={() => onActive(null)}
                  className={cn(
                    "grid grid-cols-[140px_1fr] items-center gap-3 px-2 py-2.5",
                    highlight && "rounded-md bg-red-50/70 text-red-600 dark:bg-red-500/10 dark:text-red-400",
                    (isMissing || doubt) && "rounded-md bg-amber-50/70 dark:bg-amber-500/10",
                  )}
                  title={doubt ?? undefined}
                >
                  <dt className={cn("text-muted-foreground", highlight && "text-red-600 dark:text-red-400")}>{label}</dt>
                  <dd className="font-medium">
                    {editing && row.type === "docType" ? (
                      <select
                        value={draft.doc_type ?? ""}
                        onChange={(e) => setDraft({ ...draft, doc_type: e.target.value || null })}
                        aria-label={label}
                        className={selectClass}
                      >
                        <option value="">{tc("empty")}</option>
                        {docTypes.map((type) => (
                          <option key={type} value={type}>
                            {docTypeLabel(type)}
                          </option>
                        ))}
                      </select>
                    ) : editing ? (
                      <Input
                        type={row.type}
                        step={row.type === "number" ? "0.01" : undefined}
                        value={(draft[row.key] as string | number | null) ?? ""}
                        onChange={(e) => {
                          const v = e.target.value
                          setDraft({ ...draft, [row.key]: v === "" ? null : row.type === "number" ? Number(v) : v })
                        }}
                        aria-label={label}
                        className="h-8"
                      />
                    ) : isMissing ? (
                      <span className="text-amber-700 dark:text-amber-400">{t("toComplete")}</span>
                    ) : doubt && row.display === "—" ? (
                      <span className="text-amber-700 dark:text-amber-400">{doubt}</span>
                    ) : (
                      <span className="flex items-center gap-1.5">
                        {highlight && <CalendarDotsIcon className="size-3.5" />}
                        {row.display}
                      </span>
                    )}
                  </dd>
                </div>
              )
            })}
            {!editing &&
              details.map((d) => (
                <div key={d.key} className="grid grid-cols-[140px_1fr] items-center gap-3 px-2 py-2.5">
                  <dt className="text-muted-foreground">{fieldLabel(d.key)}</dt>
                  <dd className="font-medium tabular-nums">{d.display}</dd>
                </div>
              ))}
          </dl>
        )}

        <div className="mt-5">
          <div className="mb-1.5 flex justify-between text-sm">
            <span className="text-muted-foreground">
              {doc.extractor.includes("llm") ? t("confidenceLlm") : t("confidenceRules")}
            </span>
            <span className="font-medium tabular-nums">
              {formatNumber(doc.confidence, { style: "percent", maximumFractionDigits: 0 })}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                doc.confidence >= 0.8 ? "bg-emerald-500" : doc.confidence >= 0.6 ? "bg-amber-500" : "bg-red-500",
              )}
              style={{ width: `${doc.confidence * 100}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            {doc.extractor === "rules"
              ? t("extractor.rules")
              : doc.extractor === "manual"
                ? t("extractor.manual")
                : t("extractor.llm")}
          </p>
        </div>

        <RetentionInfo doc={doc} />

        <p className="mt-5 flex items-center gap-2 text-sm text-primary">
          <FolderIcon className="size-4" />
          <Link to={doc.area ? `/papers?area=${doc.area}` : "/papers"} className="hover:underline">
            {categoryLabel(doc.category)}
          </Link>
          <CaretRightIcon className="size-3" /> {year}
          <CaretRightIcon className="size-3" />{" "}
          <span className="truncate text-muted-foreground" title={t("standardNameHint")}>
            {doc.standard_name}
          </span>
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-t p-4">
        {editing ? (
          <>
            <Button onClick={() => save(true)} disabled={update.isPending}>
              <CheckIcon /> {t("saveAndValidate")}
            </Button>
            <Button variant="outline" onClick={() => save(false)} disabled={update.isPending}>
              {tc("action.save")}
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              <XIcon /> {tc("action.cancel")}
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={() => setEditing(true)} disabled={processing}>
              <PencilSimpleIcon /> {tc("action.edit")}
            </Button>
            {doc.status === "to_review" && (
              <Button onClick={() => save(true)} disabled={update.isPending}>
                <CheckIcon /> {t("validate")}
              </Button>
            )}
            <Button variant="outline" render={<a href={fileUrl(doc.id)} download={doc.standard_name} />} nativeButton={false}>
              <DownloadSimpleIcon /> {t("export")}
            </Button>
          </>
        )}
      </div>

      {doc.text && (
        <details className="border-t px-5 py-3 text-sm">
          <summary className="cursor-pointer text-muted-foreground">{t("extractedText")}</summary>
          <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-muted/50 p-3 font-sans text-xs whitespace-pre-wrap">{doc.text}</pre>
        </details>
      )}
      <DocumentHistory id={doc.id} />
    </Card>
  )
}

function DocumentHistory({ id }: { id: number }) {
  const t = useT(documentDetail)
  const history = useActivity({ document_id: id })
  return (
    <details className="border-t text-sm">
      <summary className="cursor-pointer px-5 py-3 text-muted-foreground">
        {history.data ? t("historyCount", { count: history.data.length }) : t("history")}
      </summary>
      <div className="border-t">
        <ActivityList entries={history.data} loading={history.isPending} linkDocuments={false} />
      </div>
    </details>
  )
}

/** Probable duplicate or old version: Binder flags it, you decide. */
function OrganizeNotices({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  const original = useDocument(doc.duplicate_of)
  const latest = useDocument(doc.superseded_by)
  const update = useUpdateDocument(doc.id)
  const remove = useDeleteDocument()
  const { unarchive } = useArchiveDocument()
  const navigate = useNavigate()

  if (doc.archived_at !== null)
    return (
      <div className="flex flex-wrap items-center gap-3 border-b bg-muted/60 px-5 py-3 text-sm">
        <ArchiveIcon className="size-4 shrink-0 text-muted-foreground" />
        <p className="min-w-0 flex-1">{t(`archivedBecause.${doc.archive_reason ?? "user"}`)}</p>
        <Button size="sm" variant="outline" disabled={unarchive.isPending} onClick={() => unarchive.mutate(doc.id)}>
          <ArrowUUpLeftIcon /> {t("unarchive")}
        </Button>
      </div>
    )

  if (doc.duplicate_of !== null)
    return (
      <div className="flex flex-wrap items-center gap-3 border-b bg-amber-50/70 px-5 py-3 text-sm dark:bg-amber-500/10">
        <CopyIcon className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <p className="min-w-0 flex-1">
          {t("duplicate.before")}
          <Link to={`/documents/${doc.duplicate_of}`} className="font-medium underline">
            {t("quoted", { title: original.data?.title ?? "…" })}
          </Link>
          {t("duplicate.after")}
        </p>
        <Button
          size="sm"
          variant="outline"
          disabled={update.isPending}
          onClick={() => update.mutate({ validated: true }, { onSuccess: () => toast.success(t("keptBoth")) })}
        >
          {t("keepBoth")}
        </Button>
        <Button
          size="sm"
          disabled={remove.isPending}
          onClick={() =>
            remove.mutate(doc.id, { onSuccess: () => navigate(`/documents/${doc.duplicate_of}`) })
          }
        >
          <TrashIcon /> {t("trashDuplicate")}
        </Button>
      </div>
    )

  if (doc.superseded_by !== null)
    return (
      <div className="flex items-center gap-3 border-b bg-muted/60 px-5 py-3 text-sm">
        <ClockCounterClockwiseIcon className="size-4 shrink-0 text-muted-foreground" />
        <p>
          {t("superseded.before")}
          <Link to={`/documents/${doc.superseded_by}`} className="font-medium underline">
            {t("quoted", { title: latest.data?.title ?? "…" })}
          </Link>
          {latest.data?.issue_date ? t("superseded.date", { date: formatDate(latest.data.issue_date) }) : ""}
          {t("superseded.after")}
        </p>
      </div>
    )

  return null
}

function RetentionInfo({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  const update = useUpdateDocument(doc.id)
  const { archive } = useArchiveDocument()
  if (!doc.retention_rule) return null
  const setKeep = (keep_forever: boolean) =>
    update.mutate(
      { keep_forever },
      { onSuccess: () => toast.success(keep_forever ? t("keptForever") : t("retentionRestored")) },
    )
  return (
    <div className="mt-5 rounded-lg bg-muted/60 px-4 py-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium">{t("retention")}</p>
          <p className="text-muted-foreground">
            {doc.retention_rule}
            {doc.keep_until && !doc.keep_forever ? t("keepUntil", { date: formatDate(doc.keep_until) }) : ""}
          </p>
          {doc.renew_from && !doc.superseded_by && (
            <p className="mt-1 text-muted-foreground">{t("renewFrom", { date: formatDate(doc.renew_from) })}</p>
          )}
        </div>
        {doc.keep_forever ? (
          <Button variant="ghost" size="sm" onClick={() => setKeep(false)} disabled={update.isPending}>
            {t("restore")}
          </Button>
        ) : (
          doc.archivable_reason && (
            <div className="flex shrink-0 gap-2">
              <Button variant="ghost" size="sm" onClick={() => setKeep(true)} disabled={update.isPending}>
                {t("keep")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => archive.mutate(doc.id)} disabled={archive.isPending}>
                <ArchiveIcon /> {t("archiveIt")}
              </Button>
            </div>
          )
        )}
      </div>
      {doc.archivable_reason && <p className="mt-2 text-muted-foreground">{doc.archivable_reason}.</p>}
    </div>
  )
}

/** The letter explained in plain words, and what needs doing. */
function InShort({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  const qc = useQueryClient()
  const key = ["explanation", doc.id, doc.amount, doc.due_date, doc.expiry_date, doc.title]
  const ex = useQuery({ queryKey: key, queryFn: () => api.explanation(doc.id), staleTime: Infinity })
  const refresh = useMutation({
    mutationFn: () => api.explanation(doc.id, true),
    onSuccess: (data) => qc.setQueryData(key, data),
  })
  return (
    <div className="border-b px-5 py-4 text-sm">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="font-semibold">{t("inShort")}</h2>
        {ex.data &&
          (ex.data.action_required ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
              {t("actionRequired")}
            </span>
          ) : (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
              {t("nothingToDo")}
            </span>
          ))}
        {ex.data && (
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="ml-auto text-muted-foreground hover:text-foreground"
            aria-label={t("reexplain")}
            title={t("reexplain")}
          >
            <ArrowsClockwiseIcon className={cn("size-3.5", refresh.isPending && "animate-spin")} />
          </button>
        )}
      </div>
      {ex.isPending ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <CircleNotchIcon className="size-4 animate-spin" /> {t("readingLetter")}
        </p>
      ) : ex.isError ? (
        <p className="text-muted-foreground">{t("explanationUnavailable")}</p>
      ) : (
        <>
          <p className="leading-relaxed">{ex.data.summary}</p>
          {ex.data.actions.length > 0 && (
            <ul className="mt-2 space-y-1">
              {ex.data.actions.map((a) => (
                <li key={a.label} className="flex items-start gap-2 font-medium">
                  <CheckIcon className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <span>
                    {a.label}
                    {a.due_date && (
                      <span className="font-normal text-muted-foreground">{t("before", { date: formatDate(a.due_date) })}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {ex.data.key_points.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-muted-foreground">
              {ex.data.key_points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11px] text-muted-foreground">
            {ex.data.engine === "llm" ? t("engine.llm") : t("engine.rules")}
          </p>
        </>
      )}
    </div>
  )
}
