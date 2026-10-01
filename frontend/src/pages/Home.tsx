import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { Archive, ArrowRight, TrendingUp, CalendarClock, ChevronRight, FileCheck2, FileClock, FlaskConical, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { PageHeader } from "@/components/layout/AppLayout"
import { useUpload } from "@/components/upload"
import {
  useDeadlines, useDocuments, useExpirations, useInvalidateAll, useRetention, useStats, useSubscriptions,
} from "@/hooks/queries"
import { useT } from "@/i18n"
import { common } from "@/i18n/messages/common"
import { home } from "@/i18n/messages/home"
import { api, type Category } from "@/lib/api"
import {
  categoryLabel, daysLabel, formatAmount, formatDate, formatNumber, missingLabel, toIso, urgency, urgencyStyles,
} from "@/lib/format"
import { cn } from "@/lib/utils"

export function HomePage() {
  const t = useT(home)
  const stats = useStats()
  const s = stats.data
  if (s && s.total_documents === 0) return <Welcome />
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="grid gap-3 sm:grid-cols-3 sm:gap-4">
        <StatCard
          icon={CalendarClock}
          value={s?.upcoming_deadlines}
          label={t("stat.deadlines")}
          hint={t("stat.deadlinesHint")}
          tone="red"
          to="/deadlines"
        />
        <StatCard
          icon={FileClock}
          value={s?.to_review}
          label={t("stat.toReview")}
          hint={t("stat.toReviewHint")}
          tone="amber"
          to="/documents?status=to_review"
        />
        <StatCard
          icon={FileCheck2}
          value={s?.classified_this_week}
          label={t("stat.classified")}
          hint={t("stat.classifiedHint")}
          to="/documents"
        />
      </div>
      <IncreaseHint />
      <SortingHint />
      <div className="mt-6 grid items-start gap-6 lg:grid-cols-2">
        <AttentionList />
        <RecentDocuments />
      </div>
      <ImportBar />
    </>
  )
}

// Only a non-zero count that calls for action gets a hue; the card itself stays neutral.
const TONES = {
  red: "text-red-600 dark:text-red-400",
  amber: "text-amber-600 dark:text-amber-400",
}

function StatCard({
  icon: Icon,
  value,
  label,
  hint,
  tone,
  to,
}: {
  icon: typeof CalendarClock
  value: number | undefined
  label: string
  hint: string
  tone?: keyof typeof TONES
  to: string
}) {
  return (
    // Phone: one compact row per figure, so the three of them do not fill the first screen.
    <Link
      to={to}
      className="flex items-center gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40 sm:block sm:p-5"
    >
      {value === undefined ? (
        <Skeleton className="h-9 w-10" />
      ) : (
        <span className={cn("min-w-11 text-3xl font-semibold tabular-nums sm:min-w-0", tone && value > 0 && TONES[tone])}>
          {value}
        </span>
      )}
      <div className="min-w-0 sm:mt-1">
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <Icon className="size-3.5 shrink-0 text-muted-foreground" /> {label}
        </p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
    </Link>
  )
}

function SectionCard({ title, to, children }: { title: string; to: string; children: React.ReactNode }) {
  const t = useT(common)
  return (
    <Card className="gap-0 p-0">
      <div className="flex items-center justify-between px-5 pt-4 pb-3">
        <h2 className="font-semibold">{title}</h2>
        <Link to={to} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          {t("action.seeAll")} <ArrowRight className="size-3" />
        </Link>
      </div>
      {children}
    </Card>
  )
}

interface AttentionItem {
  key: string
  to: string
  title: string
  category: Category
  reason: string
  reasonClass: string
  amount: number | null
}

