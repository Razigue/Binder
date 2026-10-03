import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { ArchiveIcon, ArrowsClockwiseIcon, CaretRightIcon, CheckIcon, CircleNotchIcon, DotsThreeIcon, DownloadSimpleIcon, EnvelopeIcon, FolderIcon, HourglassIcon, PencilSimpleIcon, TrashIcon, XIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAgent } from "@/components/agent/context"
import { CategoryIcon } from "@/components/CategoryIcon"
import { StatusBadge } from "@/components/DocumentList"
import { FeedCard } from "@/components/feed"
import { useArchiveDocument, useDeleteDocument, useFeed, useReanalyze, useUpdateDocument } from "@/hooks/queries"
import { useT } from "@/i18n"
import { common } from "@/i18n/messages/common"
import { documentDetail } from "@/i18n/messages/documentDetail"
import { CATEGORIES, fileUrl, type DocDetail } from "@/lib/api"
import { categoryLabel, fieldLabel, formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"
import { DocumentFields } from "./DocumentFields"
import { DocumentHistory } from "./DocumentHistory"
import { toDraft, type Draft } from "./draft"
import { InShort } from "./InShort"
import { OrganizeNotices } from "./OrganizeNotices"
import { RetentionInfo } from "./RetentionInfo"

/** Everything Binder knows about the document, beside its page: what it says, what to do, what
 * was read (to correct), how long to keep it. */
export function InfoPanel({ doc, onActive }: { doc: DocDetail; onActive: (field: string | null) => void }) {
  const t = useT(documentDetail)
  const tc = useT(common)
  const feed = useFeed()
  const question = feed.data?.items.find((i) => i.kind === "question" && i.document_ids.includes(doc.id))
  // Paid twice, price rise…: shown on each paper involved, with a way to see the others.
  const alerts = feed.data?.items.filter((i) => i.kind === "anomaly" && i.document_ids.includes(doc.id)) ?? []
  // The fields being corrected, from the document as it was when editing began; null otherwise.
  const [draft, setDraft] = useState<Draft | null>(null)
  const editing = draft !== null
  const update = useUpdateDocument(doc.id)
  const reanalyze = useReanalyze()

  const processing = doc.status === "processing"
  const waiting = doc.status === "waiting"
  const year = (doc.issue_date ?? doc.due_date ?? doc.created_at).slice(0, 4)

  const save = (validated = false) =>
    update.mutate(
      // Validating without editing sends the fields as they are.
      { ...(draft ?? toDraft(doc)), validated },
      {
        onSuccess: () => {
          setDraft(null)
          toast.success(validated ? t("validated") : t("saved"))
        },
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <Card className="gap-0 p-0">
      <div className="flex items-start gap-4 border-b p-5">
        <CategoryIcon category={doc.category} size="lg" />
        <div className="min-w-0 flex-1">
          {draft ? (
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
            {draft ? (
              <select
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: CATEGORIES.find((c) => c === e.target.value) ?? draft.category })}
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
        <DocumentMenu doc={doc} onReanalyze={() => reanalyze.mutate(doc.id)} />
      </div>

      {question && (
        <ul className="border-b bg-amber-50/50 dark:bg-amber-500/5">
          <FeedCard item={question} />
        </ul>
      )}
      {alerts.length > 0 && (
        <ul className="divide-y border-b bg-amber-50/50 dark:bg-amber-500/5">
          {alerts.map((item) => (
            <FeedCard key={item.key} item={item} />
          ))}
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
          <p role="status" className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <CircleNotchIcon className="size-4 animate-spin" /> {t("reading")}
          </p>
        ) : (
          <DocumentFields doc={doc} draft={draft} onDraft={setDraft} onActive={onActive} />
        )}

        <ReadingConfidence doc={doc} />
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
            <Button variant="ghost" onClick={() => setDraft(null)}>
              <XIcon /> {tc("action.cancel")}
            </Button>
          </>
        ) : (
          <>
            <Button variant="outline" onClick={() => setDraft(toDraft(doc))} disabled={processing}>
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

/** Read again, write a letter about it, open the original, archive, trash. */
function DocumentMenu({ doc, onReanalyze }: { doc: DocDetail; onReanalyze: () => void }) {
  const t = useT(documentDetail)
  const agent = useAgent()
  const remove = useDeleteDocument()
  const { archive } = useArchiveDocument()
  const navigate = useNavigate()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("moreActions")} />}>
        <DotsThreeIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem onClick={onReanalyze}>
          <ArrowsClockwiseIcon /> {t("reanalyze")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => agent.open(t("letterAbout", { title: doc.title, id: doc.id }))}>
          <EnvelopeIcon /> {t("writeLetter")}
        </DropdownMenuItem>
        <DropdownMenuItem render={<a href={fileUrl(doc.id)} target="_blank" rel="noreferrer" />}>
          <DownloadSimpleIcon /> {t("openOriginal")}
        </DropdownMenuItem>
        {doc.archived_at === null && (
          <DropdownMenuItem onClick={() => archive.mutate(doc.id)}>
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
  )
}

/** How sure the reading is, and who read it (the model, the rules, the user). */
function ReadingConfidence({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  return (
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
      <p className="mt-1.5 text-[0.6875rem] text-muted-foreground">
        {doc.extractor === "rules"
          ? t("extractor.rules")
          : doc.extractor === "manual"
            ? t("extractor.manual")
            : t("extractor.llm")}
      </p>
    </div>
  )
}
