import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { FolderInput, Languages, Mail, Monitor, Moon, RefreshCw, Sun, SunMoon, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { PageHeader } from "@/components/layout/AppLayout"
import { ModelSettings } from "@/components/ModelSettings"
import { useInvalidateAll } from "@/hooks/queries"
import { useLocale, useT } from "@/i18n"
import { settings as messages } from "@/i18n/messages/settings"
import { api, type ImportSettings, type Preferences, type PreferencesUpdate, type Theme } from "@/lib/api"
import { countryName, countryOptions } from "@/lib/countries"
import { currentLocale, formatDateTime } from "@/lib/format"
import { cn } from "@/lib/utils"

// Language names are written in their own language, so that anyone can find theirs.
const LANGUAGE_NAMES = { en: "English", fr: "Français" } as const
const AUTO = "auto"

function LastCheck({ at, error }: { at: string | null; error: string | null }) {
  const t = useT(messages)
  if (error) return <p className="text-xs text-red-600 dark:text-red-400">{t("lastCheck.error", { error })}</p>
  if (!at) return <p className="text-xs text-muted-foreground">{t("lastCheck.never")}</p>
  return <p className="text-xs text-muted-foreground">{t("lastCheck.at", { date: formatDateTime(at) })}</p>
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
      <input type="checkbox" className="size-4 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

function CardHeading({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300">
        <Icon className="size-4" />
      </span>
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const t = useT(messages)
  const settings = useQuery({ queryKey: ["import-settings"], queryFn: api.importSettings })
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


  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="space-y-8">
        <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
          <RegionCard />
          <AppearanceCard />
        </div>
        <ModelSettings />
        <section className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{t("import.title")}</h2>
              <p className="text-sm text-muted-foreground">{t("import.description")}</p>
            </div>
            <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
              <RefreshCw className={run.isPending ? "animate-spin" : ""} /> {t("import.check")}
            </Button>
          </div>
          {settings.data && (
            <div className="grid gap-6 lg:grid-cols-2">
              <FolderCard settings={settings.data} />
              <MailCard settings={settings.data} />
            </div>
          )}
        </section>
      </div>
    </>
  )
}

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
    <Card className="gap-4 p-5">
      <CardHeading icon={Languages} title={t("region.title")} description={t("region.description")} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="pref-language">{t("language.label")}</Label>
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
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pref-country">{t("country.label")}</Label>
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
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">{t("country.hint")}</p>
        <p className="text-xs font-medium">{t("currency", money)}</p>
      </div>
    </Card>
  )
}

const THEMES: { value: Theme; icon: LucideIcon }[] = [
  { value: "system", icon: Monitor },
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
]

function AppearanceCard() {
  const t = useT(messages)
  const { theme } = useLocale()
  const save = useSavePreference()
  return (
    <Card className="gap-4 p-5">
      <CardHeading icon={SunMoon} title={t("appearance.title")} description={t("appearance.description")} />
      <div className="space-y-1.5">
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
                "flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
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
  useEffect(() => {
    setEnabled(settings.folder.enabled)
    setPath(settings.folder.path)
  }, [settings.folder.enabled, settings.folder.path])

  return (
    <Card className="gap-4 p-5">
      <CardHeading icon={FolderInput} title={t("folder.title")} description={t("folder.description")} />
      <Toggle checked={enabled} onChange={setEnabled} label={t("folder.toggle")} />
      <div className="space-y-1.5">
        <Label htmlFor="watch-path">{t("folder.path")}</Label>
        <Input id="watch-path" value={path} onChange={(e) => setPath(e.target.value)} placeholder="~/Documents/Scans" />
      </div>
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
    <Card className="gap-4 p-5">
      <CardHeading icon={Mail} title={t("mail.title")} description={t("mail.description")} />
      <Toggle checked={form.enabled} onChange={(enabled) => set({ enabled })} label={t("mail.toggle")} />
      <div className="grid grid-cols-[1fr_90px] gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="imap-host">{t("mail.host")}</Label>
          <Input id="imap-host" value={form.host} onChange={(e) => set({ host: e.target.value })} placeholder="imap.gmail.com" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imap-port">{t("mail.port")}</Label>
          <Input id="imap-port" type="number" value={form.port} onChange={(e) => set({ port: Number(e.target.value) })} />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="imap-user">{t("mail.user")}</Label>
          <Input id="imap-user" value={form.user} onChange={(e) => set({ user: e.target.value })} autoComplete="off" />
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
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="imap-folder">{t("mail.folder")}</Label>
          <Input id="imap-folder" value={form.folder} onChange={(e) => set({ folder: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imap-since">{t("mail.since")}</Label>
          <Input id="imap-since" type="number" min={1} max={365} value={form.since_days} onChange={(e) => set({ since_days: Number(e.target.value) })} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{t("mail.passwordNote")}</p>
      <LastCheck at={m.last_check} error={m.last_error} />
      <div>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {t("save")}
        </Button>
      </div>
    </Card>
  )
}
