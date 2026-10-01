import { useState } from "react"
import { toast } from "sonner"
import { RotateCcw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { PageHeader } from "@/components/layout/AppLayout"
import { usePurgeDocument, useRestoreDocument, useTrash } from "@/hooks/queries"
import { useT } from "@/i18n"
import { trash as messages } from "@/i18n/messages/trash"
import type { Doc } from "@/lib/api"
import { categoryLabel, formatDate } from "@/lib/format"

export function TrashPage() {
  const t = useT(messages)
  const trash = useTrash()
  const restore = useRestoreDocument()
  const purge = usePurgeDocument()
  const [target, setTarget] = useState<Doc | null>(null)

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
      />
      <Card className="gap-0 p-0">
        {trash.isPending ? (
          <div className="space-y-2 p-4">
            {[0, 1].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !trash.data?.length ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="divide-y">
            {trash.data.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <CategoryIcon category={d.category} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{d.title || d.filename}</span>
                  <span className="block text-xs text-muted-foreground">
                    {categoryLabel(d.category)} · {t("deletedOn", { date: formatDate(d.deleted_at) })}
                  </span>
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={restore.isPending}
                  onClick={() =>
                    restore.mutate(d.id, { onSuccess: () => toast.success(t("restored", { title: d.title })) })
                  }
                >
                  <RotateCcw /> {t("restore")}
                </Button>
                <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setTarget(d)}>
                  <Trash2 /> {t("purge")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => !open && setTarget(null)}
        title={t("confirmTitle")}
        description={t("confirmDescription", { title: target?.title ?? "" })}
        confirmLabel={t("purge")}
        onConfirm={async () => {
          if (!target) return
          await purge.mutateAsync(target.id)
          toast.success(t("purged"))
        }}
      />
    </>
  )
}
