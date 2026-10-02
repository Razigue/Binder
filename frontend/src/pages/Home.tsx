import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowUpIcon, VaultIcon, RobotIcon, CheckCircleIcon, FlaskIcon, CircleNotchIcon, PaperclipIcon, ArrowCounterClockwiseIcon, UploadSimpleIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { useAgent } from "@/components/agent"
import { FeedCard } from "@/components/feed"
import { Ongoing } from "@/components/ongoing"
import { Timeline } from "@/components/timeline"
import { Upcoming } from "@/components/upcoming"
import { PageHeader } from "@/components/layout/AppLayout"
import { usePanels } from "@/components/panels"
import { useUpload } from "@/components/upload"
import { useDeadlines, useFeed, useInvalidateAll, useProfile } from "@/hooks/queries"
import { useT } from "@/i18n"
import { today } from "@/i18n/messages/today"
import { api, type FeedItem, type SetupStatus } from "@/lib/api"
import { formatSize, formatDate, toIso } from "@/lib/format"

const BACK = 14
const AHEAD = 60

export function HomePage() {
  const t = useT(today)
  const feed = useFeed()
  const data = feed.data
  const [day] = useState(() => new Date())
  // The timeline looks two weeks back, paid ones included; "Coming up" only ahead.
  const horizon = useMemo(
    () => ({
      start: toIso(new Date(day.getTime() - BACK * 86_400_000)),
      end: toIso(new Date(day.getTime() + AHEAD * 86_400_000)),
      include_done: true,
    }),
    [day],
  )
  const deadlines = useDeadlines(horizon)
  const greeting = useGreeting(day)
  if (data && data.documents === 0 && !data.items.some((i) => i.kind === "report")) return <Welcome setup={data.setup} />
  const items = data?.items ?? []
  // What to do, what Binder asks, what is merely worth knowing: three different gestures.
  const questions = items.filter((i) => i.kind === "question")
  const toDo = items.filter((i) => i.kind !== "question" && i.tone !== "info")
  const later = items.filter((i) => i.kind !== "question" && i.tone === "info")
  const attention = toDo.length + questions.length
  const summary = attention ? t("summary", { count: attention }) : t("summaryNone")
  return (
    <>
      <PageHeader title={greeting} subtitle={data ? `${formatDate(toIso(day), "long")} · ${summary}` : formatDate(toIso(day), "long")} />
      {data && <SetupCard setup={data.setup} />}
      <AskCard />
      {!data ? (
        <Card className="gap-3 p-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </Card>
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]">
          <div className="min-w-0 space-y-8">
            <Timeline deadlines={deadlines.data ?? []} back={BACK} ahead={AHEAD} loading={deadlines.isPending} />
            {attention === 0 && (
              <div className="flex items-start gap-3 rounded-xl bg-card p-5 ring-1 ring-foreground/10">
                <CheckCircleIcon className="mt-0.5 size-5 text-emerald-600 dark:text-emerald-400" />
                <div>
                  <p className="font-medium">{t("allGood")}</p>
                  <p className="text-sm text-muted-foreground">{t("allGoodHint")}</p>
                </div>
              </div>
            )}
            {toDo.length > 0 && (
              <Section title={t("toDo")} count={toDo.length}>
                <FeedList items={toDo} />
              </Section>
            )}
            {questions.length > 0 && (
              <Section title={t("questions")} hint={t("questionsHint")} count={questions.length}>
                <FeedList items={questions} />
              </Section>
            )}
            {later.length > 0 && (
              <Section title={t("later")}>
                <FeedList items={later} />
              </Section>
            )}
            <DropBar />
          </div>
          <aside className="grid items-start gap-6 md:grid-cols-2 xl:grid-cols-1">
            <Ongoing limit={4} />
            <Upcoming deadlines={(deadlines.data ?? []).filter((d) => !d.done && d.days_left >= 0).slice(0, 6)} empty={t("upcomingEmpty")} />
          </aside>
        </div>
      )}
    </>
  )
}

/** "Hello Camille": the first name from the profile, when it looks like one. */
function useGreeting(now: Date) {
  const t = useT(today)
  const name = useProfile().data?.name.trim() ?? ""
  const first = name.split(/\s+/)[0] ?? ""
  // "M. MARTIN Camille" or "MARTIN" would make an odd greeting: stay plain then.
  const usable = /\p{Ll}/u.test(first) && !first.endsWith(".")
  const evening = now.getHours() >= 18
  if (!usable) return evening ? t("evening") : t("hello")
  return evening ? t("eveningName", { name: first }) : t("helloName", { name: first })
}

function Section({ title, hint, count, children }: { title: string; hint?: string; count?: number; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-3">
        <h2 className="font-semibold">
          {title}
          {count !== undefined && <span className="ml-2 font-normal text-muted-foreground tabular-nums">{count}</span>}
        </h2>
        {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </section>
  )
}

const EXAMPLES = ["upcoming", "alerts", "letter"] as const

/** The agent at the top of Today: ask or delegate in a sentence, or start from an example. */
function AskCard() {
  const t = useT(today)
  const agent = useAgent()
  const upload = useUpload()
  const [text, setText] = useState("")
  return (
    <Card className="mb-8 gap-3 p-4 sm:p-5">
      <p className="flex items-center gap-2 font-semibold">
        <RobotIcon className="size-4 text-primary" /> {t("askTitle")}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          agent.open(text.trim() || undefined)
          setText("")
        }}
        className="flex items-center gap-2 rounded-xl border bg-background p-1.5 pl-2 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/30"
      >
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={upload.open}
          aria-label={t("attach")}
          title={t("attach")}
          className="text-muted-foreground"
        >
          <PaperclipIcon />
        </Button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("askPlaceholder")}
          aria-label={t("askTitle")}
          className="h-10 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground md:text-sm"
        />
        <Button type="submit" size="icon" aria-label={t("send")} title={t("send")}>
          <ArrowUpIcon />
        </Button>
      </form>
      <div className="flex flex-wrap items-center gap-2">
        {EXAMPLES.map((key) => (
          <button
            key={key}
            onClick={() => agent.open(t(`example.${key}`))}
            className="rounded-lg border bg-card px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent"
          >
            {t(`example.${key}`)}
          </button>
        ))}
        <Link to="/prepare" className="px-1 text-sm font-medium text-primary hover:underline">
          {t("everything")}
        </Link>
      </div>
    </Card>
  )
}

