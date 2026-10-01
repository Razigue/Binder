import { createContext, Fragment, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api, type Preferences, type PreferencesUpdate, type Theme } from "@/lib/api"
import { setFormatLocale } from "@/lib/format"
import { detectBrowserCountry, detectBrowserLanguage, translate, type Dict, type Language, type Messages, type Translate } from "./core"

export { defineMessages, type Language } from "./core"

// Last known choices, to render the first frame in the right language and theme before the
// preferences arrive from the backend.
const STORAGE_KEY = "binder.preferences"

interface Cached {
  language: Language
  country: string | null
  currency: string
  theme: Theme
}

function readCache(): Cached | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Cached) : null
  } catch {
    return null
  }
}

function writeCache(value: Cached) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Storage unavailable: the backend stays the source of truth.
  }
}

interface I18nContextValue {
  language: Language
  country: string | null
  currency: string
  theme: Theme
  resolvedTheme: "light" | "dark"
  /** Saved preferences, including what the operating system reports. */
  preferences: Preferences | undefined
  update: (patch: PreferencesUpdate) => Promise<Preferences>
}

const I18nContext = createContext<I18nContextValue | null>(null)

function useSystemDark(): boolean {
  const query = "(prefers-color-scheme: dark)"
  const [dark, setDark] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = () => setDark(media.matches)
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [])
  return dark
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: ["preferences"], queryFn: api.preferences, staleTime: Infinity })
  const prefs = query.data
  const cached = useMemo(readCache, [])

  const language: Language =
    (prefs?.effective_language as Language | undefined) ?? cached?.language ?? detectBrowserLanguage()
  const country = prefs ? prefs.effective_country : (cached?.country ?? detectBrowserCountry())
  const currency = prefs?.currency ?? cached?.currency ?? "EUR"
  const theme: Theme = prefs?.theme ?? cached?.theme ?? "system"
  const systemDark = useSystemDark()
  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme

  // Formatting must be ready before children render.
  useMemo(() => setFormatLocale(language, country, currency), [language, country, currency])

  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", resolvedTheme === "dark")
    root.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  useEffect(() => {
    if (prefs) writeCache({ language, country, currency, theme })
  }, [prefs, language, country, currency, theme])

  const mutation = useMutation({
    mutationFn: api.updatePreferences,
    onSuccess: (data, patch) => {
      qc.setQueryData(["preferences"], data)
      // Server-rendered text (agent answers, explanations, activity log…) follows the language.
      if ("language" in patch || "country" in patch) {
        void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "preferences" })
      }
    },
  })

  const value = useMemo<I18nContextValue>(
    () => ({
      language,
      country,
      currency,
      theme,
      resolvedTheme,
      preferences: prefs,
      update: (patch) => mutation.mutateAsync(patch),
    }),
    [language, country, currency, theme, resolvedTheme, prefs, mutation],
  )

  return (
    <I18nContext.Provider value={value}>
      {/* Remount on locale change so that every formatted value is recomputed. */}
      <Fragment key={`${language}-${country}-${currency}`}>{children}</Fragment>
    </I18nContext.Provider>
  )
}

export function useLocale(): I18nContextValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error("useLocale must be used inside I18nProvider")
  return ctx
}

/** Translator for one namespace: `const t = useT(home)` then `t("title")`, `t("docs", { count })`. */
export function useT<E extends Dict>(messages: Messages<E>): Translate<E> {
  const { language } = useLocale()
  return useMemo(() => translate(messages, language), [messages, language])
}
