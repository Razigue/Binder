import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { ArchiveIcon, ArrowUUpLeftIcon, ClockCounterClockwiseIcon, CopyIcon, TrashIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { useArchiveDocument, useDeleteDocument, useDocument, useUpdateDocument } from "@/hooks/queries"
import { useT } from "@/i18n"
import { documentDetail } from "@/i18n/messages/documentDetail"
import type { DocDetail } from "@/lib/api"
import { formatDate } from "@/lib/format"

/** Probable duplicate or old version: Binder flags it, you decide. */
export function OrganizeNotices({ doc }: { doc: DocDetail }) {
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