function AttentionList() {
  const t = useT(home)
  const today = new Date()
  const inAWeek = new Date(today.getTime() + 7 * 86_400_000)
  const deadlines = useDeadlines({ end: toIso(inAWeek) })
  const toReview = useDocuments({ status: "to_review", limit: 5 })
  const expirations = useExpirations()

  const items: AttentionItem[] = [
    ...(expirations.data ?? [])
      .filter((e) => e.state !== "valid")
      .map((e) => ({
        key: `e${e.document.id}`,
        to: `/documents/${e.document.id}`,
        title: e.document.title,
        category: e.document.category,
        reason: e.state === "expired" ? t("expired") : t("renew", { count: e.days_left }),
        reasonClass: e.state === "expired" ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400",
        amount: null,
      })),
    ...(deadlines.data ?? []).map((d) => ({
      key: `d${d.id}`,
      to: d.document_id ? `/documents/${d.document_id}` : "/deadlines",
      title: d.title,
      category: d.category,
      reason: d.days_left < 0 ? daysLabel(d.days_left) : t("due", { when: daysLabel(d.days_left).toLowerCase() }),
      reasonClass: urgencyStyles[urgency(d.days_left)].text,
      amount: d.amount,
    })),
    ...(toReview.data ?? []).map((d) => ({
      key: `r${d.id}`,
      to: `/documents/${d.id}`,
      title: d.title || d.filename,
      category: d.category,
      reason: missingLabel(d.missing_fields),
      reasonClass: "text-amber-600 dark:text-amber-400",
      amount: d.amount,
    })),
  ].slice(0, 5)

  return (
    <SectionCard title={t("attention")} to="/documents?status=to_review">
      {deadlines.isPending || toReview.isPending ? (
        <ListSkeleton />
      ) : items.length === 0 ? (
        <p className="px-5 pb-6 text-sm text-muted-foreground">{t("attentionEmpty")}</p>
      ) : (
        <ul className="divide-y border-t">
          {items.map((it) => (
            <li key={it.key}>
              <Link to={it.to} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3 hover:bg-muted/40">
                <CategoryIcon category={it.category} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{it.title}</span>
                  <span className="block text-xs text-muted-foreground">{categoryLabel(it.category)}</span>
                </span>
                <span className="text-right">
                  <span className={cn("block text-xs font-medium", it.reasonClass)}>{it.reason}</span>
                  {it.amount !== null && (
                    <span className="block text-xs text-muted-foreground tabular-nums">{formatAmount(it.amount)}</span>
                  )}
                </span>
                <ChevronRight className="size-4 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}

const PERCENT: Intl.NumberFormatOptions = { style: "percent", maximumFractionDigits: 0, signDisplay: "always" }

function IncreaseHint() {
  const t = useT(home)
  const { data } = useSubscriptions()
  const rising = data?.filter((s) => s.increase) ?? []
  if (!rising.length) return null
  return (
    <Link
      to="/subscriptions"
      className="mt-4 flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50/60 px-5 py-3 text-sm hover:bg-amber-50 dark:border-border dark:bg-card dark:hover:bg-accent"
    >
      <TrendingUp className="size-4 text-amber-600 dark:text-amber-400" />
      <span className="flex-1">
        {t("increase", {
          list: rising
            .map((s) => `${s.label} (${formatNumber(s.change_pct / 100, PERCENT)})`)
            .join(", "),
        })}
      </span>
      <ArrowRight className="size-4 text-muted-foreground" />
    </Link>
  )
}

function SortingHint() {
  const t = useT(home)
  const { data } = useRetention()
  if (!data?.length) return null
  return (
    <Link to="/sorting" className="mt-4 flex items-center gap-3 rounded-xl border bg-card px-5 py-3 text-sm hover:bg-muted/40">
      <Archive className="size-4 text-muted-foreground" />
      <span className="flex-1">
        {t("sorting", { count: data.length })}
      </span>
      <ArrowRight className="size-4 text-muted-foreground" />
    </Link>
  )
}

function RecentDocuments() {
  const t = useT(home)
  const docs = useDocuments({ limit: 5 })
  return (
    <SectionCard title={t("recent")} to="/documents">
      {docs.isPending ? (
        <ListSkeleton />
      ) : (
        <ul className="divide-y border-t">
          {docs.data?.map((d) => (
            <li key={d.id}>
              <Link to={`/documents/${d.id}`} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3 hover:bg-muted/40">
                <CategoryIcon category={d.category} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{d.status === "processing" ? t("analysing") : d.title}</span>
                  <span className="block truncate text-xs text-muted-foreground">{categoryLabel(d.category)}</span>
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">{formatDate(d.issue_date ?? d.created_at, "day")}</span>
                <ChevronRight className="size-4 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}

function ImportBar() {
  const t = useT(home)
  const { uploadFiles, open } = useUpload()
  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        uploadFiles(e.dataTransfer.files)
      }}
      className="mt-6 flex flex-wrap items-center justify-center gap-6 rounded-xl border-2 border-dashed bg-card/60 px-6 py-6 sm:justify-between"
    >
      <div className="flex-1 text-center">
        <p className="flex items-center justify-center gap-2 text-sm font-medium">
          <Upload className="size-4" /> {t("dropHere")}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{t("dropHint")}</p>
      </div>
      <Button onClick={open}>{t("import")}</Button>
    </div>
  )
}

function ListSkeleton() {
  return (
    <div className="space-y-3 border-t p-5">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}

function Welcome() {
  const t = useT(home)
  const invalidate = useInvalidateAll()
  const demo = useMutation({ mutationFn: api.seedDemo, onSuccess: invalidate })
  return (
    <>
      <PageHeader title={t("welcome")} subtitle={t("welcomeSubtitle")} />
      <ImportBar />
      <div className="mt-6 flex flex-col items-center gap-3 text-center text-sm text-muted-foreground">
        <p>{t("noDocument")}</p>
        <Button variant="outline" onClick={() => demo.mutate()} disabled={demo.isPending}>
          <FlaskConical /> {demo.isPending ? t("demoLoading") : t("demo")}
        </Button>
      </div>
    </>
  )
}
