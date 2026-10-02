import { useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { CopyIcon, EraserIcon, FlaskIcon, FoldersIcon, KeyIcon, EnvelopeIcon, MonitorIcon, MoonIcon, ArrowsClockwiseIcon, SunIcon, CircleHalfIcon, TrashIcon, type Icon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { usePanels } from "@/components/panels"
import { PageHeader } from "@/components/layout/AppLayout"
import { useInvalidateAll } from "@/hooks/queries"
import { useLocale, useT } from "@/i18n"
import { settings as messages } from "@/i18n/messages/settings"
import { api, type ImportSettings, type Preferences, type PreferencesUpdate, type Profile, type Theme } from "@/lib/api"
import { countryName, countryOptions } from "@/lib/countries"
import { currentLocale, formatDateTime } from "@/lib/format"
import { imapHost } from "@/lib/mail"
import { cn } from "@/lib/utils"

// Language names are written in their own language, so that anyone can find theirs.
const LANGUAGE_NAMES = { en: "English", fr: "Français" } as const
const AUTO = "auto"

export function SettingsPage() {
  const t = useT(messages)
  const imports = useQuery({ queryKey: ["import-settings"], queryFn: api.importSettings })
  const invalidate = useInvalidateAll()
  const run = useMutation({
    mutationFn: api.runImports,
    onSuccess: (r) => {
      invalidate()
      const errors = [r.folder?.error, r.mail?.error].filter(Boolean)
      const imported = (r.folder?.imported ?? 0) + (r.mail?.imported ?? 0)
      if (errors.length) toast.error(errors.join(" · "))
      else if (!r.folder && !r.mail) toast.info(t("import.noSource"))
      else toast.success(imported ? t("import.imported", { count: imported }) : t("import.nothing"))
    },
  })
  const anySource = imports.data && (imports.data.folder.enabled || imports.data.mail.enabled)

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="divide-y">
        <Section title={t("you.title")} description={t("you.description")}>
          <ProfileCard />
        </Section>
        <Section title={t("region.title")} description={t("region.description")}>
          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <RegionCard />
            <AppearanceCard />
          </div>
        </Section>
        <Section
          title={t("import.title")}
          description={t("import.description")}
          action={
            anySource && (
              <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
                <ArrowsClockwiseIcon className={run.isPending ? "animate-spin" : ""} /> {t("import.check")}
              </Button>
            )
          }
        >
          {imports.data ? (
            <div className="grid items-start gap-6 2xl:grid-cols-2">
              {/* Remounted when the server's values change, so the form starts from them. */}
              <FolderCard key={`${imports.data.folder.enabled}:${imports.data.folder.path}`} settings={imports.data} />
              <MailCard settings={imports.data} />
            </div>
          ) : (
            <Skeleton className="h-64 w-full" />
          )}
        </Section>
        <Section title={t("security.title")} description={t("security.description")}>
          <RecoveryCard />
        </Section>
        <Section title={t("data.title")} description={t("data.description")}>
          <DataCard />
        </Section>
      </div>
    </>
  )
}

/** A settings group: what it is about on the left, its cards on the right (stacked on small screens). */
function Section({ title, description, action, children }: { title: string; description: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-4 py-8 first:pt-0 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[20rem_minmax(0,1fr)]">
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
        {action}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}

function CardHeading({ icon: Icon, title, description }: { icon: Icon; title: string; description?: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
        <Icon className="size-5" />
      </span>
      <div className="min-w-0">
        <h3 className="font-semibold">{title}</h3>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
    </div>
  )
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex min-h-10 cursor-pointer items-center gap-3 text-sm font-medium">
      <input type="checkbox" className="size-5 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

function Field({ id, label, hint, className, children }: { id: string; label: string; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function LastCheck({ at, error }: { at: string | null; error: string | null }) {
  const t = useT(messages)
  if (error) return <p className="text-xs text-red-600 dark:text-red-400">{t("lastCheck.error", { error })}</p>
  return (
    <p className="text-xs text-muted-foreground">{at ? t("lastCheck.at", { date: formatDateTime(at) }) : t("lastCheck.never")}</p>
  )
}

// --- About you ---------------------------------------------------------------------------------

const EMPTY_PROFILE: Profile = { name: "", address: "", city: "", email: "", phone: "", notes: "", auto: [] }

function ProfileCard() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile })
  if (!profile.data) return <Skeleton className="h-80 w-full" />
  // Remounted when Binder or the agent changes the details, so the form shows them.
  return <ProfileForm key={JSON.stringify(profile.data)} initial={{ ...EMPTY_PROFILE, ...profile.data }} />
}

function ProfileForm({ initial }: { initial: Profile }) {
  const t = useT(messages)
  const [form, setForm] = useState<Profile>(initial)
  const queryClient = useQueryClient()
  const save = useMutation({
    mutationFn: () => api.saveProfile(form),
    onSuccess: (saved) => {
      queryClient.setQueryData(["profile"], saved)
      toast.success(t("saved"))
    },
    onError: (e) => toast.error(e.message),
  })
  const set = (patch: Partial<Profile>) => setForm((f) => ({ ...f, ...patch }))
  // Filled by Binder from the documents, and not changed since.
  const found = (field: "name" | "address" | "city" | "email" | "phone") =>
    initial.auto.includes(field) && form[field] === initial[field] ? t("you.found") : undefined

  return (
    <Card className="gap-5 p-6">
      <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
        <Field id="profile-name" label={t("you.name")} hint={found("name")}>
          <Input id="profile-name" value={form.name} onChange={(e) => set({ name: e.target.value })} autoComplete="name" />
        </Field>
        <Field id="profile-city" label={t("you.city")} hint={found("city")}>
          <Input id="profile-city" value={form.city} onChange={(e) => set({ city: e.target.value })} />
        </Field>
        <Field id="profile-address" label={t("you.address")} hint={found("address")} className="md:row-span-2">
          <Textarea
            id="profile-address"
            value={form.address}
            onChange={(e) => set({ address: e.target.value })}
            rows={4}
            autoComplete="street-address"
            className="min-h-[7.5rem]"
          />
        </Field>
        <Field id="profile-email" label={t("you.email")} hint={found("email")}>
          <Input id="profile-email" type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} autoComplete="email" />
        </Field>
        <Field id="profile-phone" label={t("you.phone")} hint={found("phone")}>
          <Input id="profile-phone" type="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} autoComplete="tel" />
        </Field>
        <Field id="profile-notes" label={t("you.notes")} hint={t("you.notesHint")} className="md:col-span-2">
          <Textarea
            id="profile-notes"
            value={form.notes}
            onChange={(e) => set({ notes: e.target.value })}
            placeholder={t("you.notesPlaceholder")}
            maxLength={2000}
            rows={4}
          />
        </Field>
      </div>
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {t("save")}
        </Button>
      </div>
    </Card>
  )
}

// --- Language, region and appearance -----------------------------------------------------------

/** Saves a preference at once; the whole interface follows (I18nProvider). */
function useSavePreference() {
  const t = useT(messages)
  const { update } = useLocale()
  return (patch: PreferencesUpdate) => {
    update(patch).catch((e: Error) => toast.error(t("saveError", { error: e.message })))
  }
}

function currencyLabel(currency: string, language: string): { name: string; symbol: string } {
  let name = currency
  let symbol = currency
  try {
    name = new Intl.DisplayNames([language], { type: "currency" }).of(currency) ?? currency
    symbol =
      new Intl.NumberFormat(currentLocale(), { style: "currency", currency })
        .formatToParts(0)
        .find((part) => part.type === "currency")?.value ?? currency
  } catch {
    // Unknown currency code: show the code.
  }
  return { name: name.charAt(0).toLocaleUpperCase(language) + name.slice(1), symbol }
}

function RegionCard() {
  const t = useT(messages)
  const { language, currency, preferences } = useLocale()
  const save = useSavePreference()
  const countries = useMemo(() => countryOptions(language), [language])

  const systemLanguage = preferences?.system_language ?? language
  const systemCountry = preferences?.system_country ?? null
  const languageItems: Record<string, string> = {
    [AUTO]: t("language.auto", { name: LANGUAGE_NAMES[systemLanguage] }),
    ...LANGUAGE_NAMES,
  }
  const countryItems = useMemo<Record<string, string>>(
    () => ({
      [AUTO]: systemCountry ? t("country.auto", { name: countryName(systemCountry, language) }) : t("country.autoUnknown"),
      ...Object.fromEntries(countries.map((c) => [c.code, c.name])),
    }),
    [t, systemCountry, language, countries],
  )
  const money = currencyLabel(currency, language)

  return (
    <Card className="gap-5 p-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="pref-language" label={t("language.label")}>
          <Select
            items={languageItems}
            value={preferences?.language ?? AUTO}
            onValueChange={(value) => value && save({ language: value as Preferences["language"] })}
            disabled={!preferences}
          >
            <SelectTrigger id="pref-language" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>{languageItems[AUTO]}</SelectItem>
              <SelectSeparator />
              {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
                <SelectItem key={code} value={code} lang={code}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id="pref-country" label={t("country.label")}>
          <Select
            items={countryItems}
            value={preferences?.country ?? AUTO}
            onValueChange={(value) => value && save({ country: value === AUTO ? null : value })}
            disabled={!preferences}
          >
            <SelectTrigger id="pref-country" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="max-h-80">
              <SelectItem value={AUTO}>{countryItems[AUTO]}</SelectItem>
              <SelectSeparator />
              {countries.map((c) => (
                <SelectItem key={c.code} value={c.code}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">{t("country.hint")}</p>
        <p className="text-sm font-medium">{t("currency", money)}</p>
      </div>
    </Card>
  )
}

const THEMES: { value: Theme; icon: Icon }[] = [
  { value: "system", icon: MonitorIcon },
  { value: "light", icon: SunIcon },
  { value: "dark", icon: MoonIcon },
]

function AppearanceCard() {
  const t = useT(messages)
  const { theme } = useLocale()
  const save = useSavePreference()
  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={CircleHalfIcon} title={t("appearance.title")} description={t("appearance.description")} />
      <div className="space-y-2">
        <p id="pref-theme" className="text-sm font-medium">
          {t("theme.label")}
        </p>
        <div role="radiogroup" aria-labelledby="pref-theme" className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1">
          {THEMES.map(({ value, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={theme === value}
              onClick={() => theme !== value && save({ theme: value })}
              className={cn(
                "flex min-h-10 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                theme === value
                  ? "bg-card text-foreground shadow-sm ring-1 ring-foreground/5"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" /> {t(`theme.${value}` as const)}
            </button>
          ))}
        </div>
      </div>
    </Card>
  )
}

// --- Automatic import --------------------------------------------------------------------------

function FolderCard({ settings }: { settings: ImportSettings }) {
  const t = useT(messages)
  const [enabled, setEnabled] = useState(settings.folder.enabled)
  const [path, setPath] = useState(settings.folder.path)
  const invalidate = useInvalidateAll()
  const save = useMutation({
    mutationFn: () => api.saveImportSettings({ folder: { enabled, path } }),
    onSuccess: () => {
      invalidate()
      toast.success(enabled ? t("folder.enabled") : t("folder.disabled"))
    },
    onError: (e) => toast.error(e.message),
  })

  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={FoldersIcon} title={t("folder.title")} description={t("folder.description")} />
      <Toggle checked={enabled} onChange={setEnabled} label={t("folder.toggle")} />
      <Field id="watch-path" label={t("folder.path")}>
        <Input id="watch-path" value={path} onChange={(e) => setPath(e.target.value)} placeholder="~/Documents/Scans" />
      </Field>
      <LastCheck at={settings.folder.last_check} error={settings.folder.last_error} />
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {t("save")}
        </Button>
      </div>
    </Card>
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
            placeholder="prenom.nom@gmail.com"
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

// --- Security ----------------------------------------------------------------------------------

function RecoveryCard() {
  const t = useT(messages)
  const queryClient = useQueryClient()
  const backup = useQuery({ queryKey: ["backup"], queryFn: api.backup })
  const [renewing, setRenewing] = useState(false)
  const update = { onSuccess: (info: Awaited<ReturnType<typeof api.backup>>) => queryClient.setQueryData(["backup"], info) }
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
          <Button variant="outline" onClick={() => navigator.clipboard.writeText(info.code ?? "").then(() => toast.success(t("recovery.copied")))}>
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

// --- Data: demo documents and erasing everything ----------------------------------------------

function DataCard() {
  const t = useT(messages)
  const panels = usePanels()
  const demo = useQuery({ queryKey: ["demo"], queryFn: api.demoStatus })
  const invalidate = useInvalidateAll()
  const [confirming, setConfirming] = useState<"demo" | "erase" | null>(null)
  const seed = useMutation({
    mutationFn: api.seedDemo,
    onSuccess: (r) => {
      invalidate()
      toast.success(t("demo.loaded", { count: r.imported }))
      if (r.batch) panels.showReport(r.batch)
    },
    onError: (e) => toast.error(e.message),
  })
  const clear = useMutation({
    mutationFn: api.clearDemo,
    onSuccess: (r) => {
      invalidate()
      toast.success(r.removed ? t("demo.cleared", { count: r.removed }) : t("demo.leftoversCleared"))
    },
    onError: (e) => toast.error(e.message),
  })
  const erase = useMutation({
    mutationFn: api.eraseData,
    onSuccess: (r) => {
      invalidate()
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
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <FlaskIcon className="size-5" />
        </span>
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
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
          <EraserIcon className="size-5" />
        </span>
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
