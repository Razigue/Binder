import { useMemo, useState } from "react"
import { toast } from "sonner"
import { ArrowCounterClockwiseIcon, TrashIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { PageHeader } from "@/components/layout/AppLayout"
import {
  RowCheckbox, SelectionBar, SelectionMenu, selectableRow, selectedRowClass, useSelection, useSelectionKeys,
  type SelectionAction,
} from "@/components/selection"
import { useBulkDocuments, usePurgeDocument, useRestoreDocument, useTrash } from "@/hooks/queries"
import { useT } from "@/i18n"
import { selection as selectionMessages } from "@/i18n/messages/selection"
import { trash as messages } from "@/i18n/messages/trash"
import type { Doc } from "@/lib/api"
import { categoryLabel, formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

export function TrashPage() {
  const t = useT(messages)
  const ts = useT(selectionMessages)
  const trash = useTrash()
  const restore = useRestoreDocument()
  const purge = usePurgeDocument()
  const bulk = useBulkDocuments()
  const [target, setTarget] = useState<Doc | null>(null)
  // Ids to delete permanently together, waiting for confirmation.
  const [purging, setPurging] = useState<number[] | null>(null)
  const order = useMemo(() => (trash.data ?? []).map((d) => d.id), [trash.data])
  const selection = useSelection(order)
  const fail = (e: Error) => toast.error(e.message)

  const actions: SelectionAction[] = selection.ids.length
    ? [
        {
          key: "restore",
          label: ts("restore"),
          icon: ArrowCounterClockwiseIcon,
          primary: true,
          onSelect: () => bulk.restore.mutate(selection.ids, { onSuccess: selection.clear, onError: fail }),
        },
        {
          key: "purge",
          label: ts("purge"),
          icon: TrashIcon,
          primary: true,
          destructive: true,
          shortcut: ts("shortcutDelete"),
          onSelect: () => setPurging(selection.ids),
        },
      ]
    : []
  useSelectionKeys(selection, actions.find((a) => a.key === "purge")?.onSelect)

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
          <SelectionMenu selection={selection} actions={actions}>
            <ul className="divide-y">
              {trash.data.map((d) => (
                <li
                  key={d.id}
                  {...selectableRow(selection, d.id)}
                  className={cn("group/row relative flex flex-wrap items-center gap-3 px-5 py-3", selectedRowClass)}
                >
                  <span className="size-9 shrink-0" />
                  <RowCheckbox selection={selection} id={d.id} label={d.title || d.filename}>
                    <CategoryIcon category={d.category} />
                  </RowCheckbox>
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
                    <ArrowCounterClockwiseIcon /> {t("restore")}
                  </Button>
                  <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setTarget(d)}>
                    <TrashIcon /> {t("purge")}
                  </Button>
                </li>
              ))}
            </ul>
          </SelectionMenu>
        )}
      </Card>
      <SelectionBar selection={selection} actions={actions} />
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
      <ConfirmDialog
        open={purging !== null}
        onOpenChange={(open) => !open && setPurging(null)}
        title={ts("purgeTitle", { count: purging?.length ?? 0 })}
        description={ts("purgeDescription", { count: purging?.length ?? 0 })}
        confirmLabel={ts("purge")}
        onConfirm={async () => {
          if (!purging) return
          const result = await bulk.purge.mutateAsync(purging)
          selection.clear()
          toast.success(result.message)
        }}
      />
    </>
  )
}
