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
import { api, CATEGORIES, fileUrl, previewUrl, type Category, type DocDetail, type DocPatch } from "@/lib/api"
import { FIELD_LABELS, formatAmount, formatDate, parseDate } from "@/lib/format"
import { cn } from "@/lib/utils"

export function DocumentDetailPage() {
  const id = Number(useParams().id)
  const { data: doc, isPending, isError } = useDocument(id)

  if (isError)
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        Document introuvable. <Link to="/documents" className="text-primary underline">Retour aux documents</Link>
      </div>
    )

  return (
    <>
      <div className="mb-5 flex items-center justify-between gap-4 text-sm">
        <nav className="flex min-w-0 items-center gap-2 text-muted-foreground">
          <Link to="/documents" className="hover:text-foreground">Documents</Link>
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
  const [page, setPage] = useState(0)
  const [zoom, setZoom] = useState(false)
  const pages = Math.max(doc.page_count, 1)
  return (
    <Card className="gap-0 overflow-hidden p-0">
      <div className={cn("bg-muted/50 p-4", zoom ? "overflow-auto" : "")}>
        <img
          src={previewUrl(doc.id, page)}
          alt={`Aperçu de ${doc.title}, page ${page + 1}`}
          onClick={() => setZoom((z) => !z)}
          className={cn("mx-auto rounded bg-white shadow-sm", zoom ? "max-w-none cursor-zoom-out" : "w-full cursor-zoom-in")}
        />
      </div>
      <div className="flex items-center justify-center gap-3 border-t py-2 text-sm">
        <Button variant="ghost" size="icon-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)} aria-label="Page précédente">
          <ChevronLeft />
        </Button>
        <span className="tabular-nums">
          {page + 1} / {pages}
        </span>
        <Button variant="ghost" size="icon-sm" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} aria-label="Page suivante">
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
          toast.success(validated ? "Document validé" : "Modifications enregistrées")
        },
        onError: (e) => toast.error(e.message),
      },
    )

  const rows: { key: keyof Draft; label: string; type: "text" | "number" | "date"; display: string }[] = [
    { key: "amount", label: FIELD_LABELS.amount, type: "number", display: formatAmount(doc.amount) },
    { key: "issue_date", label: FIELD_LABELS.issue_date, type: "date", display: formatDate(doc.issue_date) },
    { key: "due_date", label: FIELD_LABELS.due_date, type: "date", display: formatDate(doc.due_date) },
    { key: "expiry_date", label: FIELD_LABELS.expiry_date, type: "date", display: formatDate(doc.expiry_date) },
    { key: "reference", label: FIELD_LABELS.reference, type: "text", display: doc.reference ?? "—" },
    { key: "issuer", label: "Émetteur", type: "text", display: doc.issuer ?? "—" },
    { key: "doc_type", label: "Type", type: "text", display: doc.doc_type ?? "—" },
  ]
  const year = (doc.issue_date ?? doc.due_date ?? doc.created_at).slice(0, 4)

  return (
    <Card className="gap-0 p-0">
      <div className="flex items-start gap-4 border-b p-5">
        <CategoryIcon category={doc.category} size="lg" />
        <div className="min-w-0 flex-1">
          {editing ? (
            <Input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className="h-9 text-base font-semibold" />
          ) : (
            <h1 className="text-lg font-semibold">{processing ? "Analyse en cours…" : doc.title}</h1>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {editing ? (
              <select
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value as Category })}
                className="h-8 rounded-md border bg-background px-2 text-sm"
              >
                {CATEGORIES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            ) : (
              <span>{doc.category}</span>
            )}
            <StatusBadge doc={doc} />
          </div>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Plus d'actions" />}>
            <MoreHorizontal />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => reanalyze.mutate()}>
              <RefreshCw /> Relancer l'analyse
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate(`/courriers?document=${doc.id}`)}>
              <Mail /> Rédiger un courrier
            </DropdownMenuItem>
            <DropdownMenuItem render={<a href={fileUrl(doc.id)} target="_blank" rel="noreferrer" />}>
              <Download /> Ouvrir l'original
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() =>
                remove.mutate(doc.id, {
                  onSuccess: () => {
                    toast.success("Document mis à la corbeille", {
                      action: {
                        label: "Annuler",
                        onClick: () => restore.mutate(doc.id, { onSuccess: () => navigate(`/documents/${doc.id}`) }),
                      },
                    })
                    navigate("/documents")
                  },
                })
              }
            >
              <Trash2 /> Mettre à la corbeille
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <OrganizeNotices doc={doc} />
      {!processing && <InShort doc={doc} />}

      <div className="p-5">
        <h2 className="mb-2 font-semibold">Informations extraites</h2>
        {processing || reanalyze.isPending ? (
          <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Lecture du document…
          </p>
        ) : (
          <dl className="divide-y text-sm">
            {rows.map((row) => {
              const isMissing = missing.has(row.key)
              const highlight = row.key === "due_date" && doc.due_date && dueSoon
              return (
                <div
                  key={row.key}
                  className={cn(
                    "grid grid-cols-[140px_1fr] items-center gap-3 px-2 py-2.5",
                    highlight && "rounded-md bg-red-50/70 text-red-600",
                    isMissing && "rounded-md bg-amber-50/70",
                  )}
                >
                  <dt className={cn("text-muted-foreground", highlight && "text-red-600")}>{row.label}</dt>
                  <dd className="font-medium">
                    {editing ? (
                      <Input
                        type={row.type}
                        step={row.type === "number" ? "0.01" : undefined}
                        value={(draft[row.key] as string | number | null) ?? ""}
                        onChange={(e) => {
                          const v = e.target.value
                          setDraft({ ...draft, [row.key]: v === "" ? null : row.type === "number" ? Number(v) : v })
                        }}
                        className="h-8"
                      />
                    ) : isMissing ? (
                      <span className="text-amber-700">À compléter</span>
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
            <span className="text-muted-foreground">Confiance {doc.extractor.includes("llm") ? "IA" : "de l'extraction"}</span>
            <span className="font-medium tabular-nums">{Math.round(doc.confidence * 100)} %</span>
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
            Extrait par {doc.extractor === "rules" ? "règles locales" : doc.extractor === "manual" ? "vous (corrigé)" : "le modèle local + règles"}
          </p>
        </div>

        <RetentionInfo doc={doc} />

        <p className="mt-5 flex items-center gap-2 text-sm text-primary">
          <Folder className="size-4" />
          <Link to={`/documents?category=${encodeURIComponent(doc.category)}`} className="hover:underline">{doc.category}</Link>
          <ChevronRight className="size-3" /> {year}
          <ChevronRight className="size-3" /> <span className="truncate text-muted-foreground" title="Nom utilisé au téléchargement et à l'export">{doc.standard_name}</span>
        </p>
      </div>

      <div className="flex flex-wrap gap-2 border-t p-4">
        {editing ? (
          <>
            <Button onClick={() => save(true)} disabled={update.isPending}>
              <Check /> Enregistrer et valider
            </Button>
            <Button variant="outline" onClick={() => save(false)} disabled={update.isPending}>
              Enregistrer
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              <X /> Annuler
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={() => setEditing(true)} disabled={processing}>
              <Pencil /> Modifier
            </Button>
            {doc.status === "to_review" && (
              <Button onClick={() => save(true)} disabled={update.isPending}>
                <Check /> Valider
              </Button>
            )}
            <Button variant="outline" render={<a href={fileUrl(doc.id)} download={doc.standard_name} />} nativeButton={false}>
              <Download /> Exporter
            </Button>
          </>
        )}
      </div>

      {doc.text && (
        <details className="border-t px-5 py-3 text-sm">
          <summary className="cursor-pointer text-muted-foreground">Texte extrait</summary>
          <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-muted/50 p-3 font-sans text-xs whitespace-pre-wrap">{doc.text}</pre>
        </details>
      )}
      <DocumentHistory id={doc.id} />
    </Card>
  )
}

function DocumentHistory({ id }: { id: number }) {
  const history = useActivity({ document_id: id })
  return (
    <details className="border-t text-sm">
      <summary className="cursor-pointer px-5 py-3 text-muted-foreground">
        Historique{history.data ? ` (${history.data.length})` : ""}
      </summary>
      <div className="border-t">
        <ActivityList entries={history.data} loading={history.isPending} linkDocuments={false} />
      </div>
    </details>
  )
}

/** Doublon probable ou ancienne version : Binder signale, vous décidez. */
function OrganizeNotices({ doc }: { doc: DocDetail }) {
  const original = useDocument(doc.duplicate_of)
  const latest = useDocument(doc.superseded_by)
  const update = useUpdateDocument(doc.id)
  const remove = useDeleteDocument()
  const restore = useRestoreDocument()
  const navigate = useNavigate()

  if (doc.duplicate_of !== null)
    return (
      <div className="flex flex-wrap items-center gap-3 border-b bg-amber-50/70 px-5 py-3 text-sm">
        <Copy className="size-4 shrink-0 text-amber-600" />
        <p className="min-w-0 flex-1">
          Doublon probable de{" "}
          <Link to={`/documents/${doc.duplicate_of}`} className="font-medium underline">
            « {original.data?.title ?? "…"} »
          </Link>
          . Son échéance n'est pas comptée deux fois.
        </p>
        <Button
          size="sm"
          variant="outline"
          disabled={update.isPending}
          onClick={() => update.mutate({ validated: true }, { onSuccess: () => toast.success("Les deux documents sont conservés") })}
        >
          Garder les deux
        </Button>
        <Button
          size="sm"
          disabled={remove.isPending}
          onClick={() =>
            remove.mutate(doc.id, {
              onSuccess: () => {
                toast.success("Doublon mis à la corbeille", {
                  action: { label: "Annuler", onClick: () => restore.mutate(doc.id) },
                })
                navigate(`/documents/${doc.duplicate_of}`)
              },
            })
          }
        >
          <Trash2 /> Mettre le doublon à la corbeille
        </Button>
      </div>
    )

  if (doc.superseded_by !== null)
    return (
      <div className="flex items-center gap-3 border-b bg-muted/60 px-5 py-3 text-sm">
        <History className="size-4 shrink-0 text-muted-foreground" />
        <p>
          Ancienne version. La plus récente est{" "}
          <Link to={`/documents/${doc.superseded_by}`} className="font-medium underline">
            « {latest.data?.title ?? "…"} »
          </Link>
          {latest.data?.issue_date ? ` du ${formatDate(latest.data.issue_date)}` : ""}.
        </p>
      </div>
    )

  return null
}

function RetentionInfo({ doc }: { doc: DocDetail }) {
  const update = useUpdateDocument(doc.id)
  if (!doc.retention_rule) return null
  const setKeep = (keep_forever: boolean) =>
    update.mutate({ keep_forever }, { onSuccess: () => toast.success(keep_forever ? "Document conservé sans limite" : "Durée conseillée rétablie") })
  return (
    <div className="mt-5 rounded-lg border px-4 py-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium">Conservation</p>
          <p className="text-muted-foreground">
            {doc.retention_rule}
            {doc.keep_until && !doc.keep_forever ? ` · jusqu'au ${formatDate(doc.keep_until)}` : ""}
          </p>
          {doc.renew_from && !doc.superseded_by && (
            <p className="mt-1 text-muted-foreground">À renouveler à partir du {formatDate(doc.renew_from)}</p>
          )}
        </div>
        {doc.keep_forever ? (
          <Button variant="ghost" size="sm" onClick={() => setKeep(false)} disabled={update.isPending}>
            Rétablir
          </Button>
        ) : (
          doc.deletable_reason && (
            <Button variant="outline" size="sm" onClick={() => setKeep(true)} disabled={update.isPending}>
              Garder
            </Button>
          )
        )}
      </div>
      {doc.deletable_reason && (
        <p className="mt-2 text-amber-700">
          {doc.deletable_reason}. <Link to="/tri" className="underline">Voir les documents à trier</Link>
        </p>
      )}
    </div>
  )
}

/** Le courrier expliqué simplement, et ce qu'il y a à faire. */
function InShort({ doc }: { doc: DocDetail }) {
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
        <h2 className="font-semibold">En bref</h2>
        {ex.data &&
          (ex.data.action_required ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">Action requise</span>
          ) : (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">Rien à faire</span>
          ))}
        {ex.data && (
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="ml-auto text-muted-foreground hover:text-foreground"
            aria-label="Réexpliquer"
            title="Réexpliquer"
          >
            <RefreshCw className={cn("size-3.5", refresh.isPending && "animate-spin")} />
          </button>
        )}
      </div>
      {ex.isPending ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Lecture du courrier…
        </p>
      ) : ex.isError ? (
        <p className="text-muted-foreground">Explication indisponible.</p>
      ) : (
        <>
          <p className="leading-relaxed">{ex.data.summary}</p>
          {ex.data.actions.length > 0 && (
            <ul className="mt-2 space-y-1">
              {ex.data.actions.map((a) => (
                <li key={a.label} className="flex items-start gap-2 font-medium">
                  <Check className="mt-0.5 size-4 shrink-0 text-amber-600" />
                  <span>
                    {a.label}
                    {a.due_date && <span className="font-normal text-muted-foreground"> · avant le {formatDate(a.due_date)}</span>}
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
            {ex.data.engine === "llm" ? "Rédigé par le modèle local" : "Rédigé par les règles locales"}
          </p>
        </>
      )}
    </div>
  )
}
