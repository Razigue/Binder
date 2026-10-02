import { translate, type Language } from "@/i18n/core"
import { common } from "@/i18n/messages/common"

// Formatting follows the current locale, set by I18nProvider (language, country, currency).
// The provider remounts the app when it changes, so plain functions are enough here.
let language: Language = "en"
let locale = "en"
let money = new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" })
let moneyRound = new Intl.NumberFormat(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 })
let t = translate(common, language)

export function setFormatLocale(lang: Language, country: string | null, currency: string) {
  language = lang
  locale = country ? `${lang}-${country}` : lang
  try {
    money = new Intl.NumberFormat(locale, { style: "currency", currency })
  } catch {
    locale = lang
    money = new Intl.NumberFormat(locale, { style: "currency", currency: "EUR" })
  }
  moneyRound = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: money.resolvedOptions().currency,
    maximumFractionDigits: 0,
  })
  t = translate(common, language)
}

/** BCP 47 locale for Intl APIs, e.g. "fr-FR" or "en-GB". */
export function currentLocale(): string {
  return locale
}

export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return Number.isInteger(value) ? moneyRound.format(value) : money.format(value)
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(locale, options).format(value)
}

export function parseDate(iso: string): Date {
  // UTC date-time (created_at, deleted_at…): local day, not the UTC day.
  if (iso.length > 10) {
    const local = new Date(iso)
    return new Date(local.getFullYear(), local.getMonth(), local.getDate())
  }
  const [y, m, d] = iso.split("-").map(Number)
  return new Date(y, m - 1, d)
}

export function formatDate(iso: string | null | undefined, style: "short" | "long" | "day" = "short"): string {  if (!iso) return "—"
  const date = parseDate(iso)
  if (style === "long") return date.toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })
  // "short" and "day" share the abbreviated month: an all-numeric date reads differently in
  // the US and in Europe (10/6 is October 6th or June 10th).
  return date.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" })
}

export function formatDateTime(iso: string, options: Intl.DateTimeFormatOptions = { dateStyle: "short", timeStyle: "short" }): string {
  return new Intl.DateTimeFormat(locale, options).format(new Date(iso))
}

export function toIso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function daysLabel(days: number): string {
  if (days < 0) return t("days.late", { count: -days })
  if (days === 0) return t("days.today")
  if (days === 1) return t("days.tomorrow")
  return t("days.in", { count: days })
}

export type Urgency = "late" | "urgent" | "soon" | "later"

export function urgency(days: number): Urgency {
  if (days < 0) return "late"
  if (days <= 7) return "urgent"
  if (days <= 14) return "soon"
  return "later"
}

export const urgencyStyles: Record<Urgency, { dot: string; pill: string; text: string }> = {
  late: { dot: "bg-red-600", pill: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300", text: "text-red-600 dark:text-red-400" },
  urgent: { dot: "bg-red-500", pill: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300", text: "text-red-600 dark:text-red-400" },
  soon: { dot: "bg-amber-500", pill: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300", text: "text-amber-700 dark:text-amber-400" },
  later: { dot: "bg-emerald-500", pill: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300", text: "text-emerald-700 dark:text-emerald-400" },
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return t("size.bytes", { value: bytes })
  if (bytes < 1024 * 1024) return t("size.kb", { value: formatNumber(bytes / 1024, { maximumFractionDigits: 0 }) })
  return t("size.mb", { value: formatNumber(bytes / 1024 / 1024, { maximumFractionDigits: 1 }) })
}

export function fieldLabel(field: string): string {
  const key = `field.${field}` as const
  return key in common.en ? t(key as keyof typeof common.en) : field
}

export function categoryLabel(category: string): string {
  const key = `category.${category}`
  return key in common.en ? t(key as keyof typeof common.en) : category
}

export function docTypeLabel(docType: string | null | undefined): string {
  if (!docType) return "—"
  const key = `docType.${docType}`
  return key in common.en ? t(key as keyof typeof common.en) : docType
}

/** "unverified:due_date" → "Not found in the text" (a doubt raised when reading). */
export function doubtLabel(doubt: string): string | null {
  const key = `doubt.${doubt.split(":")[0]}`
  return key in common.en ? t(key as keyof typeof common.en) : null
}

export function missingLabel(fields: string[]): string {
  if (fields.includes("text")) return t("missing.text")
  if (fields.includes("duplicate")) return t("missing.duplicate")
  const doubt = fields.map(doubtLabel).find(Boolean)
  if (doubt) return doubt
  if (fields.length === 0) return t("missing.none")
  if (fields.length > 1) return t("missing.several")
  const key = `missing.${fields[0]}`
  return key in common.en ? t(key as keyof typeof common.en) : t("missing.several")
}
