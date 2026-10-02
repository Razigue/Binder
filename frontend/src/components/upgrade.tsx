import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowCounterClockwiseIcon, DownloadSimpleIcon, SparkleIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { localAi } from "@/i18n/messages/localAi"
import { api, type ModelUpgrade } from "@/lib/api"
import { formatSize } from "@/lib/format"

/** A better model for this machine: offered with its size, downloaded only on a yes. */
export function UpgradeOffer({ upgrade }: { upgrade: ModelUpgrade }) {
  const t = useT(localAi)
  const invalidate = useInvalidateAll()
  const accept = useMutation({ mutationFn: api.acceptUpgrade, onSuccess: invalidate, onError: (e) => toast.error(e.message) })
  const decline = useMutation({
    mutationFn: api.declineUpgrade,
    onSuccess: () => {
      invalidate()
      toast.info(t("offer.declined"))
    },
    onError: (e) => toast.error(e.message),
  })
  const download = upgrade.download
  const failed = download?.phase === "error"
  const busy = accept.isPending || decline.isPending
  if (upgrade.accepted && download && !failed) {
    const ratio = download.total ? Math.min(100, (download.completed / download.total) * 100) : null
    return (
      <div className="space-y-2">
        <p className="font-medium">{t("offer.downloading", { label: upgrade.label })}</p>
        <p className="text-sm text-muted-foreground">{t("offer.switch")}</p>
        {ratio !== null && (
          <div className="space-y-1">
            <Progress
              value={ratio}
              aria-label={t("offer.downloading", { label: upgrade.label })}
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
    )
  }
  return (
    <div className="flex flex-wrap items-start gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <SparkleIcon className="size-4" />
      </span>
      <div className="min-w-0 flex-1 basis-60">
        <p className="font-medium">{t("offer.title")}</p>
        <p role={failed ? "alert" : undefined} className="text-sm text-muted-foreground">
          {failed
            ? t("offer.failed", { error: download?.error ?? "" })
            : t("offer.text", { label: upgrade.label, size: formatSize(upgrade.size) })}
        </p>
      </div>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => decline.mutate()} disabled={busy}>
          {t("offer.decline")}
        </Button>
        <Button size="sm" onClick={() => accept.mutate()} disabled={busy}>
          {failed ? <ArrowCounterClockwiseIcon /> : <DownloadSimpleIcon />} {failed ? t("offer.retry") : t("offer.accept")}
        </Button>
      </div>
    </div>
  )
}
