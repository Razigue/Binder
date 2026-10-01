import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { Archive, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { PageHeader } from "@/components/layout/AppLayout"
import { useInvalidateAll, useRetention } from "@/hooks/queries"
import { api } from "@/lib/api"
import { formatDate } from "@/lib/format"

export function SortingPage() {
  const { data, isPending } = useRetention()
  const [unchecked, setUnchecked] = useState<Set<number>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const invalidate = useInvalidateAll()
  const keep = useMutation({
    mutationFn: (id: number) => api.updateDocument(id, { keep_forever: true }),
    onSuccess: invalidate,
  })
  const selected = useMemo(() => (data ?? []).filter((d) => !unchecked.has(d.id)), [data, unchecked])

  const toggle = (id: number) =>
    setUnchecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <>
      <PageHeader
        title="Tri"
        subtitle="Documents que vous n'êtes plus tenu de conserver. Binder ne supprime rien sans vous."
        actions={
          selected.length > 0 && (
            <Button onClick={() => setConfirming(true)}>
              <Trash2 /> Mettre {selected.length} document{selected.length > 1 ? "s" : ""} à la corbeille
            </Button>
          )
        }
      />
      <Card className="gap-0 p-0">
        {isPending ? (
          <div className="space-y-2 p-4">
            {[0, 1].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !data?.length ? (
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">
            Rien à trier : tous vos documents sont encore dans leur durée de conservation.
          </p>
        ) : (
          <ul className="divide-y">
            {data.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={!unchecked.has(d.id)}
                  onChange={() => toggle(d.id)}
                  aria-label={`Sélectionner ${d.title}`}
                />
                <CategoryIcon category={d.category} />
                <span className="min-w-0 flex-1">
                  <Link to={`/documents/${d.id}`} className="block truncate text-sm font-medium hover:underline">
                    {d.title}
                  </Link>
                  <span className="block text-xs text-muted-foreground">
                    {formatDate(d.issue_date ?? d.created_at)} · {d.deletable_reason}
                  </span>
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={keep.isPending}
                  onClick={() => keep.mutate(d.id, { onSuccess: () => toast.success(`« ${d.title} » sera conservé`) })}
                >
                  <Archive /> Garder
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">
        Durées indicatives pour un particulier, d'après service-public.fr. Un document mis à la corbeille reste
        restaurable.
      </p>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Mettre ${selected.length} document${selected.length > 1 ? "s" : ""} à la corbeille ?`}
        description="Vous pourrez les restaurer depuis la corbeille tant que vous ne les supprimez pas définitivement."
        confirmLabel="Mettre à la corbeille"
        destructive={false}
        onConfirm={async () => {
          const { trashed } = await api.trashDeletable(selected.map((d) => d.id))
          setUnchecked(new Set())
          invalidate()
          toast.success(`${trashed} document${trashed > 1 ? "s" : ""} mis à la corbeille`)
        }}
      />
    </>
  )
}
