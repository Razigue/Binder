import { useState } from "react"
import { CalendarDotsIcon } from "@phosphor-icons/react"
import { Input } from "@/components/ui/input"
import { Glossed } from "@/components/glossary"
import { useT } from "@/i18n"
import { common } from "@/i18n/messages/common"
import { documentDetail } from "@/i18n/messages/documentDetail"
import { DOC_TYPES, type DocDetail } from "@/lib/api"
import { docTypeLabel, doubtLabel, fieldLabel, formatAmount, formatDate, parseDate } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Draft } from "./draft"

const selectClass = "h-8 w-full rounded-md border bg-background px-2 text-sm"

type Row = { key: keyof Draft; type: "text" | "number" | "date" | "docType"; display: string }

const DAY_MS = 86_400_000

/** What Binder read on the document, field by field; each field can be corrected while `draft`
 * is given. Hovering a field highlights where it was read on the page. */
export function DocumentFields({
  doc,
  draft,
  onDraft,
  onActive,
}: {
  doc: DocDetail
  draft: Draft | null
  onDraft: (draft: Draft) => void
  onActive: (field: string | null) => void
}) {
  const t = useT(documentDetail)
  const tc = useT(common)
  // Read once: "due soon" does not change while the page is open.
  const [now] = useState(Date.now)
  const missing = new Set(doc.missing_fields)
  // Doubts of the reading ("unverified:due_date"), by field: highlighted, value kept.
  const doubts = new Map(
    doc.missing_fields.flatMap((f) => {
      const field = f.split(":")[1]
      return field ? [[field, doubtLabel(f)] as const] : []
    }),
  )
  const dueSoon = doc.due_date ? (parseDate(doc.due_date).getTime() - now) / DAY_MS < 15 : false

  const rows: Row[] = [
    { key: "amount", type: "number", display: formatAmount(doc.amount) },
    { key: "issue_date", type: "date", display: formatDate(doc.issue_date) },
    { key: "due_date", type: "date", display: formatDate(doc.due_date) },
    { key: "expiry_date", type: "date", display: formatDate(doc.expiry_date) },
    { key: "reference", type: "text", display: doc.reference ?? "—" },
    { key: "issuer", type: "text", display: doc.issuer ?? "—" },
    { key: "person", type: "text", display: doc.person ?? "—" },
    { key: "doc_type", type: "docType", display: docTypeLabel(doc.doc_type) },
  ]
  // Breakdown read from the document, shown when it says more than the main amount.
  const details: { key: string; display: string }[] = [
    { key: "amount_ht", value: doc.amount_ht },
    { key: "amount_tva", value: doc.amount_tva },
    { key: "amount_ttc", value: doc.amount_ttc !== doc.amount ? doc.amount_ttc : null },
    { key: "amount_due", value: doc.amount_due !== doc.amount ? doc.amount_due : null },
  ]
    .filter((d) => d.value != null)
    .map((d) => ({ key: d.key, display: formatAmount(d.value ?? null) }))
  if (doc.period_start && doc.period_end)
    details.push({ key: "period", display: `${formatDate(doc.period_start)} – ${formatDate(doc.period_end)}` })
  if (doc.iban) details.push({ key: "iban", display: doc.iban })
  if (doc.siret) details.push({ key: "siret", display: doc.siret })
  // Keep a legacy value that is not a known type selectable, so that saving does not drop it.
  const docTypes: string[] =
    draft?.doc_type && !(DOC_TYPES as readonly string[]).includes(draft.doc_type) ? [...DOC_TYPES, draft.doc_type] : [...DOC_TYPES]

  return (
    <dl className="divide-y text-sm">
      {rows.map((row) => {
        const isMissing = missing.has(row.key)
        const doubt = doubts.get(row.key)
        const highlight = row.key === "due_date" && doc.due_date && dueSoon
        const label = fieldLabel(row.key)
        return (
          <div
            key={row.key}
            onMouseEnter={() => onActive(row.key)}
            onMouseLeave={() => onActive(null)}
            className={cn(
              "grid grid-cols-[140px_1fr] items-center gap-3 px-2 py-2.5",
              highlight && "rounded-md bg-red-50/70 text-red-600 dark:bg-red-500/10 dark:text-red-400",
              (isMissing || doubt) && "rounded-md bg-amber-50/70 dark:bg-amber-500/10",
            )}
          >
            <dt className={cn("text-muted-foreground", highlight && "text-red-600 dark:text-red-400")}>
              <Glossed text={label} />
            </dt>
            <dd className="font-medium">
              {draft && row.type === "docType" ? (
                <select
                  value={draft.doc_type ?? ""}
                  onChange={(e) => onDraft({ ...draft, doc_type: e.target.value || null })}
                  aria-label={label}
                  className={selectClass}
                >
                  <option value="">{tc("empty")}</option>
                  {docTypes.map((type) => (
                    <option key={type} value={type}>
                      {docTypeLabel(type)}
                    </option>
                  ))}
                </select>
              ) : draft ? (
                <Input
                  type={row.type}
                  step={row.type === "number" ? "0.01" : undefined}
                  value={draft[row.key] ?? ""}
                  onChange={(e) => {
                    const v = e.target.value
                    onDraft({ ...draft, [row.key]: v === "" ? null : row.type === "number" ? Number(v) : v })
                  }}
                  aria-label={label}
                  className="h-8"
                />
              ) : isMissing ? (
                <span className="text-amber-700 dark:text-amber-400">{t("toComplete")}</span>
              ) : doubt && row.display === "—" ? (
                <span className="text-amber-700 dark:text-amber-400">{doubt}</span>
              ) : (
                <>
                  <span className="flex items-center gap-1.5">
                    {highlight && <CalendarDotsIcon className="size-3.5" aria-hidden />}
                    {row.key === "doc_type" ? <Glossed text={row.display} /> : row.display}
                    {highlight && <span className="sr-only">, {t("dueSoon")}</span>}
                  </span>
                  {/* The doubt in words, not only as the amber tint. */}
                  {doubt && (
                    <span className="mt-0.5 block text-xs font-normal text-amber-700 dark:text-amber-400">{doubt}</span>
                  )}
                </>
              )}
            </dd>
          </div>
        )
      })}
      {!draft &&
        details.map((d) => (
          <div key={d.key} className="grid grid-cols-[140px_1fr] items-center gap-3 px-2 py-2.5">
            <dt className="text-muted-foreground">
              <Glossed text={fieldLabel(d.key)} />
            </dt>
            <dd className="font-medium tabular-nums">{d.display}</dd>
          </div>
        ))}
    </dl>
  )
}
