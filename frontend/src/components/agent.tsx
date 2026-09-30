import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { ArrowUp, Bot, CalendarClock, ChevronRight, FileText, Loader2, Search, User } from "lucide-react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Input } from "@/components/ui/input"
import { useInvalidateAll } from "@/hooks/queries"
import { api, type ChatMessage, type ChatResponse } from "@/lib/api"
import { daysLabel, formatAmount, formatDate } from "@/lib/format"
import { CategoryIcon } from "./CategoryIcon"

const SUGGESTIONS = [
  "Quels documents arrivent bientôt ?",
  "Trouve mon dernier avis d'impôt",
  "Liste mes échéances d'octobre",
  "Quels documents sont à vérifier ?",
  "Trouve mes factures EDF",
]

interface Turn {
  question: string
  response?: ChatResponse
  error?: string
}

const AgentContext = createContext<{ open: (question?: string) => void } | null>(null)

export function useAgent() {
  const ctx = useContext(AgentContext)
  if (!ctx) throw new Error("useAgent hors de AgentProvider")
  return ctx
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const invalidate = useInvalidateAll()
  const chat = useMutation({
    mutationFn: ({ question, history }: { question: string; history: ChatMessage[] }) => api.chat(question, history),
  })

  const ask = (question: string) => {
    const q = question.trim()
    if (!q || chat.isPending) return
    const history: ChatMessage[] = turns.flatMap((t) =>
      t.response ? [{ role: "user", content: t.question }, { role: "assistant", content: t.response.answer }] : [],
    )
    const index = turns.length
    setTurns((prev) => [...prev, { question: q }])
    chat.mutate(
      { question: q, history },
      {
        onSuccess: (response) => {
          setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, response } : t)))
          if (response.tool_calls.some((c) => c.name === "create_reminder")) invalidate()
        },
        onError: (err) => setTurns((prev) => prev.map((t, i) => (i === index ? { ...t, error: err.message } : t))),
      },
    )
  }

  const open = (question?: string) => {
    setOpen(true)
    if (question) ask(question)
  }

  return (
    <AgentContext.Provider value={{ open }}>
      {children}
      <Sheet open={isOpen} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle className="flex items-center gap-2.5 text-lg">
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Bot className="size-4" />
              </span>
              Agent
            </SheetTitle>
            <SheetDescription className="sr-only">Posez une question sur vos documents.</SheetDescription>
          </SheetHeader>
          <AgentConversation turns={turns} pending={chat.isPending} onAsk={ask} onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
    </AgentContext.Provider>
  )
}

function AgentConversation({
  turns,
  pending,
  onAsk,
  onNavigate,
}: {
  turns: Turn[]
  pending: boolean
  onAsk: (q: string) => void
  onNavigate: () => void
}) {
  const [draft, setDraft] = useState("")
  const [search, setSearch] = useState("")
  const bottom = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" })
  }, [turns, pending])

  const submit = () => {
    onAsk(draft)
    setDraft("")
  }

  return (
    <>
      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        <div>
          <p className="mb-2 text-sm font-medium">Que voulez-vous faire ?</p>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (!search.trim()) return
              onNavigate()
              navigate(`/recherche?q=${encodeURIComponent(search.trim())}`)
            }}
            className="relative"
          >
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher dans mes documents…"
              className="h-10 pl-9"
            />
          </form>
        </div>

        {turns.length === 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">Suggestions</p>
            <div className="flex flex-col items-start gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => onAsk(s)}
                  className="inline-flex items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent"
                >
                  <FileText className="size-3.5 text-muted-foreground" /> {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className="space-y-4">
            <div className="flex gap-3">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted">
                <User className="size-3.5" />
              </span>
              <div>
                <p className="mb-1 text-xs font-medium">Vous</p>
                <p className="rounded-lg bg-accent px-3 py-2 text-sm">{turn.question}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Bot className="size-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="mb-1 text-xs font-medium">Agent</p>
                {turn.error ? (
                  <p className="text-sm text-destructive">{turn.error}</p>
                ) : turn.response ? (
                  <AgentAnswer response={turn.response} onNavigate={onNavigate} />
                ) : (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-3.5 animate-spin" /> Je cherche…
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        className="border-t p-4"
      >
        <div className="relative">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Écrivez votre demande…"
            className="h-11 pr-11"
            disabled={pending}
          />
          <button
            type="submit"
            disabled={pending || !draft.trim()}
            className="absolute top-1/2 right-2 flex size-7 -translate-y-1/2 items-center justify-center rounded-full bg-primary text-primary-foreground disabled:opacity-40"
            aria-label="Envoyer"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </form>
    </>
  )
}

/** Rendu minimal des liens markdown [texte](url) renvoyés par l'agent. */
function RichText({ text }: { text: string }) {
  const parts = text.split(/(\[[^\]]+\]\([^)]+\))/g)
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
        return m ? (
          <a key={i} href={m[2]} className="font-medium text-primary underline underline-offset-2">
            {m[1]}
          </a>
        ) : (
          <span key={i}>{part}</span>
        )
      })}
    </>
  )
}

function AgentAnswer({ response, onNavigate }: { response: ChatResponse; onNavigate: () => void }) {
  const [expanded, setExpanded] = useState(response.documents.length <= 3)
  const docs = response.documents
  return (
    <div className="space-y-3">
      <p className="text-sm leading-relaxed">
        <RichText text={response.answer} />
      </p>
      {docs.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          {!expanded ? (
            <button onClick={() => setExpanded(true)} className="flex w-full items-center gap-3 px-3 py-2.5 text-sm hover:bg-accent">
              <span className="flex size-7 items-center justify-center rounded-md bg-accent text-primary">
                <FileText className="size-3.5" />
              </span>
              <span className="flex-1 text-left font-medium">{docs.length} documents</span>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>
          ) : (
            <ul className="divide-y">
              {docs.map((d) => (
                <li key={d.id}>
                  <Link to={`/documents/${d.id}`} onClick={onNavigate} className="flex items-center gap-3 px-3 py-2 hover:bg-accent">
                    <CategoryIcon category={d.category} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{d.title}</span>
                      <span className="block text-xs text-muted-foreground">
                        {d.category} · {formatDate(d.issue_date)}
                      </span>
                    </span>
                    <span className="text-xs text-muted-foreground">{formatAmount(d.amount)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {response.deadlines.length > 0 && (
        <ul className="divide-y overflow-hidden rounded-lg border">
          {response.deadlines.map((d) => (
            <li key={d.id} className="flex items-center gap-3 px-3 py-2">
              <CalendarClock className="size-4 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{d.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {formatDate(d.due_date)} · {daysLabel(d.days_left)}
                </span>
              </span>
              <span className="text-xs text-muted-foreground">{formatAmount(d.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      {response.engine === "rules" && (
        <p className="text-[11px] text-muted-foreground">Réponse du mode hors IA (Ollama inactif).</p>
      )}
    </div>
  )
}
