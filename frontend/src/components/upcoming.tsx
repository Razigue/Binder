import { Link } from "react-router-dom"
import { ClockCountdownIcon } from "@phosphor-icons/react"
import { Card } from "@/components/ui/card"
import { useT } from "@/i18n"
import { area as messages } from "@/i18n/messages/area"
import { daysLabel, formatAmount, formatDate, urgency, urgencyStyles } from "@/lib/format"
import { cn } from "@/lib/utils"

type UpcomingDeadline = { id: number; title: string; due_date: string; amount: number | null; days_left: number; document_id: number | null }

/** Deadlines to come, nearest first; each opens the document it comes from. */
export function Upcoming({ deadlines, empty }: { deadlines: UpcomingDeadline[]; empty?: string }) {
  const t = useT(messages)
  return (
    <Card className="gap-0 p-0">
      <h2 className="px-5 pt-4 pb-3 font-semibold">{t("upcoming")}</h2>
      {deadlines.length === 0 ? (
        <p className="border-t px-5 py-4 text-sm text-muted-foreground">{empty ?? t("noUpcoming")}</p>
      ) : (
        <ul className="divide-y border-t">
          {deadlines.map((d) => {
            const row = (
              <>
                <ClockCountdownIcon className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{d.title}</span>
                  <span className={cn("block text-xs", urgencyStyles[urgency(d.days_left)].text)}>
                    {formatDate(d.due_date)} · {daysLabel(d.days_left)}
                  </span>
                </span>
                <span className="text-sm tabular-nums">{formatAmount(d.amount)}</span>
              </>
            )
            return (
              <li key={d.id}>
                {d.document_id ? (
                  <Link to={`/documents/${d.document_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/40">
                    {row}
                  </Link>
                ) : (
                  <div className="flex items-center gap-3 px-5 py-3">{row}</div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
