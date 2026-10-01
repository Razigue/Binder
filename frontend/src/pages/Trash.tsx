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
import type { Doc } from "@/lib/api"
import { formatDate } from "@/lib/format"

export function TrashPage() {
  const trash = useTrash()
  const restore = useRestoreDocument()
  const purge = usePurgeDocument()
  const [target, setTarget] = useState<Doc | null>(null)

  return (
    <>
      <PageHeader
        title="Corbeille"
        subtitle="Les documents supprimés restent ici, restaurables, tant que vous ne les effacez pas définitivement."
      />
      <Card className="gap-0 p-0">
        {trash.isPending ? (
          <div className="space-y-2 p-4">
            {[0, 1].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !trash.data?.length ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">La corbeille est vide.</p>
        ) : (
          <ul className="divide-y">
            {trash.data.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <CategoryIcon category={d.category} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{d.title || d.filename}</span>
                  <span className="block text-xs text-muted-foreground">
                    {d.category} · supprimé le {formatDate(d.deleted_at)}
                  </span>
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={restore.isPending}
                  onClick={() =>
                    restore.mutate(d.id, { onSuccess: () => toast.success(`« ${d.title} » restauré`) })
                  }
                >
                  <RotateCcw /> Restaurer
                </Button>
                <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setTarget(d)}>
                  <Trash2 /> Supprimer définitivement
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => !open && setTarget(null)}
        title="Supprimer définitivement ?"
        description={
          <>
            « {target?.title} » et son fichier seront effacés de votre machine. Cette action est
            irréversible.
          </>
        }
        confirmLabel="Supprimer définitivement"
        onConfirm={async () => {
          if (!target) return
          await purge.mutateAsync(target.id)
          toast.success("Document supprimé définitivement")
        }}
      />
    </>
  )
}
