import { createContext } from "react"
import type { Preferences, PreferencesUpdate, TextSize, Theme } from "@/lib/api"
import type { Language } from "./core"

export interface I18nContextValue {
  language: Language
  country: string | null
  currency: string
  theme: Theme
  textSize: TextSize
  resolvedTheme: "light" | "dark"
  /** Saved preferences, including what the operating system reports. */
  preferences: Preferences | undefined
  update: (patch: PreferencesUpdate) => Promise<Preferences>
}

export const I18nContext = createContext<I18nContextValue | null>(null)
