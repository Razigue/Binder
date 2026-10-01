import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, CircleDashed, Clock, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { PageHeader } from "@/components/layout/AppLayout"
import { Chip } from "@/pages/Documents"
import { useDocuments } from "@/hooks/queries"
import { api, folderExportUrl, type FolderPiece } from "@/lib/api"
import { cn } from "@/lib/utils"

const STATUS: Record<FolderPiece["status"], { icon: typeof CheckCircle2; tone: string; label: string }> = {
  ok: { icon: CheckCircle2, tone: "text-emerald-600", label: "Prêt" },
  partial: { icon: Clock, tone: "text-amber-600", label: "Incomplet" },
  outdated: { icon: AlertTriangle, tone: "text-amber-600", label: "À renouveler" },
  missing: { icon: CircleDashed, tone: "text-muted-foreground", label: "Manquant" },
}

export function FoldersPage() {
  const folders = useQuery({ queryKey: ["folders"], queryFn: api.folders })
  const docs = useDocuments({ limit: 500 })
  const [selected, setSelected] = useState("location")
  const folder = folders.data?.find((f) => f.key === selected)
  const titles = new Map(docs.data?.map((d) => [d.id, d.title]))

  return (
    <>
      <PageHeader title="Dossiers" subtitle="Rassemblez les pièces d'une démarche et voyez ce qui manque." />
      <div className="mb-4 flex flex-wrap gap-2">
        {folders.data?.map((f) => (
          <Chip key={f.key} active={f.key === selected} onClick={() => setSelected(f.key)}>
            {f.title} <span>{f.ready}/{f.total}</span>
          </Chip>
        ))}
      </div>
      {!folder ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <Card className="gap-0 p-0">
          <div className="flex flex-wrap items-center gap-4 border-b p-5">
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold">{folder.title}</h2>
              <p className="text-sm text-muted-foreground">{folder.description}</p>
              <div className="mt-3 h-2 max-w-sm overflow-hidden rounded-full bg-muted">
                <div
                  className={cn("h-full rounded-full", folder.complete ? "bg-emerald-500" : "bg-amber-500")}
                  style={{ width: `${(folder.ready / folder.total) * 100}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {folder.complete ? "Dossier complet" : `${folder.ready} pièce${folder.ready > 1 ? "s" : ""} prête${folder.ready > 1 ? "s" : ""} sur ${folder.total}`}
              </p>
            </div>
            <Button variant="outline" render={<a href={folderExportUrl(folder.key)} />} nativeButton={false}>
              <Download /> Exporter le dossier
            </Button>
          </div>
          <ul className="divide-y">
            {folder.pieces.map((p) => {
              const s = STATUS[p.status]
              const Icon = s.icon
              return (
                <li key={p.key} className="flex gap-3 px-5 py-3.5">
                  <Icon className={cn("mt-0.5 size-5 shrink-0", s.tone)} />
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-medium">
                      {p.label}
                      {p.optional && <span className="ml-2 text-xs font-normal text-muted-foreground">facultatif</span>}
                    </p>
                    {p.document_ids.length > 0 && (
                      <p className="mt-1 flex flex-wrap gap-1.5">
                        {p.document_ids.map((id) => (
                          <Link key={id} to={`/documents/${id}`} className="rounded-md border px-2 py-0.5 text-xs hover:bg-muted">
                            {titles.get(id) ?? `Document ${id}`}
                          </Link>
                        ))}
                      </p>
                    )}
                    {p.status !== "ok" && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {p.note && <span className={s.tone}>{p.note}. </span>}
                        {p.hint}
                      </p>
                    )}
                  </div>
                  <span className={cn("text-xs font-medium", s.tone)}>{s.label}</span>
                </li>
              )
            })}
          </ul>
        </Card>
      )}
    </>
  )
}
