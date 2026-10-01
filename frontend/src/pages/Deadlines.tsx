import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { BellPlus, ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { CategoryIcon } from "@/components/CategoryIcon"
import { ExpirationSection } from "@/components/Expirations"
import { PageHeader } from "@/components/layout/AppLayout"
import { useDeadlines, useInvalidateAll, useToggleDeadline } from "@/hooks/queries"
import { useT } from "@/i18n"
import { common } from "@/i18n/messages/common"
import { deadlines as messages } from "@/i18n/messages/deadlines"
import { api, type Deadline } from "@/lib/api"
import {
  categoryLabel, daysLabel, formatAmount, formatDate, formatDateTime, parseDate, toIso, urgency, urgencyStyles,
} from "@/lib/format"
import { cn } from "@/lib/utils"

export function DeadlinesPage() {
  const t = useT(messages)
  const now = new Date()
  const [month, setMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1))
  const upcoming = useDeadlines({ start: toIso(now) })
  const overdue = useDeadlines({ end: toIso(new Date(now.getTime() - 86_400_000)) })
  const next = upcoming.data?.[0]
  const [autoMonth, setAutoMonth] = useState(true)

  useEffect(() => {
    if (!autoMonth || !next) return
    const d = parseDate(next.due_date)
    setMonth(new Date(d.getFullYear(), d.getMonth(), 1))
    setAutoMonth(false)
  }, [autoMonth, next])

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={<ReminderDialog />}
      />
      <MonthTimeline
        month={month}
        onMonthChange={(m) => {
          setAutoMonth(false)
          setMonth(m)
        }}
      />
      {!!overdue.data?.length && (
        <DeadlineSection title={t("overdue")} deadlines={overdue.data} />
      )}
      <ExpirationSection />
      <DeadlineSection
        title={t("upcoming")}
        deadlines={upcoming.data}
        loading={upcoming.isPending}
        empty={t("upcomingEmpty")}
      />
    </>
  )
}

