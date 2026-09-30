const euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" })
const euroRound = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 })

export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return Number.isInteger(value) ? euroRound.format(value) : euro.format(value)
}

export function parseDate(iso: string): Date {
  // Date-heure UTC (created_at, deleted_at…) : jour local, pas le jour UTC.
  if (iso.length > 10) {
    const local = new Date(iso)
    return new Date(local.getFullYear(), local.getMonth(), local.getDate())
  }
  const [y, m, d] = iso.split("-").map(Number)
  return new Date(y, m - 1, d)
}

export function formatDate(iso: string | null | undefined, style: "short" | "long" | "day" = "short"): string {
  if (!iso) return "—"
  const date = parseDate(iso)
  if (style === "long") return date.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
  if (style === "day") return date.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })
  return date.toLocaleDateString("fr-FR")
}

export function toIso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function daysLabel(days: number): string {
  if (days < 0) return days === -1 ? "En retard d'1 jour" : `En retard de ${-days} jours`
  if (days === 0) return "Aujourd'hui"
  if (days === 1) return "Demain"
  return `Dans ${days} jours`
}

export type Urgency = "late" | "urgent" | "soon" | "later"

export function urgency(days: number): Urgency {
  if (days < 0) return "late"
  if (days <= 7) return "urgent"
  if (days <= 14) return "soon"
  return "later"
}

export const urgencyStyles: Record<Urgency, { dot: string; pill: string; text: string }> = {
  late: { dot: "bg-red-600", pill: "bg-red-50 text-red-700", text: "text-red-600" },
  urgent: { dot: "bg-red-500", pill: "bg-red-50 text-red-600", text: "text-red-600" },
  soon: { dot: "bg-amber-500", pill: "bg-amber-50 text-amber-700", text: "text-amber-600" },
  later: { dot: "bg-emerald-500", pill: "bg-emerald-50 text-emerald-700", text: "text-emerald-600" },
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`
}

export const FIELD_LABELS: Record<string, string> = {
  amount: "Montant",
  due_date: "Échéance",
  issue_date: "Date d'émission",
  reference: "Référence",
  text: "Texte illisible",
}

export function missingLabel(fields: string[]): string {
  if (fields.includes("text")) return "Texte illisible"
  if (fields.length === 0) return "À confirmer"
  if (fields.length > 1) return "Document incomplet"
  return `${FIELD_LABELS[fields[0]] ?? fields[0]} manquant${fields[0] === "due_date" ? "e" : ""}`
}
