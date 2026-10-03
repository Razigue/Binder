import { useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { CircleNotchIcon, FileTextIcon, InfoIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { CategoryIcon } from "@/components/CategoryIcon"
import { Glossed } from "@/components/glossary"
import { useInvalidateAll, useReport } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { api } from "@/lib/api"
import { AreaIcon } from "@/lib/areas"

/** What an import brought in: each document read, what Binder noticed, and its questions. */
export function ReportView({ batch, onNavigate }: { batch: string; onNavigate?: () => void }) {
  const t = useT(feed)
  const navigate = useNavigate()
  const invalidate = useInvalidateAll()
  const report = useReport(batch)
  const answer = useMutation({
    mutationFn: (p: { document_id: number; choice: string }) => api.act({ type: "answer", params: p }),
    // Refreshes the report too.
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  })
  const data = report.data
  if (!data)
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <CircleNotchIcon className="size-4 animate-spin" /> {t("reportAnalysing", { count: 1 })}
      </p>
    )
  const open = (id: number) => {
    onNavigate?.()
    navigate(`/documents/${id}`)
  }
  return (
    <div className="space-y-3">
      <p role="status" className="text-sm text-muted-foreground">
        {data.processing ? (
          <span className="flex items-center gap-2">
            <CircleNotchIcon className="size-4 animate-spin" /> {t("reportAnalysing", { count: data.processing })}
          </span>
        ) : (
          data.summary
        )}
      </p>
      <ul className="divide-y rounded-lg border">
        {data.items.map(({ document: d, brief, facts, events, question }) => (
          <li key={d.id} className="space-y-2 px-4 py-3">
            <div className="flex items-start gap-3">
              {d.area ? <AreaIcon area={d.area} size="sm" /> : <CategoryIcon category={d.category} size="sm" />}
              <div className="min-w-0 flex-1">
                <button type="button" onClick={() => open(d.id)} className="block max-w-full truncate text-left text-sm font-medium hover:underline">
                  {d.status === "processing" || d.status === "waiting" ? d.filename : d.title}
                </button>
                {d.status === "processing" ? (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CircleNotchIcon className="size-3 animate-spin" /> {t("reportAnalysing", { count: 1 })}
                  </p>
                ) : (
                  <>
                    {brief && (
                      <p className="mt-0.5 text-sm">
                        <Glossed text={brief} />
                      </p>
                    )}
                    <ul className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                      {facts.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                      {events.map((e) => (
                        <li key={e} className="flex items-start gap-1 text-foreground">
                          <InfoIcon className="mt-0.5 size-3 shrink-0 text-primary" /> {e}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
              <FileTextIcon className="hidden size-4 text-muted-foreground sm:block" />
            </div>
            {question && (
              <div className="ml-10 rounded-lg bg-amber-50/70 p-3 dark:bg-amber-500/10">
                <p className="text-sm font-medium">{question.title}</p>
                <p className="text-xs text-muted-foreground">{question.detail}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {question.choices.map((c) => (
                    <Button
                      key={c.id}
                      size="xs"
                      variant={c.primary ? "default" : "outline"}
                      disabled={answer.isPending}
                      onClick={() =>
                        c.id === "open" ? open(d.id) : answer.mutate({ document_id: d.id, choice: c.id })
                      }
                    >
                      {c.label}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
      {!data.items.length && <p className="text-sm text-muted-foreground">{t("reportEmpty")}</p>}
    </div>
  )
}
