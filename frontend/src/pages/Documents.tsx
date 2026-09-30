import { useSearchParams } from "react-router-dom"
import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { DocumentList } from "@/components/DocumentList"
import { PageHeader } from "@/components/layout/AppLayout"
import { ImportButton } from "@/components/upload"
import { useDocuments, useStats } from "@/hooks/queries"
import { CATEGORIES, exportUrl, type Category, type DocumentStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

const STATUS_TABS: { value: DocumentStatus | undefined; label: string }[] = [
  { value: undefined, label: "Tous" },
  { value: "to_review", label: "À vérifier" },
  { value: "classified", label: "Classés" },
]

export function DocumentsPage() {
  const [params, setParams] = useSearchParams()
  const category = (params.get("category") as Category | null) ?? undefined
  const status = (params.get("status") as DocumentStatus | null) ?? undefined
  const docs = useDocuments({ category, status, limit: 500 })
  const stats = useStats()

  const set = (key: string, value?: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        title="Documents"
        subtitle={
          stats.data
            ? `${stats.data.total_documents} document${stats.data.total_documents > 1 ? "s" : ""} dans votre coffre-fort`
            : undefined
        }
        actions={<ImportButton />}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUS_TABS.map((t) => (
          <Chip key={t.label} active={status === t.value} onClick={() => set("status", t.value)}>
            {t.label}
          </Chip>
        ))}
        <span className="mx-2 h-5 w-px bg-border" />
        <Chip active={!category} onClick={() => set("category")}>
          Toutes catégories
        </Chip>
        {CATEGORIES.filter((c) => stats.data?.by_category[c]).map((c) => (
          <Chip key={c} active={category === c} onClick={() => set("category", c)}>
            {c} <span className="text-muted-foreground">{stats.data?.by_category[c]}</span>
          </Chip>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          render={<a href={exportUrl(category)} />}
          nativeButton={false}
        >
          <Download /> Exporter {category ? `« ${category} »` : "le dossier"}
        </Button>
      </div>
      <Card className="gap-0 p-0">
        <DocumentList docs={docs.data} loading={docs.isPending} empty="Aucun document ne correspond à ces filtres." />
      </Card>
    </>
  )
}

export function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        active ? "border-primary bg-primary text-primary-foreground [&_span]:text-primary-foreground/70" : "bg-card hover:bg-accent",
      )}
    >
      {children}
    </button>
  )
}
