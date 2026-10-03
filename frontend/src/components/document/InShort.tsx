import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowsClockwiseIcon, CheckIcon, CircleNotchIcon } from "@phosphor-icons/react"
import { Glossed } from "@/components/glossary"
import { queries } from "@/hooks/queries"
import { useT } from "@/i18n"
import { documentDetail } from "@/i18n/messages/documentDetail"
import { api, type DocDetail } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

/** The letter explained in plain words, and what needs doing. */
export function InShort({ doc }: { doc: DocDetail }) {
  const t = useT(documentDetail)
  const qc = useQueryClient()
  const explanation = queries.explanation(doc)
  const ex = useQuery(explanation)
  const refresh = useMutation({
    mutationFn: () => api.explanation(doc.id, true),
    onSuccess: (data) => qc.setQueryData(explanation.queryKey, data),
  })
  return (
    <div className="border-b px-5 py-4 text-sm">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="font-semibold">{t("inShort")}</h2>
        {ex.data &&
          (ex.data.action_required ? (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
              {t("actionRequired")}
            </span>
          ) : (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
              {t("nothingToDo")}
            </span>
          ))}
        {ex.data && (
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="ml-auto text-muted-foreground hover:text-foreground"
            aria-label={t("reexplain")}
            title={t("reexplain")}
          >
            <ArrowsClockwiseIcon className={cn("size-3.5", refresh.isPending && "animate-spin")} />
          </button>
        )}
      </div>
      {ex.isPending ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <CircleNotchIcon className="size-4 animate-spin" /> {t("readingLetter")}
        </p>
      ) : ex.isError ? (
        <p className="text-muted-foreground">{t("explanationUnavailable")}</p>
      ) : (
        <>
          <p className="leading-relaxed">
            <Glossed text={ex.data.summary} />
          </p>
          {ex.data.actions.length > 0 && (
            <ul className="mt-2 space-y-1">
              {ex.data.actions.map((a) => (
                <li key={a.label} className="flex items-start gap-2 font-medium">
                  <CheckIcon className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <span>
                    <Glossed text={a.label} />
                    {a.due_date && (
                      <span className="font-normal text-muted-foreground">{t("before", { date: formatDate(a.due_date) })}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {ex.data.key_points.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-muted-foreground">
              {ex.data.key_points.map((p) => (
                <li key={p}>
                  <Glossed text={p} />
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[0.6875rem] text-muted-foreground">
            {ex.data.engine === "llm" ? t("engine.llm") : t("engine.rules")}
          </p>
        </>
      )}
    </div>
  )
}
