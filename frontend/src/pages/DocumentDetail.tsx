import { useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"
import {
  CalendarDays, Check, Mail, ChevronLeft, ChevronRight, Copy, Download, Folder, History, Loader2, MoreHorizontal,
  Pencil, RefreshCw, Trash2, X,
} from "lucide-react"
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
import { LocalBadge } from "@/components/StatusDot"
import { ActivityList } from "@/components/ActivityList"
import {
  useActivity, useDeleteDocument, useDocument, useInvalidateAll, useRestoreDocument, useUpdateDocument,
} from "@/hooks/queries"
import { useT } from "@/i18n"
import { common } from "@/i18n/messages/common"
import { documentDetail } from "@/i18n/messages/documentDetail"
import {
  api, CATEGORIES, DOC_TYPES, fileUrl, previewUrl, type Category, type DocDetail, type DocPatch,
} from "@/lib/api"
import { categoryLabel, docTypeLabel, fieldLabel, formatAmount, formatDate, formatNumber, parseDate } from "@/lib/format"
import { cn } from "@/lib/utils"

const selectClass = "h-8 w-full rounded-md border bg-background px-2 text-sm"

export function DocumentDetailPage() {
  const t = useT(documentDetail)
  const id = Number(useParams().id)
  const { data: doc, isPending, isError } = useDocument(id)

  if (isError)
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        {t("notFound")}{" "}
        <Link to="/documents" className="text-primary underline">
          {t("backToDocuments")}
        </Link>
      </div>
    )

  return (
    <>
      <div className="mb-5 flex items-center justify-between gap-4 text-sm">
        <nav className="flex min-w-0 items-center gap-2 text-muted-foreground">
          <Link to="/documents" className="hover:text-foreground">
            {t("breadcrumb")}
          </Link>
          <ChevronRight className="size-3.5" />
          <span className="truncate font-medium text-foreground">{doc?.title ?? "…"}</span>
        </nav>
        <LocalBadge />
      </div>
      {isPending || !doc ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <Skeleton className="aspect-[3/4] w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <Preview doc={doc} />
          <InfoPanel doc={doc} />
        </div>
      )}
    </>
  )
}

