import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { keys } from "@/hooks/queries"
import { api, type TextSize, type Theme } from "@/lib/api"
import { setFormatLocale } from "@/lib/format"
import { I18nContext, type I18nContextValue } from "./context"
import { detectBrowserCountry, detectBrowserLanguage, type Language } from "./core"

// Last known choices, to render the first frame in the right language and theme before the
// preferences arrive from the backend.
const STORAGE_KEY = "binder.preferences"

interface Cached {
  language: Language
  country: string | null
  currency: string
  theme: Theme
  textSize?: TextSize
}

// Root font size per text size: rem-based sizes and spacing follow, the layout scales as a whole.
const ROOT_SIZE: Record<TextSize, string> = { normal: "100%", large: "112.5%", larger: "125%" }

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
  const query = useQuery({ queryKey: keys.preferences, queryFn: api.preferences, staleTime: Infinity })
  const prefs = query.data
  const [cached] = useState(readCache)

  const language: Language =
    (prefs?.effective_language as Language | undefined) ?? cached?.language ?? detectBrowserLanguage()
  const country = prefs ? prefs.effective_country : (cached?.country ?? detectBrowserCountry())
  const currency = prefs?.currency ?? cached?.currency ?? "EUR"
  const theme: Theme = prefs?.theme ?? cached?.theme ?? "system"
  const textSize: TextSize = prefs?.text_size ?? cached?.textSize ?? "normal"
  const systemDark = useSystemDark()
  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme

  // Formatting must be ready before children render (idempotent: the same values set again).
  setFormatLocale(language, country, currency)

  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", resolvedTheme === "dark")
    root.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  useEffect(() => {
    document.documentElement.style.fontSize = ROOT_SIZE[textSize] ?? ROOT_SIZE.normal
  }, [textSize])

  useEffect(() => {
    if (prefs) writeCache({ language, country, currency, theme, textSize })
  }, [prefs, language, country, currency, theme, textSize])

  const mutation = useMutation({
    mutationFn: api.updatePreferences,
    onSuccess: (data, patch) => {
      qc.setQueryData(keys.preferences, data)
      // Server-rendered text (agent answers, explanations, activity log…) follows the language.
      if ("language" in patch || "country" in patch) {
        void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== keys.preferences[0] })
      }
    },
  })

  const value = useMemo<I18nContextValue>(
    () => ({
      language,
      country,
      currency,
      theme,
      textSize,
      resolvedTheme,
      preferences: prefs,
      update: (patch) => mutation.mutateAsync(patch),
    }),
    [language, country, currency, theme, textSize, resolvedTheme, prefs, mutation],
  )

  return (
    <I18nContext value={value}>
      {/* Remount on locale change so that every formatted value is recomputed. */}
      <Fragment key={`${language}-${country}-${currency}`}>{children}</Fragment>
    </I18nContext>
  )
}