function MonthTimeline({ month, onMonthChange }: { month: Date; onMonthChange: (d: Date) => void }) {
  const t = useT(messages)
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0)
  const days = last.getDate()
  const { data = [] } = useDeadlines({ start: toIso(month), end: toIso(last), include_done: true })
  const today = new Date()
  const todayPos = today.getMonth() === month.getMonth() && today.getFullYear() === month.getFullYear()
    ? ((today.getDate() - 1) / (days - 1)) * 100
    : null
  const ticks = [1, 5, 10, 15, 20, 25, days]
  const shift = (n: number) => onMonthChange(new Date(month.getFullYear(), month.getMonth() + n, 1))
  const label = formatDateTime(month.toISOString(), { month: "long", year: "numeric" })

  return (
    <Card className="mb-6 gap-0 p-0">
      <div className="flex items-center justify-between px-5 pt-4">
        <h2 className="font-semibold first-letter:uppercase">{label}</h2>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon-sm" onClick={() => shift(-1)} aria-label={t("previousMonth")}>
            <ChevronLeft />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => shift(1)} aria-label={t("nextMonth")}>
            <ChevronRight />
          </Button>
        </div>
      </div>
      <div className="px-8 pt-6 pb-4">
        <div className="relative h-12">
          {ticks.map((tick) => (
            <span
              key={tick}
              className="absolute top-0 -translate-x-1/2 text-xs text-muted-foreground tabular-nums"
              style={{ left: `${((tick - 1) / (days - 1)) * 100}%` }}
            >
              {String(tick).padStart(2, "0")}
            </span>
          ))}
          <div className="absolute top-8 right-0 left-0 h-px bg-border" />
          {ticks.map((tick) => (
            <span
              key={`t${tick}`}
              className="absolute top-6 h-4 w-px bg-border"
              style={{ left: `${((tick - 1) / (days - 1)) * 100}%` }}
            />
          ))}
          {todayPos !== null && (
            <span className="absolute top-5 h-6 w-0.5 rounded bg-primary/40" style={{ left: `${todayPos}%` }} title={t("today")} />
          )}
          {data.map((d) => {
            const day = parseDate(d.due_date).getDate()
            return (
              <span
                key={d.id}
                title={`${d.title} · ${formatDate(d.due_date)}`}
                className={cn(
                  "absolute top-8 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-4 ring-card",
                  d.done ? "bg-muted-foreground/40" : urgencyStyles[urgency(d.days_left)].dot,
                )}
                style={{ left: `${((day - 1) / (days - 1)) * 100}%` }}
              />
            )
          })}
        </div>
      </div>
      {data.length > 0 ? (
        <div className="grid grid-cols-2 overflow-hidden border-t sm:grid-cols-3 lg:grid-cols-4">
          {data.map((d) => (
            <div key={d.id} className={cn("-mb-px border-r border-b px-5 py-3", d.done && "opacity-50")}>
              <p className="flex items-center gap-2 text-sm font-medium">
                <span className={cn("size-2 rounded-full", urgencyStyles[urgency(d.days_left)].dot)} />
                <span className="truncate">{d.category === "other" ? d.title : categoryLabel(d.category)}</span>
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">{formatDate(d.due_date, "day")}</p>
              {d.amount !== null && (
                <p className={cn("text-xs font-medium tabular-nums", urgencyStyles[urgency(d.days_left)].text)}>{formatAmount(d.amount)}</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="border-t px-5 py-4 text-sm text-muted-foreground">{t("monthEmpty")}</p>
      )}
    </Card>
  )
}

function DeadlineSection({
  title,
  deadlines,
  loading,
  empty,
}: {
  title: string
  deadlines?: Deadline[]
  loading?: boolean
  empty?: string
}) {
  const t = useT(messages)
  const tc = useT(common)
  const toggle = useToggleDeadline()
  return (
    <section className="mb-6">
      <h2 className="mb-3 font-semibold">{title}</h2>
      <Card className="gap-0 p-0">
        {loading ? (
          <p className="p-5 text-sm text-muted-foreground">{tc("state.loading")}</p>
        ) : !deadlines?.length ? (
          <p className="p-5 text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul className="divide-y">
            {deadlines.map((d) => {
              const u = urgencyStyles[urgency(d.days_left)]
              const content = (
                <>
                  <CategoryIcon category={d.category} />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{d.title}</span>
                    <span className="block text-xs text-muted-foreground">
                      {categoryLabel(d.category)}
                      {d.source === "manual" ? ` · ${t("reminder")}` : ""}
                    </span>
                  </span>
                  <span className="hidden text-sm tabular-nums sm:block">
                    <span className="block">{formatDate(d.due_date, "day")}</span>
                    {d.amount !== null && <span className="block text-xs text-muted-foreground">{formatAmount(d.amount)}</span>}
                  </span>
                  <span className={cn("rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap", u.pill)}>
                    {daysLabel(d.days_left)}
                  </span>
                </>
              )
              return (
                <li key={d.id} className="flex items-center gap-3 pl-5">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    aria-label={t("markPaid", { title: d.title })}
                    onChange={() =>
                      toggle.mutate(
                        { id: d.id, done: true },
                        { onSuccess: () => toast.success(t("markedPaid", { title: d.title })) },
                      )
                    }
                  />
                  {d.document_id ? (
                    <Link to={`/documents/${d.document_id}`} className={rowClass}>
                      {content}
                      <ChevronRight className="size-4 text-muted-foreground" />
                    </Link>
                  ) : (
                    <div className={rowClass}>
                      {content}
                      <span className="size-4" />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </section>
  )
}

const rowClass =
  "grid flex-1 grid-cols-[auto_1fr_auto_auto] items-center gap-4 py-3 pr-5 hover:bg-muted/40 sm:grid-cols-[auto_1fr_120px_auto_auto]"

function ReminderDialog() {
  const t = useT(messages)
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [date, setDate] = useState("")
  const [amount, setAmount] = useState("")
  const invalidate = useInvalidateAll()
  const valid = useMemo(() => title.trim() && date, [title, date])

  const submit = async () => {
    if (!valid) return
    try {
      await api.createDeadline({ title: title.trim(), due_date: date, amount: amount ? Number(amount) : null })
      invalidate()
      toast.success(t("reminderCreated"))
      setOpen(false)
      setTitle("")
      setDate("")
      setAmount("")
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" />}>
        <BellPlus /> {t("addReminder")}
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("newReminder")}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="r-title">{t("reminderTitle")}</Label>
            <Input id="r-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("reminderPlaceholder")} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="r-date">{t("date")}</Label>
              <Input id="r-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-amount">{t("amountOptional")}</Label>
              <Input id="r-amount" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!valid}>
              {t("createReminder")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