function Preview({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  const [page, setPage] = useState(0)
  const [zoom, setZoom] = useState(false)
  const pages = Math.max(doc.page_count, 1)
  return (
    <Card className="gap-0 overflow-hidden p-0">
      <div className={cn("bg-muted/50 p-4", zoom ? "overflow-auto" : "")}>
        {/* White backing on purpose: it is a picture of a paper page, in both themes. */}
        <img
          src={previewUrl(doc.id, page)}
          alt={t("previewAlt", { title: doc.title, page: page + 1 })}
          onClick={() => setZoom((z) => !z)}
          className={cn("mx-auto rounded bg-white shadow-sm dark:brightness-[0.88]", zoom ? "max-w-none cursor-zoom-out" : "w-full cursor-zoom-in")}
        />
      </div>
      <div className="flex items-center justify-center gap-3 border-t py-2 text-sm">
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          aria-label={t("previousPage")}
        >
          <ChevronLeft />
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
          <ChevronRight />
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
  }
}

function InfoPanel({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  const tc = useT(common)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Draft>(() => toDraft(doc))
  const update = useUpdateDocument(doc.id)
  const remove = useDeleteDocument()
  const restore = useRestoreDocument()
  const invalidate = useInvalidateAll()
  const reanalyze = useMutation({ mutationFn: () => api.reanalyze(doc.id), onSuccess: invalidate })
  const navigate = useNavigate()

  useEffect(() => {
    if (!editing) setDraft(toDraft(doc))
  }, [doc, editing])

  const processing = doc.status === "processing"
  const missing = new Set(doc.missing_fields)
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
    { key: "doc_type", type: "docType", display: docTypeLabel(doc.doc_type) },
  ]
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
            <MoreHorizontal />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => reanalyze.mutate()}>
              <RefreshCw /> {t("reanalyze")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate(`/letters?document=${doc.id}`)}>
              <Mail /> {t("writeLetter")}
            </DropdownMenuItem>
            <DropdownMenuItem render={<a href={fileUrl(doc.id)} target="_blank" rel="noreferrer" />}>
              <Download /> {t("openOriginal")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() =>
                remove.mutate(doc.id, {
                  onSuccess: () => {
                    toast.success(t("trashed"), {
                      action: {
                        label: t("undo"),
                        onClick: () => restore.mutate(doc.id, { onSuccess: () => navigate(`/documents/${doc.id}`) }),
                      },
                    })
                    navigate("/documents")
                  },
                })
              }
            >
              <Trash2 /> {t("trash")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <OrganizeNotices doc={doc} />
      {!processing && <InShort doc={doc} />}

      <div className="p-5">
        <h2 className="mb-2 font-semibold">{t("extracted")}</h2>
        {processing || reanalyze.isPending ? (
          <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> {t("reading")}
          </p>
        ) : (
          <dl className="divide-y text-sm">
            {rows.map((row) => {
              const isMissing = missing.has(row.key)
              const highlight = row.key === "due_date" && doc.due_date && dueSoon
              const label = fieldLabel(row.key)
              return (
                <div
                  key={row.key}
                  className={cn(
                    "grid grid-cols-[140px_1fr] items-center gap-3 px-2 py-2.5",
                    highlight && "rounded-md bg-red-50/70 text-red-600 dark:bg-red-500/10 dark:text-red-400",
                    isMissing && "rounded-md bg-amber-50/70 dark:bg-amber-500/10",
                  )}
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
                    ) : (
                      <span className="flex items-center gap-1.5">
                        {highlight && <CalendarDays className="size-3.5" />}
                        {row.display}
                      </span>
                    )}
                  </dd>
                </div>
              )
            })}
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
          <Folder className="size-4" />
          <Link to={`/documents?category=${encodeURIComponent(doc.category)}`} className="hover:underline">
            {categoryLabel(doc.category)}
          </Link>
          <ChevronRight className="size-3" /> {year}
          <ChevronRight className="size-3" />{" "}
          <span className="truncate text-muted-foreground" title={t("standardNameHint")}>
            {doc.standard_name}
          </span>
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-t p-4">
        {editing ? (
          <>
            <Button onClick={() => save(true)} disabled={update.isPending}>
              <Check /> {t("saveAndValidate")}
            </Button>
            <Button variant="outline" onClick={() => save(false)} disabled={update.isPending}>
              {tc("action.save")}
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              <X /> {tc("action.cancel")}
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={() => setEditing(true)} disabled={processing}>
              <Pencil /> {tc("action.edit")}
            </Button>
            {doc.status === "to_review" && (
              <Button onClick={() => save(true)} disabled={update.isPending}>
                <Check /> {t("validate")}
              </Button>
            )}
            <Button variant="outline" render={<a href={fileUrl(doc.id)} download={doc.standard_name} />} nativeButton={false}>
              <Download /> {t("export")}
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
  const restore = useRestoreDocument()
  const navigate = useNavigate()

  if (doc.duplicate_of !== null)
    return (
      <div className="flex flex-wrap items-center gap-3 border-b bg-amber-50/70 px-5 py-3 text-sm dark:bg-amber-500/10">
        <Copy className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
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
            remove.mutate(doc.id, {
              onSuccess: () => {
                toast.success(t("duplicateTrashed"), {
                  action: { label: t("undo"), onClick: () => restore.mutate(doc.id) },
                })
                navigate(`/documents/${doc.duplicate_of}`)
              },
            })
          }
        >
          <Trash2 /> {t("trashDuplicate")}
        </Button>
      </div>
    )

  if (doc.superseded_by !== null)
    return (
      <div className="flex items-center gap-3 border-b bg-muted/60 px-5 py-3 text-sm">
        <History className="size-4 shrink-0 text-muted-foreground" />
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
          doc.deletable_reason && (
            <Button variant="outline" size="sm" onClick={() => setKeep(true)} disabled={update.isPending}>
              {t("keep")}
            </Button>
          )
        )}
      </div>
      {doc.deletable_reason && (
        <p className="mt-2 text-amber-700 dark:text-amber-400">
          {doc.deletable_reason}.{" "}
          <Link to="/sorting" className="underline">
            {t("seeSorting")}
          </Link>
        </p>
      )}
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
            <RefreshCw className={cn("size-3.5", refresh.isPending && "animate-spin")} />
          </button>
        )}
      </div>
      {ex.isPending ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> {t("readingLetter")}
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
                  <Check className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
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
