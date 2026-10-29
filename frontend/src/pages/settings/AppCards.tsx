import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowsClockwiseIcon, BellIcon, CopyIcon, CpuIcon, EraserIcon, FlaskIcon, KeyIcon, TrashIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { usePanels } from "@/components/panels/context"
import { UpgradeOffer } from "@/components/upgrade"
import { keys, useBackup, useDemoStatus, useInvalidateAll, useModels, useReminders } from "@/hooks/queries"
import { useT } from "@/i18n"
import { localAi } from "@/i18n/messages/localAi"
import { settings as messages } from "@/i18n/messages/settings"
import { api, type BackupInfo, type ModelsOverview } from "@/lib/api"
import { formatDateTime, formatSize } from "@/lib/format"
import { CardHeading, ChoiceGroup, IconTile, Toggle } from "./parts"

export function RemindersCard() {
  const t = useT(messages)
  const queryClient = useQueryClient()
  const reminders = useReminders()
  const save = useMutation({
    mutationFn: api.saveReminders,
    onSuccess: (data) => {
      queryClient.setQueryData(keys.reminders, data)
      toast.success(data.enabled ? t("reminders.enabled") : t("reminders.disabled"))
    },
    onError: (e) => toast.error(e.message),
  })
  if (!reminders.data) return <Skeleton className="h-36 w-full" />
  const { enabled, available, hour } = reminders.data
  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={BellIcon} title={t("reminders.card")} description={t("reminders.cardDescription", { hour })} />
      {available ? (
        <Toggle checked={enabled} onChange={(v) => save.mutate(v)} label={t("reminders.toggle")} />
      ) : (
        <p className="text-sm text-muted-foreground">{t("reminders.unavailable")}</p>
      )}
    </Card>
  )
}

export function RecoveryCard() {
  const t = useT(messages)
  const queryClient = useQueryClient()
  const backup = useBackup()
  const [renewing, setRenewing] = useState(false)
  const update = { onSuccess: (info: BackupInfo) => queryClient.setQueryData(keys.backup, info) }
  const confirm = useMutation({ mutationFn: api.confirmRecoveryCode, ...update })
  const renew = useMutation({ mutationFn: api.renewRecoveryCode, ...update })
  const now = useMutation({
    mutationFn: api.backupNow,
    onSuccess: (info) => {
      update.onSuccess(info)
      if (info.last_error) toast.error(t("backup.error", { error: info.last_error }))
      else toast.success(t("backup.done"))
    },
    onError: (e) => toast.error(e.message),
  })
  const info = backup.data
  if (!info) return <Skeleton className="h-48 w-full" />

  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={KeyIcon} title={t("recovery.title")} description={info.code ? t("recovery.toWrite") : t("recovery.noted")} />
      {info.code ? (
        <div className="flex flex-wrap items-center gap-3">
          <code className="rounded-lg border bg-muted/50 px-4 py-2 font-sans text-lg font-semibold tracking-wider select-all">
            {info.code}
          </code>
          <Button variant="outline" onClick={() => void navigator.clipboard.writeText(info.code ?? "").then(() => toast.success(t("recovery.copied")))}>
            <CopyIcon /> {t("recovery.copy")}
          </Button>
          <Button onClick={() => confirm.mutate()} disabled={confirm.isPending}>
            {t("recovery.done")}
          </Button>
        </div>
      ) : (
        <div>
          <Button variant="outline" onClick={() => setRenewing(true)}>
            <KeyIcon /> {t("recovery.renew")}
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4 border-t pt-5">
        <div className="min-w-0 space-y-1 text-sm">
          {info.last_error ? (
            <p className="text-red-600 dark:text-red-400">{t("backup.error", { error: info.last_error })}</p>
          ) : (
            <p className="font-medium">{info.last_backup ? t("backup.last", { date: formatDateTime(info.last_backup) }) : t("backup.never")}</p>
          )}
          <p className="text-xs break-all text-muted-foreground">{t("backup.folder", { path: info.folder })}</p>
        </div>
        <Button variant="outline" onClick={() => now.mutate()} disabled={now.isPending}>
          <ArrowsClockwiseIcon className={now.isPending ? "animate-spin" : ""} /> {t("backup.now")}
        </Button>
      </div>
      <ConfirmDialog
        open={renewing}
        onOpenChange={setRenewing}
        title={t("recovery.renewTitle")}
        description={t("recovery.renewDescription")}
        confirmLabel={t("recovery.renew")}
        destructive={false}
        onConfirm={() => renew.mutateAsync()}
      />
    </Card>
  )
}

/** The local AI: the model in use and the one this machine suits. */
export function LocalAiCard() {
  const t = useT(localAi)
  const models = useModels()
  if (!models.data) return <Skeleton className="h-32 w-full" />
  const data = models.data
  if (!data.enabled) {
    return (
      <Card className="gap-5 p-6">
        <CardHeading icon={CpuIcon} title={t("card.title")} description={t("card.disabled")} />
      </Card>
    )
  }
  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={CpuIcon} title={t("card.title")} description={data.automatic ? t("card.automatic") : t("card.manual")} />
      <ModelPicker data={data} />
      {data.upgrade && <UpgradeOffer upgrade={data.upgrade} />}
    </Card>
  )
}

