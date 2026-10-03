import { toast } from "sonner"
import { ArchiveIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Glossed } from "@/components/glossary"
import { useArchiveDocument, useUpdateDocument } from "@/hooks/queries"
import { useT } from "@/i18n"
import { documentDetail } from "@/i18n/messages/documentDetail"
import type { DocDetail } from "@/lib/api"
import { formatDate } from "@/lib/format"

/** How long the paper is kept and why; keep it forever, or archive it once it may go. */
export function RetentionInfo({ doc }: { doc: DocDetail }) {
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
          <p className="font-medium">
            <Glossed text={t("retention")} />
          </p>
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
