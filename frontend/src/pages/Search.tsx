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

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const [draft, setDraft] = useState(q)
  const agent = useAgent()
  const results = useDocuments({ q, limit: 100 })

  useEffect(() => {
    setDraft(q)
  }, [q])

  // Recherche au fil de la frappe, avec un léger délai.
  useEffect(() => {
    const t = setTimeout(() => {
      if (draft !== q) setParams(draft ? { q: draft } : {}, { replace: true })
    }, 250)
    return () => clearTimeout(t)
  }, [draft, q, setParams])

  return (
    <>
      <PageHeader title="Recherche" subtitle="Dans le texte, les titres, émetteurs et références de vos documents." />
      <div className="relative mb-4">
        <Search className="absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ex. taxe foncière, EDF, numéro fiscal…"
          className="h-12 bg-card pl-12 text-base"
        />
      </div>
      {q && (
        <div className="mb-3 flex items-center justify-between text-sm text-muted-foreground">
          <span>{results.data ? `${results.data.length} résultat${results.data.length > 1 ? "s" : ""}` : "Recherche…"}</span>
          <Button variant="ghost" size="sm" onClick={() => agent.open(q)}>
            <Bot /> Demander à l'agent
          </Button>
        </div>
      )}
      {q ? (
        <Card className="gap-0 p-0">
          <DocumentList docs={results.data} loading={results.isPending} empty={`Aucun document ne contient « ${q} ».`} />
        </Card>
      ) : (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Tapez un mot-clé. La recherche ignore les accents et trouve les mots partiels.
        </p>
      )}
    </>
  )
}
