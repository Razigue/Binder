import { useMemo } from "react"
import { toast } from "sonner"
import { CircleHalfIcon, MonitorIcon, MoonIcon, SunIcon, type Icon } from "@phosphor-icons/react"
import { Card } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useLocale, useT } from "@/i18n"
import { settings as messages } from "@/i18n/messages/settings"
import type { Preferences, PreferencesUpdate, TextSize, Theme } from "@/lib/api"
import { countryName, countryOptions } from "@/lib/countries"
import { currentLocale } from "@/lib/format"
import { cn } from "@/lib/utils"
import { CardHeading, ChoiceGroup, Field } from "./parts"

// Language names are written in their own language, so that anyone can find theirs.
const LANGUAGE_NAMES = { en: "English", fr: "Français" } as const
const AUTO = "auto"

const isLanguage = (value: string): value is keyof typeof LANGUAGE_NAMES => value in LANGUAGE_NAMES

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

export function RegionCard() {
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
            onValueChange={(value) => {
              const choice: Preferences["language"] | null = value === AUTO ? AUTO : value && isLanguage(value) ? value : null
              if (choice) save({ language: choice })
            }}
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

// The letter drawn at each size, so that the choice shows what it does.
const TEXT_SIZES: { value: TextSize; sample: string }[] = [
  { value: "normal", sample: "text-sm" },
  { value: "large", sample: "text-base" },
  { value: "larger", sample: "text-lg" },
]

export function AppearanceCard() {
  const t = useT(messages)
  const { theme, textSize } = useLocale()
  const save = useSavePreference()
  return (
    <Card className="gap-5 p-6">
      <CardHeading icon={CircleHalfIcon} title={t("appearance.title")} description={t("appearance.description")} />
      <ChoiceGroup
        labelId="pref-theme"
        label={t("theme.label")}
        value={theme}
        onChange={(next) => save({ theme: next })}
        options={THEMES.map(({ value, icon: Icon }) => ({
          value,
          content: (
            <>
              <Icon className="size-4" /> {t(`theme.${value}`)}
            </>
          ),
        }))}
      />
      <ChoiceGroup
        labelId="pref-text-size"
        label={t("textSize.label")}
        value={textSize}
        onChange={(next) => save({ text_size: next })}
        options={TEXT_SIZES.map(({ value, sample }) => ({
          value,
          content: (
            <>
              <span aria-hidden className={cn("font-semibold leading-none", sample)}>
                A
              </span>
              {t(`textSize.${value}`)}
            </>
          ),
        }))}
      />
    </Card>
  )
}
