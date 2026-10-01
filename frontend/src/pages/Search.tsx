import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { Bot, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useAgent } from "@/components/agent"
import { DocumentList } from "@/components/DocumentList"
import { PageHeader } from "@/components/layout/AppLayout"
import { useDocuments } from "@/hooks/queries"
import { useT } from "@/i18n"
import { search } from "@/i18n/messages/search"

export function SearchPage() {
  const t = useT(search)
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const [draft, setDraft] = useState(q)
  const agent = useAgent()
  const results = useDocuments({ q, limit: 100 })

  useEffect(() => {
    setDraft(q)
  }, [q])

  // Search as you type, with a short debounce.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (draft !== q) setParams(draft ? { q: draft } : {}, { replace: true })
    }, 250)
    return () => clearTimeout(timer)
  }, [draft, q, setParams])

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="relative mb-4">
        <Search className="absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("placeholder")}
          aria-label={t("title")}
          className="h-12 bg-card pl-12 text-base"
        />
      </div>
      {q && (
        <div className="mb-3 flex items-center justify-between text-sm text-muted-foreground">
          <span>{results.data ? t("results", { count: results.data.length }) : t("searching")}</span>
          <Button variant="ghost" size="sm" onClick={() => agent.open(q)}>
            <Bot /> {t("askAgent")}
          </Button>
        </div>
      )}
      {q ? (
        <Card className="gap-0 p-0">
          <DocumentList docs={results.data} loading={results.isPending} empty={t("empty", { q })} />
        </Card>
      ) : (
        <p className="py-16 text-center text-sm text-muted-foreground">{t("hint")}</p>
      )}
    </>
  )
}
