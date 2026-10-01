import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Check, Cpu, Download, ExternalLink, LoaderCircle, RefreshCw, Trash2, TriangleAlert, X } from "lucide-react"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { keys } from "@/hooks/queries"
import { useT } from "@/i18n"
import type { Translate } from "@/i18n/core"
import { models as messages } from "@/i18n/messages/models"
import { api, type LocalModel, type ModelsOverview } from "@/lib/api"
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

type T = Translate<typeof messages.en>

// Sizes as announced by Ollama, in decimal units (6.6 GB).
const gigabytes = (t: T, bytes: number) => t("gigabytes", { value: formatNumber(bytes / 1e9, { maximumFractionDigits: 1 }) })

/** A message whose `{name}` placeholder is replaced by a React node (e.g. inline code). */
function withNode(text: string, name: string, node: React.ReactNode) {
  const [before, after] = text.split(`{${name}}`)
  return (
    <>
      {before}
      {node}
      {after}
    </>
  )
}

const isDownloading = (m: LocalModel) => m.download !== null && m.download.phase !== "error"

export function ModelSettings() {
  const t = useT(messages)
  const qc = useQueryClient()
  const overview = useQuery({
    queryKey: ["llm"],
    queryFn: api.models,
    // Progress of running downloads; otherwise, watch for Ollama to start.
    refetchInterval: (q) => {
      const data = q.state.data
      if (data?.models.some(isDownloading)) return 1000
      return data && data.enabled && !data.ollama ? 5000 : false
    },
  })
  const data = overview.data

  // A download finished: tell the user and refresh the AI status (sidebar).
  const downloading = useRef(new Set<string>())
  useEffect(() => {
    if (!data) return
    const now = new Set(data.models.filter(isDownloading).map((m) => m.name))
    for (const name of downloading.current) {
      const model = data.models.find((m) => m.name === name)
      if (!now.has(name) && model?.installed) {
        toast.success(t("ready", { name: model.label }))
        qc.invalidateQueries({ queryKey: keys.status })
      }
    }
    downloading.current = now
  }, [data, qc, t])

  const update = (next: ModelsOverview) => {
    qc.setQueryData(["llm"], next)
    qc.invalidateQueries({ queryKey: keys.status })
  }
  const onError = (e: Error) => toast.error(e.message)
  const choose = useMutation({ mutationFn: api.chooseModel, onSuccess: update, onError })
  const download = useMutation({ mutationFn: api.downloadModel, onSuccess: update, onError })
  const refresh = () => qc.invalidateQueries({ queryKey: ["llm"] })
  const cancel = useMutation({ mutationFn: api.cancelDownload, onSettled: refresh })
  const remove = useMutation({
    mutationFn: api.deleteModel,
    onSuccess: () => {
      refresh()
      qc.invalidateQueries({ queryKey: keys.status })
    },
    onError,
  })
  const [toDelete, setToDelete] = useState<LocalModel | null>(null)

  const active = data?.models.find((m) => m.name === data.active)
  // Ollama shares layers between models: no deletion during a download.
  const anyDownload = data?.models.some(isDownloading) ?? false

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Cpu className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{t("title")}</h2>
          <p className="text-xs text-muted-foreground">{t("description")}</p>
        </div>
        {data && data.enabled && data.ollama && (
          <Badge variant={data.active_installed ? "secondary" : "outline"} className="mt-1">
            {data.active_installed ? t("active", { name: active?.label ?? data.active }) : t("noActive")}
          </Badge>
        )}
      </div>

      {data && !data.enabled && (
        <Notice>{withNode(t("disabled"), "setting", <code>BINDER_LLM_ENABLED=false</code>)}</Notice>
      )}
      {data && data.enabled && !data.ollama && (
        <Notice>
          <p>{withNode(t("offline"), "url", <code>{data.ollama_url}</code>)}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" render={<a href="https://ollama.com/download" target="_blank" rel="noreferrer" />} nativeButton={false}>
              <ExternalLink /> {t("install")}
            </Button>
            <Button size="sm" variant="ghost" onClick={refresh} disabled={overview.isFetching}>
              <RefreshCw className={overview.isFetching ? "animate-spin" : ""} /> {t("retry")}
            </Button>
          </div>
        </Notice>
      )}

      {data && data.enabled && (
        <ul className="divide-y rounded-lg border">
          {data.models.map((m) => (
            <ModelRow
              key={m.name}
              model={m}
              active={data.active_installed && m.name === data.active}
              online={data.ollama}
              busy={choose.isPending || download.isPending}
              canDelete={!anyDownload}
              onChoose={() => choose.mutate(m.name)}
              onDownload={() => download.mutate(m.name)}
              onCancel={() => cancel.mutate(m.name)}
              onDelete={() => setToDelete(m)}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(open) => !open && setToDelete(null)}
        title={t("deleteTitle", { name: toDelete?.label ?? "" })}
        description={t("deleteDescription", { size: toDelete ? gigabytes(t, toDelete.size) : "" })}
        confirmLabel={t("deleteConfirm")}
        onConfirm={() => (toDelete ? remove.mutateAsync(toDelete.name) : undefined)}
      />
    </Card>
  )
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/15 dark:text-amber-200">
      <TriangleAlert className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function ModelRow({
  model: m,
  active,
  online,
  busy,
  canDelete,
  onChoose,
  onDownload,
  onCancel,
  onDelete,
}: {
  model: LocalModel
  active: boolean
  online: boolean
  busy: boolean
  canDelete: boolean
  onChoose: () => void
  onDownload: () => void
  onCancel: () => void
  onDelete: () => void
}) {
  const t = useT(messages)
  const d = m.download
  // The search model is used as soon as it is installed: nothing to choose.
  const search = m.kind === "embedding"
  return (
    <li className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3", active && "bg-muted/40")}>
      <div className="min-w-48 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{m.label}</span>
          {m.recommended && <Badge variant="secondary">{t("recommended")}</Badge>}
          {(active || (search && m.installed)) && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
              <Check className="size-3.5" /> {search ? t("searchOn") : t("inUse")}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {m.description} <span className="tabular-nums">· {gigabytes(t, m.size)}</span>
        </p>
      </div>

      {d && d.phase !== "error" ? (
        <DownloadProgress download={d} onCancel={onCancel} />
      ) : (
        <div className="flex items-center gap-2">
          {d?.phase === "error" && <span className="text-xs text-red-600 dark:text-red-400">{t("failed", { error: d.error ?? "" })}</span>}
          {m.installed ? (
            <>
              {!active && !search && (
                <Button size="sm" variant="outline" onClick={onChoose} disabled={busy || !online}>
                  {t("use")}
                </Button>
              )}
              {m.in_catalog && (
                <Button
                  size="icon-sm"
                  variant="ghost"
                  onClick={onDelete}
                  disabled={!online || !canDelete}
                  title={canDelete ? undefined : t("deleteAfterDownload")}
                  aria-label={t("deleteLabel", { name: m.label })}
                >
                  <Trash2 />
                </Button>
              )}
            </>
          ) : (
            <Button size="sm" variant={m.recommended ? "default" : "outline"} onClick={onDownload} disabled={busy || !online}>
              <Download /> {d?.phase === "error" ? t("retry") : t("download")}
            </Button>
          )}
        </div>
      )}
    </li>
  )
}

function DownloadProgress({ download: d, onCancel }: { download: NonNullable<LocalModel["download"]>; onCancel: () => void }) {
  const t = useT(messages)
  const ratio = d.total ? d.completed / d.total : 0
  const label = {
    queued: t("queued"),
    starting: t("starting"),
    verifying: t("verifying"),
    downloading: t("progress", {
      done: gigabytes(t, d.completed),
      total: gigabytes(t, d.total),
      percent: formatNumber(Math.floor(ratio * 100) / 100, { style: "percent" }),
    }),
    error: "",
  }[d.phase]
  return (
    <div className="flex w-full items-center gap-3 sm:w-72">
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums">
          {d.phase === "queued" ? null : <LoaderCircle className="size-3 animate-spin" />} {label}
        </p>
        <Progress value={d.phase === "downloading" ? ratio * 100 : null} />
      </div>
      <Button size="icon-sm" variant="ghost" onClick={onCancel} aria-label={t("cancel")}>
        <X />
      </Button>
    </div>
  )
}
