import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader } from "@/components/layout/AppLayout"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { settings as messages } from "@/i18n/messages/settings"
import { api, type ImportSettings } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { imapHost } from "@/lib/mail"

export function SettingsPage() {
  const t = useT(messages)
  const settings = useQuery({ queryKey: ["import-settings"], queryFn: api.importSettings })
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="max-w-2xl">{settings.data && <MailCard settings={settings.data} />}</div>
    </>
  )
}

function MailCard({ settings }: { settings: ImportSettings }) {
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
      invalidate()
      setForm((f) => ({ ...f, password: "" }))
      toast.success(t("mail.saved"))
    },
    onError: (e) => toast.error(e.message),
  })
  const run = useMutation({
    mutationFn: api.runImports,
    onSuccess: (r) => {
      invalidate()
      if (r.mail?.error) toast.error(r.mail.error)
      else toast.success(r.mail?.imported ? t("mail.imported", { count: r.mail.imported }) : t("mail.nothing"))
    },
  })
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  return (
    <Card className="gap-5 p-5">
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-primary"
          checked={form.enabled}
          onChange={(e) => set({ enabled: e.target.checked })}
        />
        <span>
          <span className="block text-sm font-medium">{t("mail.toggle")}</span>
          <span className="block text-xs text-muted-foreground">{t("mail.description")}</span>
        </span>
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="imap-user">{t("mail.address")}</Label>
          <Input
            id="imap-user"
            type="email"
            value={form.user}
            onChange={(e) => set({ user: e.target.value, ...(customHost ? {} : { host: imapHost(e.target.value) }) })}
            placeholder="prenom.nom@gmail.com"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imap-pass">{t("mail.password")}</Label>
          <Input
            id="imap-pass"
            type="password"
            value={form.password}
            onChange={(e) => set({ password: e.target.value })}
            placeholder={m.password_set ? t("mail.passwordSet") : ""}
            autoComplete="new-password"
          />
          <p className="text-xs text-muted-foreground">{t("mail.passwordHint")}</p>
        </div>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground select-none">{t("mail.advanced")}</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_90px]">
          <div className="space-y-1.5">
            <Label htmlFor="imap-host">{t("mail.host")}</Label>
            <Input
              id="imap-host"
              value={form.host}
              onChange={(e) => {
                setCustomHost(true)
                set({ host: e.target.value })
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="imap-port">{t("mail.port")}</Label>
            <Input id="imap-port" type="number" value={form.port} onChange={(e) => set({ port: Number(e.target.value) })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="imap-folder">{t("mail.folder")}</Label>
            <Input id="imap-folder" value={form.folder} onChange={(e) => set({ folder: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="imap-since">{t("mail.since")}</Label>
            <Input
              id="imap-since"
              type="number"
              min={1}
              max={365}
              value={form.since_days}
              onChange={(e) => set({ since_days: Number(e.target.value) })}
            />
          </div>
        </div>
      </details>
      <p className="text-xs text-muted-foreground">{t("mail.passwordNote")}</p>
      {m.last_error ? (
        <p className="text-xs text-red-600 dark:text-red-400">{t("lastCheck.error", { error: m.last_error })}</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          {m.last_check ? t("lastCheck.at", { date: formatDateTime(m.last_check) }) : t("lastCheck.never")}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {t("save")}
        </Button>
        {m.enabled && (
          <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
            <RefreshCw className={run.isPending ? "animate-spin" : ""} /> {t("mail.check")}
          </Button>
        )}
      </div>
    </Card>
  )
}
