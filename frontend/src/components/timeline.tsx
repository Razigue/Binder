import { useLayoutEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Card } from "@/components/ui/card"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { useT } from "@/i18n"
import { timeline as messages } from "@/i18n/messages/timeline"
import { daysLabel, formatAmount, formatDate, formatDateTime, parseDate, toIso, urgency, urgencyStyles } from "@/lib/format"
import { cn } from "@/lib/utils"

type TimelineDeadline = {
  id: number
  title: string
  due_date: string
  amount: number | null
  days_left: number
  document_id: number | null
  done?: boolean
}

const DAY = 86_400_000
// Geometry in pixels: the label row, the axis, then same-place dots stacked below it.
const AXIS = 30
const DOT = 12
// 24px apart at least: each dot keeps a 24px target of its own (WCAG 2.5.8).
const STEP = 24
// Dots closer than this merge into one stack: a dot and its ring need that much room.
const GAP = 24
// Beyond this, a stack ends in a "+n" that lists the rest.
const STACK = 3
// Room a month name needs, so it never runs into "Today" or past the right edge.
const LABEL = 44

/** Deadlines on a rolling strip around today: what just passed, what is coming. */
export function Timeline({
  deadlines,
  back,
  ahead,
  loading,
}: {
  deadlines: TimelineDeadline[]
  back: number
  ahead: number
  loading?: boolean
}) {
  const t = useT(messages)
  const [strip, setStrip] = useState<HTMLDivElement | null>(null)
  const width = useWidth(strip)
  const [now] = useState(() => new Date())
  const span = back + ahead
  const start = useMemo(() => new Date(now.getFullYear(), now.getMonth(), now.getDate() - back), [now, back])
  const x = (day: number) => (day / span) * width
  const todayX = x(back)

  // Overdue deadlines older than the window sit on its left edge rather than vanish.
  const stacks = useMemo(() => {
    const placed = deadlines
      .map((d) => ({ d, day: offset(start, parseDate(d.due_date)) }))
      .filter((p) => p.day <= span)
      .map((p) => ({ d: p.d, at: (Math.max(0, p.day) / span) * width }))
      .sort((a, b) => a.at - b.at)
    const out: { at: number; items: TimelineDeadline[] }[] = []
    let first = -Infinity
    for (const p of placed) {
      const last = out[out.length - 1]
      if (last && p.at - first < GAP) {
        last.items.push(p.d)
        last.at = first + (p.at - first) / 2
      } else {
        first = p.at
        out.push({ at: p.at, items: [p.d] })
      }
    }
    return out
  }, [deadlines, start, span, width])

  const months = useMemo(() => {
    const out: { key: string; label: string; day: number }[] = []
    for (let m = new Date(start.getFullYear(), start.getMonth() + 1, 1); offset(start, m) <= span; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) {
      const options: Intl.DateTimeFormatOptions = m.getMonth() === 0 ? { month: "short", year: "numeric" } : { month: "short" }
      out.push({ key: toIso(m), label: formatDateTime(m.toISOString(), options), day: offset(start, m) })
    }
    return out
  }, [start, span])

  const mondays = useMemo(() => {
    const out: number[] = []
    for (let day = (8 - start.getDay()) % 7; day <= span; day += 7) out.push(day)
    return out
  }, [start, span])

  if (loading) {
    return (
      <Card className="gap-0 px-5 py-4">
        <Skeleton className="h-12 w-full" />
      </Card>
    )
  }
  const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + span)
  const tallest = Math.min(STACK, Math.max(1, ...stacks.map((s) => s.items.length)))
  const height = AXIS + DOT / 2 + (tallest - 1) * STEP + 10

  return (
    <Card className="gap-0 px-5 pt-4 pb-3">
      <TooltipProvider>
        <div
          ref={setStrip}
          role="group"
          aria-label={t("label", { start: formatDate(toIso(start)), end: formatDate(toIso(end)) })}
          className="relative"
          style={{ height }}
        >
          {width > 0 && (
            <>
              <span className="absolute h-px bg-border" style={{ top: AXIS, left: 0, width: todayX }} />
              <span className="absolute h-px bg-muted-foreground/35" style={{ top: AXIS, left: todayX, right: 0 }} />
              {mondays.map((day) => (
                <span key={day} className="absolute h-1 w-px bg-muted-foreground/30" style={{ top: AXIS - 4, left: x(day) }} />
              ))}
              {months.map((m) => {
                const at = x(m.day)
                const shown = Math.abs(at - todayX) > LABEL && at + LABEL < width
                return (
                  <span key={m.key} aria-hidden className="absolute" style={{ left: at, top: 0 }}>
                    {shown && (
                      <span className="absolute top-0 left-1 text-xs leading-4 whitespace-nowrap text-muted-foreground first-letter:uppercase">
                        {m.label}
                      </span>
                    )}
                    <span className="absolute w-px bg-muted-foreground/30" style={{ top: AXIS - 10, height: 10 }} />
                  </span>
                )
              })}
              <span
                className="absolute w-0.5 -translate-x-1/2 rounded-full bg-primary"
                style={{ left: todayX, top: 18, height: AXIS - 18 + DOT }}
              />
              <span
                aria-hidden
                className="absolute top-0 -translate-x-1/2 text-xs leading-4 font-medium whitespace-nowrap text-primary"
                style={{ left: todayX }}
              >
                {t("today")}
              </span>
              {stacks.map((s) => {
                const crowded = s.items.length > STACK
                const shown = crowded ? s.items.slice(0, STACK - 1) : s.items
                return (
                  <div
                    key={s.items[0]?.id ?? s.at}
                    className="absolute flex -translate-x-1/2 flex-col items-center"
                    style={{ left: s.at, top: AXIS - DOT / 2, gap: STEP - DOT }}
                  >
                    {shown.map((d) => (
                      <Dot key={d.id} deadline={d} />
                    ))}
                    {crowded && <More deadlines={s.items.slice(STACK - 1)} />}
                  </div>
                )
              })}
            </>
          )}
        </div>
      </TooltipProvider>
    </Card>
  )
}

