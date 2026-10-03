import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { EnvelopeIcon, FolderOpenIcon, FoldersIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { settings as messages } from "@/i18n/messages/settings"
import { api, type ImportSettings } from "@/lib/api"
import { imapHost } from "@/lib/mail"
import { CardHeading, Field, LastCheck, Toggle } from "./parts"

/** The system's folder dialog: the desktop window's own, else one the local server opens. */
async function chooseFolder(initial: string): Promise<string | null> {
  const desktop = window.pywebview?.api?.choose_folder
  if (desktop) return desktop(initial)
  return (await api.chooseImportFolder()).path
}

export function FolderCard({ settings }: { settings: ImportSettings }) {
  const t = useT(messages)
  const folder = settings.folder
  const watching = folder.enabled && Boolean(folder.path)
  // Stopped: the folder is remembered so the watch resumes in one click.
  const stopped = !folder.enabled && Boolean(folder.path)
  // Without a folder dialog (no display, packaged without Tk), the path is typed.
  const [manual, setManual] = useState(false)
  const [path, setPath] = useState(folder.path)
  const invalidate = useInvalidateAll()
  // Choosing the folder is the whole setup: the server starts watching and importing at once.
  const save = useMutation({
    mutationFn: (next: { enabled: boolean; path: string }) => api.saveImportSettings({ folder: next }),
    onSuccess: (_, next) => {
      void invalidate()
      toast.success(next.enabled ? t("folder.enabled") : t("folder.disabled"))
    },
    onError: (e) => toast.error(e.message),
  })
  const browse = useMutation({
    mutationFn: () => chooseFolder(folder.path),
    onSuccess: (chosen) => {
      if (chosen) save.mutate({ enabled: true, path: chosen })
    },
    onError: (e) => {
      setManual(true)
      toast.info(e.message)
    },
  })
  const busy = browse.isPending || save.isPending

  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={FoldersIcon} title={t("folder.title")} description={t("folder.description")} />
      {watching && (
        <div className="space-y-1.5 rounded-lg border bg-muted/40 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-medium">
            <span className="size-2 shrink-0 rounded-full bg-emerald-500" />
            {t("folder.watching")}
          </p>
          <p className="font-mono text-xs break-all text-muted-foreground">{folder.path}</p>
          <LastCheck at={folder.last_check} error={folder.last_error} />
        </div>
      )}
      {stopped && (
        <div className="space-y-1.5 rounded-lg border px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-medium">
            <span className="size-2 shrink-0 rounded-full bg-muted-foreground/50" />
            {t("folder.stopped")}
          </p>
          <p className="font-mono text-xs break-all text-muted-foreground">{folder.path}</p>
        </div>
      )}
      {manual && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate({ enabled: true, path })
          }}
        >
          <Field id="watch-path" label={t("folder.path")} className="min-w-0 flex-1">
            <Input id="watch-path" value={path} onChange={(e) => setPath(e.target.value)} placeholder="~/Documents/Scans" />
          </Field>
          <Button type="submit" disabled={busy || !path.trim()}>
            {t("folder.watch")}
          </Button>
        </form>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant={watching || stopped ? "outline" : "default"} onClick={() => browse.mutate()} disabled={busy}>
          <FolderOpenIcon /> {watching || stopped ? t("folder.change") : t("folder.choose")}
        </Button>
        {watching && (
          <Button variant="ghost" onClick={() => save.mutate({ enabled: false, path: folder.path })} disabled={busy}>
            {t("folder.stop")}
          </Button>
        )}
        {stopped && (
          <Button variant="outline" onClick={() => save.mutate({ enabled: true, path: folder.path })} disabled={busy}>
            {t("folder.resume")}
          </Button>
        )}
      </div>
    </Card>
  )
}

export function MailCard({ settings }: { settings: ImportSettings }) {
  const t = useT(messages)
  const m = settings.mail
  const [form, setForm] = useState({ ...m, password: "" })
  // The server follows the address until the user sets it by hand.
  const [customHost, setCustomHost] = useState(!!m.host && m.host !== imapHost(m.user))
  const invalidate = useInvalidateAll()

  const save = useMutation({
    mutationFn: () =>
      api.saveImportSettings({
        mail: {
          enabled: form.enabled,
          host: form.host.trim(),
          port: Number(form.port) || 993,
          user: form.user.trim(),
          folder: form.folder.trim() || "INBOX",
          since_days: Number(form.since_days) || 30,
          password: form.password ? form.password : null,
        },
      }),
    onSuccess: () => {
      void invalidate()
      setForm((f) => ({ ...f, password: "" }))
      toast.success(t("mail.saved"))
    },
    onError: (e) => toast.error(e.message),
  })
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={EnvelopeIcon} title={t("mail.title")} description={t("mail.description")} />
      <Toggle checked={form.enabled} onChange={(enabled) => set({ enabled })} label={t("mail.toggle")} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="imap-user" label={t("mail.address")}>
          <Input
            id="imap-user"
            type="email"
            value={form.user}
            onChange={(e) => set({ user: e.target.value, ...(customHost ? {} : { host: imapHost(e.target.value) }) })}
            placeholder={t("mail.addressPlaceholder")}
            autoComplete="off"
          />
        </Field>
        <Field id="imap-pass" label={t("mail.password")} hint={t("mail.passwordHint")}>
          <Input
            id="imap-pass"
            type="password"
            value={form.password}
            onChange={(e) => set({ password: e.target.value })}
            placeholder={m.password_set ? t("mail.passwordSet") : ""}
            autoComplete="new-password"
          />
        </Field>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer py-1 text-muted-foreground select-none">{t("mail.advanced")}</summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-[1fr_100px]">
          <Field id="imap-host" label={t("mail.host")}>
            <Input
              id="imap-host"
              value={form.host}
              onChange={(e) => {
                setCustomHost(true)
                set({ host: e.target.value })
              }}
            />
          </Field>
          <Field id="imap-port" label={t("mail.port")}>
            <Input id="imap-port" type="number" value={form.port} onChange={(e) => set({ port: Number(e.target.value) })} />
          </Field>
          <Field id="imap-folder" label={t("mail.folder")}>
            <Input id="imap-folder" value={form.folder} onChange={(e) => set({ folder: e.target.value })} />
          </Field>
          <Field id="imap-since" label={t("mail.since")}>
            <Input
              id="imap-since"
              type="number"
              min={1}
              max={365}
              value={form.since_days}
              onChange={(e) => set({ since_days: Number(e.target.value) })}
            />
          </Field>
        </div>
      </details>
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">{t("mail.passwordNote")}</p>
        <LastCheck at={m.last_check} error={m.last_error} />
      </div>
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {t("save")}
        </Button>
      </div>
    </Card>
  )
}
