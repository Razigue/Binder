import { useEffect, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { FolderInput, Mail, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader } from "@/components/layout/AppLayout"
import { useInvalidateAll } from "@/hooks/queries"
import { api, type ImportSettings } from "@/lib/api"

const TIME = new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" })

function LastCheck({ at, error }: { at: string | null; error: string | null }) {
  if (error) return <p className="text-xs text-red-600">Erreur : {error}</p>
  if (!at) return <p className="text-xs text-muted-foreground">Pas encore vérifié.</p>
  return <p className="text-xs text-muted-foreground">Dernière vérification : {TIME.format(new Date(at))}</p>
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
      <input type="checkbox" className="size-4 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["import-settings"], queryFn: api.importSettings })
  const invalidate = useInvalidateAll()
  const run = useMutation({
    mutationFn: api.runImports,
    onSuccess: (r) => {
      invalidate()
      const errors = [r.folder?.error, r.mail?.error].filter(Boolean)
      const imported = (r.folder?.imported ?? 0) + (r.mail?.imported ?? 0)
      if (errors.length) toast.error(errors.join(" · "))
      else if (!r.folder && !r.mail) toast.info("Aucune source d'import activée")
      else toast.success(imported ? `${imported} document${imported > 1 ? "s" : ""} importé${imported > 1 ? "s" : ""}` : "Rien de nouveau")
    },
  })

  return (
    <>
      <PageHeader
        title="Réglages"
        subtitle="Import automatique de vos documents. Binder lit sans rien déplacer ni supprimer."
        actions={
          <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
            <RefreshCw className={run.isPending ? "animate-spin" : ""} /> Vérifier maintenant
          </Button>
        }
      />
      {settings.data && (
        <div className="grid gap-6 lg:grid-cols-2">
          <FolderCard settings={settings.data} />
          <MailCard settings={settings.data} />
        </div>
      )}
    </>
  )
}

function FolderCard({ settings }: { settings: ImportSettings }) {
  const [enabled, setEnabled] = useState(settings.folder.enabled)
  const [path, setPath] = useState(settings.folder.path)
  const invalidate = useInvalidateAll()
  const save = useMutation({
    mutationFn: () => api.saveImportSettings({ folder: { enabled, path } }),
    onSuccess: () => {
      invalidate()
      toast.success(enabled ? "Dossier surveillé" : "Surveillance désactivée")
    },
    onError: (e) => toast.error(e.message),
  })
  useEffect(() => {
    setEnabled(settings.folder.enabled)
    setPath(settings.folder.path)
  }, [settings.folder.enabled, settings.folder.path])

  return (
    <Card className="gap-4 p-5">
      <div className="flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg bg-sky-50 text-sky-600">
          <FolderInput className="size-4" />
        </span>
        <div>
          <h2 className="font-semibold">Dossier surveillé</h2>
          <p className="text-xs text-muted-foreground">Chaque PDF, JPG ou PNG déposé est importé, sous-dossiers compris.</p>
        </div>
      </div>
      <Toggle checked={enabled} onChange={setEnabled} label="Surveiller un dossier" />
      <div className="space-y-1.5">
        <Label htmlFor="watch-path">Chemin du dossier</Label>
        <Input id="watch-path" value={path} onChange={(e) => setPath(e.target.value)} placeholder="~/Documents/Scans" />
      </div>
      <LastCheck at={settings.folder.last_check} error={settings.folder.last_error} />
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          Enregistrer
        </Button>
      </div>
    </Card>
  )
}

function MailCard({ settings }: { settings: ImportSettings }) {
  const m = settings.mail
  const [form, setForm] = useState({ ...m, password: "" })
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
      toast.success("Réglages de messagerie enregistrés")
    },
    onError: (e) => toast.error(e.message),
  })
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  return (
    <Card className="gap-4 p-5">
      <div className="flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg bg-sky-50 text-sky-600">
          <Mail className="size-4" />
        </span>
        <div>
          <h2 className="font-semibold">Boîte mail (IMAP)</h2>
          <p className="text-xs text-muted-foreground">
            Importe les pièces jointes des nouveaux messages, sans les marquer comme lus.
          </p>
        </div>
      </div>
      <Toggle checked={form.enabled} onChange={(enabled) => set({ enabled })} label="Relever la boîte mail toutes les 5 minutes" />
      <div className="grid grid-cols-[1fr_90px] gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="imap-host">Serveur IMAP</Label>
          <Input id="imap-host" value={form.host} onChange={(e) => set({ host: e.target.value })} placeholder="imap.gmail.com" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imap-port">Port</Label>
          <Input id="imap-port" type="number" value={form.port} onChange={(e) => set({ port: Number(e.target.value) })} />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="imap-user">Identifiant</Label>
          <Input id="imap-user" value={form.user} onChange={(e) => set({ user: e.target.value })} autoComplete="off" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imap-pass">Mot de passe d'application</Label>
          <Input
            id="imap-pass"
            type="password"
            value={form.password}
            onChange={(e) => set({ password: e.target.value })}
            placeholder={m.password_set ? "Enregistré (inchangé)" : ""}
            autoComplete="new-password"
          />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="imap-folder">Dossier</Label>
          <Input id="imap-folder" value={form.folder} onChange={(e) => set({ folder: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imap-since">Au premier passage, remonter à (jours)</Label>
          <Input id="imap-since" type="number" min={1} max={365} value={form.since_days} onChange={(e) => set({ since_days: Number(e.target.value) })} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Le mot de passe est stocké dans la base chiffrée, sur cette machine uniquement.
      </p>
      <LastCheck at={m.last_check} error={m.last_error} />
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          Enregistrer
        </Button>
      </div>
    </Card>
  )
}