function Dot({ deadline: d }: { deadline: TimelineDeadline }) {
  const t = useT(messages)
  const className = cn(
    "block size-3 shrink-0 rounded-full ring-4 ring-card outline-none hover:scale-125 focus-visible:scale-125 focus-visible:ring-ring motion-safe:transition-transform",
    d.done ? "bg-muted-foreground/40" : urgencyStyles[urgency(d.days_left)].dot,
  )
  const label = `${d.title} · ${formatDate(d.due_date)} · ${d.done ? t("done") : daysLabel(d.days_left)}`
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          d.document_id ? (
            <Link to={`/documents/${d.document_id}`} aria-label={label} className={className} />
          ) : (
            <button type="button" aria-label={label} className={className} />
          )
        }
      />
      <TooltipContent>
        <Summary deadline={d} />
      </TooltipContent>
    </Tooltip>
  )
}

/** The rest of a crowded stack, listed on click: hover alone would hide them from touch. */
function More({ deadlines }: { deadlines: TimelineDeadline[] }) {
  const t = useT(messages)
  return (
    <Popover>
      <PopoverTrigger
        aria-label={t("moreLabel", { count: deadlines.length })}
        className="flex h-4 min-w-5 items-center justify-center rounded-full bg-muted px-1 text-[0.625rem] leading-none font-medium text-muted-foreground tabular-nums ring-4 ring-card outline-none hover:bg-accent hover:text-foreground focus-visible:ring-ring data-popup-open:bg-accent data-popup-open:text-foreground"
      >
        {t("more", { count: deadlines.length })}
      </PopoverTrigger>
      <PopoverContent>
        <ul>
          {deadlines.map((d) => (
            <li key={d.id}>
              {d.document_id ? (
                <Link
                  to={`/documents/${d.document_id}`}
                  className="block rounded-md px-2.5 py-2 hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                >
                  <Summary deadline={d} />
                </Link>
              ) : (
                <div className="px-2.5 py-2">
                  <Summary deadline={d} />
                </div>
              )}
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

/** Title, then the urgency in words: the dot's colour is never the only signal. */
function Summary({ deadline: d }: { deadline: TimelineDeadline }) {
  const t = useT(messages)
  return (
    <span className="flex items-baseline gap-3">
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{d.title}</span>
        <span className="block text-xs text-muted-foreground">
          <span className={cn("font-medium", !d.done && urgencyStyles[urgency(d.days_left)].text)}>
            {d.done ? t("done") : daysLabel(d.days_left)}
          </span>
          {" · "}
          {formatDate(d.due_date)}
        </span>
      </span>
      {d.amount !== null && <span className="text-sm tabular-nums">{formatAmount(d.amount)}</span>}
    </span>
  )
}

/** Positions are in pixels so that stacking can tell when two dots would touch. */
function useWidth(el: HTMLElement | null) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    if (!el) return
    const observer = new ResizeObserver(([entry]) => entry && setWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [el])
  return width
}

function offset(start: Date, date: Date) {
  return Math.round((date.getTime() - start.getTime()) / DAY)
}
