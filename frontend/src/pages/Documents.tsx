import { useSearchParams } from "react-router-dom"
import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { DocumentList } from "@/components/DocumentList"
import { PageHeader } from "@/components/layout/AppLayout"
import { ImportButton } from "@/components/upload"
import { useDocuments, useStats } from "@/hooks/queries"
import { useT } from "@/i18n"
import { documents } from "@/i18n/messages/documents"
import { CATEGORIES, exportUrl, type Category, type DocumentStatus } from "@/lib/api"
import { categoryLabel } from "@/lib/format"
import { cn } from "@/lib/utils"

const STATUS_TABS = [
  { value: undefined, label: "tab.all" },
  { value: "to_review", label: "tab.to_review" },
  { value: "classified", label: "tab.classified" },
] as const satisfies readonly { value: DocumentStatus | undefined; label: string }[]

export function DocumentsPage() {
  const t = useT(documents)
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
        title={t("title")}
        subtitle={stats.data ? t("count", { count: stats.data.total_documents }) : undefined}
        actions={<ImportButton />}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUS_TABS.map((tab) => (
          <Chip key={tab.label} active={status === tab.value} onClick={() => set("status", tab.value)}>
            {t(tab.label)}
          </Chip>
        ))}
        <span className="mx-2 h-5 w-px bg-border" />
        <Chip active={!category} onClick={() => set("category")}>
          {t("allCategories")}
        </Chip>
        {CATEGORIES.filter((c) => stats.data?.by_category[c]).map((c) => (
          <Chip key={c} active={category === c} onClick={() => set("category", c)}>
            {categoryLabel(c)} <span className="text-muted-foreground">{stats.data?.by_category[c]}</span>
          </Chip>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          render={<a href={exportUrl(category)} />}
          nativeButton={false}
        >
          <Download /> {category ? t("exportCategory", { category: categoryLabel(category) }) : t("exportAll")}
        </Button>
      </div>
      <Card className="gap-0 p-0">
        <DocumentList docs={docs.data} loading={docs.isPending} empty={t("empty")} />
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