/** The 4B or the 9B, by hand: confirmed first, since switching may mean a long download and
 * always deletes the former model. */
function ModelPicker({ data }: { data: ModelsOverview }) {
  const t = useT(localAi)
  const queryClient = useQueryClient()
  const [target, setTarget] = useState<string | null>(null)
  const done = (overview: ModelsOverview) => {
    queryClient.setQueryData(keys.models, overview)
    if (!overview.picked) toast.success(t("pick.done", { label: overview.active_label }))
  }
  const pick = useMutation({ mutationFn: api.pickModel, onSuccess: done, onError: (e) => toast.error(e.message) })
  const stop = useMutation({
    mutationFn: api.cancelDownload,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.models }),
    onError: (e) => toast.error(e.message),
  })
  const options = data.models.filter((m) => m.pickable)
  if (!data.ollama || options.length < 2) return null
  const current = data.models.find((m) => m.name === data.active && m.in_catalog && m.kind === "chat")
  const chosen = options.find((m) => m.name === target)
  const picked = options.find((m) => m.name === data.picked)
  const download = picked?.download
  const heavier = (name: string) =>
    options.findIndex((m) => m.name === name) > options.findIndex((m) => m.name === data.recommended) &&
    options.some((m) => m.name === data.recommended)

  return (
    <div className="space-y-3 border-t pt-5">
      <ChoiceGroup
        labelId="model-pick"
        label={t("pick.label")}
        value={data.picked ?? data.active}
        className="grid-cols-2"
        disabled={pick.isPending || !!data.picked}
        onChange={setTarget}
        options={options.map((m) => ({
          value: m.name,
          content: (
            <span className="flex flex-wrap items-center justify-center gap-x-2">
              {m.label}
              {m.name === data.recommended && <span className="text-xs font-normal text-muted-foreground">{t("pick.recommended")}</span>}
            </span>
          ),
        }))}
      />
      {picked && download && (
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1 text-sm">
              {download.phase === "error" ? (
                <p role="alert" className="text-red-700 dark:text-red-400">
                  {t("pick.failed", { label: picked.label, error: download.error ?? "" })}
                </p>
              ) : (
                <>
                  <p className="font-medium">{t("pick.downloading", { label: picked.label })}</p>
                  <p className="text-muted-foreground">{t("pick.switch", { current: data.active_label })}</p>
                </>
              )}
            </div>
            <Button variant="ghost" size="sm" onClick={() => stop.mutate(picked.name)} disabled={stop.isPending}>
              {t("pick.stop")}
            </Button>
          </div>
          {download.phase !== "error" && download.total > 0 && (
            <div className="space-y-1">
              <Progress
                value={Math.min(100, (download.completed / download.total) * 100)}
                aria-label={t("pick.downloading", { label: picked.label })}
                getAriaValueText={() =>
                  t("offer.progress", { done: formatSize(download.completed), total: formatSize(download.total) })
                }
              />
              <p className="text-xs text-muted-foreground tabular-nums">
                {t("offer.progress", { done: formatSize(download.completed), total: formatSize(download.total) })}
              </p>
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={chosen !== undefined}
        onOpenChange={(open) => !open && setTarget(null)}
        title={t("pick.title", { label: chosen?.label ?? "" })}
        description={
          chosen && (
            <span className="flex flex-col gap-2">
              {!chosen.installed && (
                <span>{t("pick.download", { label: chosen.label, size: formatSize(chosen.size), current: data.active_label })}</span>
              )}
              {current && current.name !== chosen.name && (
                <span>{t("pick.removed", { label: chosen.label, current: current.label, size: formatSize(current.size) })}</span>
              )}
              {heavier(chosen.name) && <span>{t("pick.heavier", { label: chosen.label, recommended: data.recommended_label })}</span>}
              <span>{t("pick.keep")}</span>
            </span>
          )
        }
        confirmLabel={t("pick.confirm")}
        destructive={false}
        onConfirm={() => chosen && pick.mutateAsync(chosen.name)}
      />
    </div>
  )
}

/** Demo documents and erasing everything. */
export function DataCard() {
  const t = useT(messages)
  const panels = usePanels()
  const demo = useDemoStatus()
  const invalidate = useInvalidateAll()
  const [confirming, setConfirming] = useState<"demo" | "erase" | null>(null)
  const seed = useMutation({
    mutationFn: api.seedDemo,
    onSuccess: (r) => {
      void invalidate()
      toast.success(t("demo.loaded", { count: r.imported }))
      if (r.batch) panels.showReport(r.batch)
    },
    onError: (e) => toast.error(e.message),
  })
  const clear = useMutation({
    mutationFn: api.clearDemo,
    onSuccess: (r) => {
      void invalidate()
      toast.success(r.removed ? t("demo.cleared", { count: r.removed }) : t("demo.leftoversCleared"))
    },
    onError: (e) => toast.error(e.message),
  })
  const erase = useMutation({
    mutationFn: api.eraseData,
    onSuccess: (r) => {
      void invalidate()
      toast.success(t("erase.done", { count: r.removed }))
    },
    onError: (e) => toast.error(e.message),
  })
  const count = demo.data?.documents ?? 0
  const leftovers = demo.data?.leftovers ?? 0
  const busy = seed.isPending || clear.isPending || erase.isPending

  return (
    <Card className="gap-0 p-0">
      <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center">
        <IconTile icon={FlaskIcon} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{t("demo.title")}</p>
          <p className="text-sm text-muted-foreground">{count ? t("demo.count", { count }) : t("demo.none")}</p>
          {leftovers > 0 && (
            <p className="text-xs text-muted-foreground">{t("demo.leftovers", { count: leftovers })}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {count === 0 && (
            <Button variant="outline" onClick={() => seed.mutate()} disabled={busy || demo.isPending}>
              <FlaskIcon /> {seed.isPending ? t("demo.loading") : t("demo.load")}
            </Button>
          )}
          {(count > 0 || leftovers > 0) && (
            <Button variant="outline" onClick={() => setConfirming("demo")} disabled={busy}>
              <TrashIcon /> {t("demo.clear")}
            </Button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-4 border-t p-6 sm:flex-row sm:items-center">
        <IconTile icon={EraserIcon} tone="destructive" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{t("erase.title")}</p>
          <p className="text-sm text-muted-foreground">{t("erase.what")}</p>
        </div>
        <Button variant="destructive" onClick={() => setConfirming("erase")} disabled={busy}>
          <EraserIcon /> {t("erase.button")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirming === "demo"}
        onOpenChange={(open) => setConfirming(open ? "demo" : null)}
        title={t("demo.confirmTitle")}
        description={t("demo.confirmDescription")}
        confirmLabel={t("demo.clear")}
        onConfirm={() => clear.mutateAsync()}
      />
      <ConfirmDialog
        open={confirming === "erase"}
        onOpenChange={(open) => setConfirming(open ? "erase" : null)}
        title={t("erase.confirmTitle")}
        description={t("erase.confirmDescription")}
        confirmLabel={t("erase.button")}
        typeToConfirm={t("erase.word")}
        onConfirm={() => erase.mutateAsync()}
      />
    </Card>
  )
}
