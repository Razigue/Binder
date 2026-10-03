import { ActivityList } from "@/components/ActivityList"
import { useActivity } from "@/hooks/queries"
import { useT } from "@/i18n"
import { documentDetail } from "@/i18n/messages/documentDetail"

/** What happened to the document, folded under one line. */
export function DocumentHistory({ id }: { id: number }) {
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
