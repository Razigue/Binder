import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { VaultIcon, CheckCircleIcon, FlaskIcon, CircleNotchIcon, ArrowCounterClockwiseIcon, UploadSimpleIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { FeedCard } from "@/components/feed"
import { UpgradeOffer } from "@/components/upgrade"
import { PageHeader } from "@/components/layout/AppLayout"
import { usePanels } from "@/components/panels"
import { useUpload } from "@/components/upload"
import { useFeed, useInvalidateAll, useProfile } from "@/hooks/queries"
import { useT } from "@/i18n"
import { today } from "@/i18n/messages/today"
import { api, type FeedItem, type SetupStatus } from "@/lib/api"
import { formatSize, formatDate, toIso } from "@/lib/format"

const TONE_RANK: Record<FeedItem["tone"], number> = { urgent: 0, soon: 1, info: 2 }
// The weekly briefing repeats the cards below it: To do shows the cards themselves.
const HIDDEN: FeedItem["kind"][] = ["briefing"]

/** To do: one pile of cards, the most urgent on top. Each says what it is, what to do and by
 * when, with its action. Nothing else: the calendar lives in My papers. */
export function HomePage() {
  const t = useT(today)
  const feed = useFeed()
  const data = feed.data
  const [day] = useState(() => new Date())
  const greeting = useGreeting(day)
  if (data && data.documents === 0 && !data.items.some((i) => i.kind === "report")) return <Welcome setup={data.setup} />
  const items = (data?.items ?? [])
    .filter((i) => !HIDDEN.includes(i.kind))
    // The import report first (what just happened), then by urgency; stable within a tone.
    .map((item, index) => ({ item, index }))
    .sort((a, b) => rank(a.item) - rank(b.item) || a.index - b.index)
    .map(({ item }) => item)
  const attention = items.filter((i) => i.tone !== "info").length
  const summary = attention ? t("summary", { count: attention }) : t("summaryNone")
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={greeting} subtitle={data ? `${formatDate(toIso(day), "long")} · ${summary}` : formatDate(toIso(day), "long")} />
      {data && <SetupCard setup={data.setup} />}
      {!data ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {attention === 0 && <AllInOrder />}
          {items.map((item) => (
            <Card key={item.key} className="gap-0 p-0">
              <ul>
                <FeedCard item={item} />
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function rank(item: FeedItem): number {
  return item.kind === "report" ? -1 : TONE_RANK[item.tone]
}

/** The reward when nothing needs the user. */
function AllInOrder() {
  const t = useT(today)
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl bg-card px-6 py-10 text-center ring-1 ring-foreground/10">
      <CheckCircleIcon className="size-12 text-emerald-600 dark:text-emerald-400" weight="fill" />
      <p className="text-lg font-semibold">{t("allGood")}</p>
      <p className="max-w-md text-sm text-muted-foreground">{t("allGoodHint")}</p>
    </div>
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

/** The local AI installing itself: shown until it is ready, never asks anything. */
function SetupCard({ setup }: { setup: SetupStatus }) {
  const t = useT(today)
  const invalidate = useInvalidateAll()
  const retry = useMutation({ mutationFn: api.retrySetup, onSuccess: invalidate })
  if (setup.phase === "ready" && (setup.warning || setup.upgrade)) {
    return (
      <>
        {setup.upgrade && (
          <Card className="mb-6 p-5">
            <UpgradeOffer upgrade={setup.upgrade} />
          </Card>
        )}
        {setup.warning && (
          <Card className="mb-6 flex-row items-start gap-3 p-5">
            <VaultIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">{setup.warning}</p>
          </Card>
        )}
      </>
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