function FeedList({ items }: { items: FeedItem[] }) {
  return (
    <Card className="gap-0 p-0">
      <ul className="divide-y">
        {items.map((item) => (
          <FeedCard key={item.key} item={item} />
        ))}
      </ul>
    </Card>
  )
}

/** The local AI installing itself: shown until it is ready, never asks anything. */
function SetupCard({ setup }: { setup: SetupStatus }) {
  const t = useT(today)
  const invalidate = useInvalidateAll()
  const retry = useMutation({ mutationFn: api.retrySetup, onSuccess: invalidate })
  if (setup.phase === "ready" && setup.warning) {
    return (
      <Card className="mb-6 flex-row items-start gap-3 p-5">
        <VaultIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{setup.warning}</p>
      </Card>
    )
  }
  if (setup.phase === "ready" || setup.phase === "disabled") return null
  const error = setup.phase === "error"
  const ratio = setup.total ? Math.min(100, (setup.completed / setup.total) * 100) : null
  return (
    <Card className="mb-6 gap-3 p-5">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          {error ? <VaultIcon className="size-4" /> : <CircleNotchIcon className="size-4 animate-spin" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{t(`setup.${setup.phase}`)}</p>
          <p className="text-sm text-muted-foreground">{error ? setup.error || t("setup.errorHint") : t("setup.hint")}</p>
        </div>
        {error && (
          <Button variant="outline" size="sm" onClick={() => retry.mutate()} disabled={retry.isPending}>
            <ArrowCounterClockwiseIcon /> {t("setup.retry")}
          </Button>
        )}
      </div>
      {!error && ratio !== null && (
        <div className="space-y-1">
          <Progress value={ratio} />
          <p className="text-xs text-muted-foreground tabular-nums">
            {t("setup.progress", { done: formatSize(setup.completed), total: formatSize(setup.total) })}
          </p>
        </div>
      )}
      {error && <p className="text-xs text-muted-foreground">{t("setup.errorHint")}</p>}
    </Card>
  )
}

function DropBar() {
  const t = useT(today)
  const { uploadFiles, open } = useUpload()
  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        uploadFiles(e.dataTransfer.files)
      }}
      className="flex flex-wrap items-center justify-center gap-6 rounded-xl border-2 border-dashed bg-card/60 px-6 py-6 sm:justify-between"
    >
      <div className="flex-1 text-center">
        <p className="flex items-center justify-center gap-2 text-sm font-medium">
          <UploadSimpleIcon className="size-4" /> {t("dropHere")}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{t("dropHint")}</p>
      </div>
      <Button onClick={open}>{t("import")}</Button>
    </div>
  )
}

function Welcome({ setup }: { setup: SetupStatus }) {
  const t = useT(today)
  const invalidate = useInvalidateAll()
  const panels = usePanels()
  const [restoring, setRestoring] = useState(false)
  const demo = useMutation({
    mutationFn: api.seedDemo,
    onSuccess: (r) => {
      invalidate()
      if (r.batch) panels.showReport(r.batch)
    },
  })
  return (
    <>
      <PageHeader title={t("welcome")} subtitle={t("welcomeSubtitle")} />
      <SetupCard setup={setup} />
      <DropBar />
      <div className="mt-6 flex flex-col items-center gap-3 text-center text-sm text-muted-foreground">
        <p>{t("noDocument")}</p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="outline" onClick={() => demo.mutate()} disabled={demo.isPending}>
            <FlaskIcon /> {demo.isPending ? t("demoLoading") : t("demo")}
          </Button>
          <Button variant="ghost" onClick={() => setRestoring(true)}>
            <ArrowCounterClockwiseIcon /> {t("restore")}
          </Button>
        </div>
      </div>
      <RestoreDialog open={restoring} onOpenChange={setRestoring} />
    </>
  )
}

function RestoreDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT(today)
  const invalidate = useInvalidateAll()
  const [file, setFile] = useState<File | null>(null)
  const [code, setCode] = useState("")
  const restore = useMutation({
    mutationFn: () => api.restoreBackup(file!, code),
    onSuccess: () => {
      onOpenChange(false)
      invalidate()
      toast.success(t("restored"))
    },
    onError: (e) => toast.error(e.message),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-4 sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("restoreTitle")}</DialogTitle>
          <DialogDescription>{t("restoreDescription")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="restore-file">{t("restoreFile")}</Label>
          <Input
            id="restore-file"
            type="file"
            accept=".binderbackup,.zip"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="restore-code">{t("restoreCode")}</Label>
          <Input
            id="restore-code"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <Button onClick={() => restore.mutate()} disabled={!file || code.replace(/[^A-Z0-9]/g, "").length < 24 || restore.isPending}>
          {restore.isPending ? t("restoring") : t("restoreAction")}
        </Button>
      </DialogContent>
    </Dialog>
  )
}
