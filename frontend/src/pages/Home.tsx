import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { ArrowRight, CalendarClock, ChevronRight, FileCheck2, FileClock, Sparkles, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryIcon } from "@/components/CategoryIcon"
import { PageHeader } from "@/components/layout/AppLayout"
import { useUpload } from "@/components/upload"
import { useDeadlines, useDocuments, useInvalidateAll, useStats } from "@/hooks/queries"
import { api, type Category } from "@/lib/api"
import { daysLabel, formatAmount, formatDate, missingLabel, toIso, urgency, urgencyStyles } from "@/lib/format"
import { cn } from "@/lib/utils"

export function HomePage() {
  const stats = useStats()
  const s = stats.data
  if (s && s.total_documents === 0) return <Welcome />
  return (
    <>
      <PageHeader title="Bonjour !" subtitle="Voici ce qui nécessite votre attention aujourd'hui." />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          icon={CalendarClock}
          value={s?.upcoming_deadlines}
          label="Échéances à venir"
          hint="Dans les 30 prochains jours"
          tone="red"
          to="/echeances"
        />
        <StatCard
          icon={FileClock}
          value={s?.to_review}
          label="Documents à vérifier"
          hint="Informations manquantes"
          tone="amber"
          to="/documents?status=to_review"
        />
        <StatCard
          icon={FileCheck2}
          value={s?.classified_this_week}
          label="Documents classés"
          hint="Cette semaine"
          tone="emerald"
          to="/documents"
        />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <AttentionList />
        <RecentDocuments />
      </div>
      <ImportBar />
    </>
  )
}

const TONES = {
  red: "border-red-100 bg-red-50/60 [&_.icon]:bg-red-100 [&_.icon]:text-red-500 [&_.hint]:text-red-500/80",
  amber: "border-amber-100 bg-amber-50/60 [&_.icon]:bg-amber-100 [&_.icon]:text-amber-600 [&_.hint]:text-amber-600/80",
  emerald: "border-emerald-100 bg-emerald-50/60 [&_.icon]:bg-emerald-100 [&_.icon]:text-emerald-600 [&_.hint]:text-emerald-600/80",
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
  tone: keyof typeof TONES
  to: string
}) {
  return (
    <Link to={to} className={cn("rounded-xl border p-5 transition-shadow hover:shadow-sm", TONES[tone])}>
      <div className="flex items-center gap-3">
        <span className="icon flex size-9 items-center justify-center rounded-lg">
          <Icon className="size-4" />
        </span>
        {value === undefined ? <Skeleton className="h-8 w-8" /> : <span className="text-3xl font-semibold">{value}</span>}
      </div>
      <p className="mt-2 text-sm font-medium">{label}</p>
      <p className="hint text-xs">{hint}</p>
    </Link>
  )
}

function SectionCard({ title, to, children }: { title: string; to: string; children: React.ReactNode }) {
  return (
    <Card className="gap-0 p-0">
      <div className="flex items-center justify-between px-5 pt-4 pb-3">
        <h2 className="font-semibold">{title}</h2>
        <Link to={to} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          Voir tout <ArrowRight className="size-3" />
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
  const today = new Date()
  const inAWeek = new Date(today.getTime() + 7 * 86_400_000)
  const deadlines = useDeadlines({ end: toIso(inAWeek) })
  const toReview = useDocuments({ status: "to_review", limit: 5 })

  const items: AttentionItem[] = [
    ...(deadlines.data ?? []).map((d) => ({
      key: `d${d.id}`,
      to: d.document_id ? `/documents/${d.document_id}` : "/echeances",
      title: d.title,
      category: d.category,
      reason: d.days_left < 0 ? daysLabel(d.days_left) : `Échéance ${daysLabel(d.days_left).toLowerCase()}`,
      reasonClass: urgencyStyles[urgency(d.days_left)].text,
      amount: d.amount,
    })),
    ...(toReview.data ?? []).map((d) => ({
      key: `r${d.id}`,
      to: `/documents/${d.id}`,
      title: d.title || d.filename,
      category: d.category,
      reason: missingLabel(d.missing_fields),
      reasonClass: "text-amber-600",
      amount: d.amount,
    })),
  ].slice(0, 4)

  return (
    <SectionCard title="À vérifier" to="/documents?status=to_review">
      {deadlines.isPending || toReview.isPending ? (
        <ListSkeleton />
      ) : items.length === 0 ? (
        <p className="px-5 pb-6 text-sm text-muted-foreground">Rien d'urgent. Tout est en ordre.</p>
      ) : (
        <ul className="divide-y border-t">
          {items.map((it) => (
            <li key={it.key}>
              <Link to={it.to} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3 hover:bg-muted/40">
                <CategoryIcon category={it.category} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{it.title}</span>
                  <span className="block text-xs text-muted-foreground">{it.category}</span>
                </span>
                <span className="text-right">
                  <span className={cn("block text-xs font-medium", it.reasonClass)}>{it.reason}</span>
                  <span className="block text-xs text-muted-foreground">{formatAmount(it.amount)}</span>
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

function RecentDocuments() {
  const docs = useDocuments({ limit: 4 })
  return (
    <SectionCard title="Documents récents" to="/documents">
      {docs.isPending ? (
        <ListSkeleton />
      ) : (
        <div className="grid gap-3 border-t p-4 sm:grid-cols-2">
          {docs.data?.map((d) => (
            <Link key={d.id} to={`/documents/${d.id}`} className="flex gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40">
              <CategoryIcon category={d.category} />
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{d.status === "processing" ? "Analyse…" : d.title}</span>
                <span className="block text-xs text-muted-foreground">{d.category}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{formatDate(d.issue_date ?? d.created_at, "day")}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </SectionCard>
  )
}

function ImportBar() {
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
          <Upload className="size-4" /> Déposez vos documents ici
        </p>
        <p className="mt-1 text-xs text-muted-foreground">PDF, JPG, PNG · Ils restent sur votre machine.</p>
      </div>
      <Button onClick={open}>+ Importer</Button>
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
  const invalidate = useInvalidateAll()
  const demo = useMutation({ mutationFn: api.seedDemo, onSuccess: invalidate })
  return (
    <>
      <PageHeader title="Bienvenue dans votre coffre-fort" subtitle="Tout est analysé et chiffré sur votre machine." />
      <ImportBar />
      <div className="mt-6 flex flex-col items-center gap-3 text-center text-sm text-muted-foreground">
        <p>Pas de document sous la main ?</p>
        <Button variant="outline" onClick={() => demo.mutate()} disabled={demo.isPending}>
          <Sparkles /> {demo.isPending ? "Import en cours…" : "Charger des documents de démonstration"}
        </Button>
      </div>
    </>
  )
}
