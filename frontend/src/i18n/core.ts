// Message catalogs: one file per namespace, English and French side by side.
// `defineMessages` checks at compile time that French has exactly the English keys.

export type Language = "en" | "fr"
export const LANGUAGES: Language[] = ["en", "fr"]

export type Dict = Record<string, string>
export type Messages<E extends Dict> = { en: E; fr: { [K in keyof E]: string } }

export function defineMessages<const E extends Dict>(messages: Messages<E>): Messages<E> {
  return messages
}

// Plural forms are `key_one` / `key_other`; callers use `key` with a `count` parameter.
type PluralBase<K> = K extends `${infer B}_one` ? B : K extends `${infer B}_other` ? B : never
export type MessageKey<E extends Dict> = Extract<keyof E, string> | PluralBase<Extract<keyof E, string>>

export type Params = Record<string, string | number>
export type Translate<E extends Dict> = (key: MessageKey<E>, params?: Params) => string

const pluralRules = new Map<Language, Intl.PluralRules>()

function plural(language: Language, count: number): "one" | "other" {
  let rules = pluralRules.get(language)
  if (!rules) pluralRules.set(language, (rules = new Intl.PluralRules(language)))
  return rules.select(count) === "one" ? "one" : "other"
}

export function translate<E extends Dict>(messages: Messages<E>, language: Language): Translate<E> {
  const dict = messages[language] as Dict
  return (key, params) => {
    let template = dict[key]
    if (template === undefined && params && typeof params.count === "number") {
      template = dict[`${key}_${plural(language, params.count)}`]
    }
    if (template === undefined) return key
    if (!params) return template
    return template.replace(/\{(\w+)\}/g, (match, name: string) =>
      name in params ? String(params[name]) : match,
    )
  }
}

export function detectBrowserLanguage(): Language {
  for (const tag of navigator.languages ?? [navigator.language]) {
    const lang = tag.slice(0, 2).toLowerCase()
    if (lang === "en" || lang === "fr") return lang
  }
  return "en"
}

export function detectBrowserCountry(): string | null {
  for (const tag of navigator.languages ?? [navigator.language]) {
    const region = /^[a-z]{2,3}(?:-[A-Za-z]{4})?-([A-Z]{2})\b/i.exec(tag)?.[1]
    if (region) return region.toUpperCase()
  }
  return null
}
