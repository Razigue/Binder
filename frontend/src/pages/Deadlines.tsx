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
import { api, type Deadline } from "@/lib/api"
import { daysLabel, formatAmount, formatDate, parseDate, toIso, urgency, urgencyStyles } from "@/lib/format"
import { cn } from "@/lib/utils"

export function DeadlinesPage() {
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
        title="Échéances"
        subtitle="Paiements et fins de validité, déduits de vos documents."
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
        <DeadlineSection title="En retard" deadlines={overdue.data} />
      )}
      <ExpirationSection />
      <DeadlineSection
        title="Prochaines échéances"
        deadlines={upcoming.data}
        loading={upcoming.isPending}
        empty="Aucune échéance à venir. Importez une facture ou un avis pour commencer."
      />
    </>
  )
}

const MONTH_FMT = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" })

function MonthTimeline({ month, onMonthChange }: { month: Date; onMonthChange: (d: Date) => void }) {
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0)
  const days = last.getDate()
  const { data = [] } = useDeadlines({ start: toIso(month), end: toIso(last), include_done: true })
  const today = new Date()
  const todayPos = today.getMonth() === month.getMonth() && today.getFullYear() === month.getFullYear()
    ? ((today.getDate() - 1) / (days - 1)) * 100
    : null
  const ticks = [1, 5, 10, 15, 20, 25, days]
  const shift = (n: number) => onMonthChange(new Date(month.getFullYear(), month.getMonth() + n, 1))
  const label = MONTH_FMT.format(month)

  return (
    <Card className="mb-6 gap-0 p-0">
      <div className="flex items-center justify-between px-5 pt-4">
        <h2 className="font-semibold first-letter:uppercase">{label}</h2>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon-sm" onClick={() => shift(-1)} aria-label="Mois précédent">
            <ChevronLeft />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => shift(1)} aria-label="Mois suivant">
            <ChevronRight />
          </Button>
        </div>
      </div>
      <div className="px-8 pt-6 pb-4">
        <div className="relative h-12">
          {ticks.map((t) => (
            <span
              key={t}
              className="absolute top-0 -translate-x-1/2 text-xs text-muted-foreground tabular-nums"
              style={{ left: `${((t - 1) / (days - 1)) * 100}%` }}
            >
              {String(t).padStart(2, "0")}
            </span>
          ))}
          <div className="absolute top-8 right-0 left-0 h-px bg-border" />
          {ticks.map((t) => (
            <span key={`t${t}`} className="absolute top-6 h-4 w-px bg-border" style={{ left: `${((t - 1) / (days - 1)) * 100}%` }} />
          ))}
          {todayPos !== null && (
            <span className="absolute top-5 h-6 w-0.5 rounded bg-primary/40" style={{ left: `${todayPos}%` }} title="Aujourd'hui" />
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
                <span className="truncate">{d.category === "Autre" ? d.title : d.category}</span>
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">{formatDate(d.due_date, "day")}</p>
              <p className={cn("text-xs font-medium", urgencyStyles[urgency(d.days_left)].text)}>{formatAmount(d.amount)}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="border-t px-5 py-4 text-sm text-muted-foreground">Aucune échéance ce mois-ci.</p>
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
  const toggle = useToggleDeadline()
  return (
    <section className="mb-6">
      <h2 className="mb-3 font-semibold">{title}</h2>
      <Card className="gap-0 p-0">
        {loading ? (
          <p className="p-5 text-sm text-muted-foreground">Chargement…</p>
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
                      {d.category}
                      {d.source === "manual" ? " · rappel" : ""}
                    </span>
                  </span>
                  <span className="hidden text-sm sm:block">
                    <span className="block">{formatDate(d.due_date, "day")}</span>
                    <span className="block text-xs text-muted-foreground">{formatAmount(d.amount)}</span>
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
                    aria-label={`Marquer « ${d.title} » comme réglée`}
                    onChange={() =>
                      toggle.mutate(
                        { id: d.id, done: true },
                        { onSuccess: () => toast.success(`« ${d.title} » marquée comme réglée`) },
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
      toast.success("Rappel créé")
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
        <BellPlus /> Ajouter un rappel
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Nouveau rappel</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="r-title">Intitulé</Label>
            <Input id="r-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Renouveler le passeport" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="r-date">Date</Label>
              <Input id="r-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="r-amount">Montant (optionnel)</Label>
              <Input id="r-amount" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!valid}>
              Créer le rappel
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
