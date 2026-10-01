import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { BookLock, CircleCheck, FlaskConical, Loader2, RotateCcw, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { FeedCard } from "@/components/feed"
import { PageHeader } from "@/components/layout/AppLayout"
import { usePanels } from "@/components/panels"
import { useUpload } from "@/components/upload"
import { useFeed, useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { today } from "@/i18n/messages/today"
import { api, type FeedItem, type SetupStatus } from "@/lib/api"
import { formatSize, formatDate, toIso } from "@/lib/format"

export function HomePage() {
  const t = useT(today)
  const feed = useFeed()
  const data = feed.data
  const [day] = useState(() => toIso(new Date()))
  if (data && data.documents === 0 && !data.items.some((i) => i.kind === "report")) return <Welcome setup={data.setup} />
  const now = data?.items.filter((i) => i.tone !== "info") ?? []
  const later = data?.items.filter((i) => i.tone === "info") ?? []
  return (
    <>
      <PageHeader title={t("title")} subtitle={formatDate(day, "long")} />
      {data && <SetupCard setup={data.setup} />}
      {!data ? (
        <Card className="gap-3 p-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </Card>
      ) : (
        <div className="space-y-6">
          {now.length === 0 ? (
            <div className="flex items-start gap-3 rounded-xl bg-card p-5 ring-1 ring-foreground/10">
              <CircleCheck className="mt-0.5 size-5 text-emerald-600 dark:text-emerald-400" />
              <div>
                <p className="font-medium">{t("allGood")}</p>
                <p className="text-sm text-muted-foreground">{t("allGoodHint")}</p>
              </div>
            </div>
          ) : (
            <FeedList items={now} />
          )}
          {later.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-medium text-muted-foreground">{t("later")}</h2>
              <FeedList items={later} />
            </section>
          )}
          <DropBar />
        </div>
      )}
    </>
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
  if (setup.phase === "ready" || setup.phase === "disabled") return null
  const error = setup.phase === "error"
  const ratio = setup.total ? Math.min(100, (setup.completed / setup.total) * 100) : null
  return (
    <Card className="mb-6 gap-3 p-5">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          {error ? <BookLock className="size-4" /> : <Loader2 className="size-4 animate-spin" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{t(`setup.${setup.phase}`)}</p>
          <p className="text-sm text-muted-foreground">{error ? setup.error || t("setup.errorHint") : t("setup.hint")}</p>
        </div>
        {error && (
          <Button variant="outline" size="sm" onClick={() => retry.mutate()} disabled={retry.isPending}>
            <RotateCcw /> {t("setup.retry")}
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
          <Upload className="size-4" /> {t("dropHere")}
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
            <FlaskConical /> {demo.isPending ? t("demoLoading") : t("demo")}
          </Button>
          <Button variant="ghost" onClick={() => setRestoring(true)}>
            <RotateCcw /> {t("restore")}
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
