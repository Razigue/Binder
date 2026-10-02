import { Fragment, type ReactNode } from "react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useT } from "@/i18n"
import { glossary as messages } from "@/i18n/messages/glossary"

type Term = Exclude<keyof (typeof messages)["en"], "explain">

// Words as they appear in French documents and in either language of the interface.
const TERMS: [Term, RegExp][] = [
  ["rib", /\bRIB\b/],
  ["iban", /\bIBAN\b/],
  ["rent_receipt", /quittances? de loyer|rent receipts?/i],
  ["tax_notice", /avis d'(?:imposition|impôt)|tax notice/i],
  ["property_tax", /taxe foncière|property tax/i],
  ["withholding", /prélèvement à la source|withholding tax/i],
  ["caf", /\bCAF\b/],
  ["overpayment", /trop-perçu|overpayment/i],
  ["formal_notice", /mise en demeure|formal notice/i],
  ["notice_period", /préavis|notice period/i],
  ["supplementary", /\bmutuelle\b|supplementary (?:health )?insurance/i],
  ["rfr", /revenu fiscal de référence|reference tax income/i],
  ["registration", /carte grise|vehicle registration/i],
  ["roadworthiness", /contrôle technique|roadworthiness test/i],
  ["payment_notice", /avis d'échéance|payment notice/i],
  ["charges", /régularisation des charges|service charges/i],
  ["termination", /résiliation|termination/i],
]

/** Text with its paperwork words explained: each known term (first time it appears) is a
 * button that shows one sentence. */
export function GlossaryText({ text }: { text: string }) {
  const t = useT(messages)
  if (!text) return null
  const found: { start: number; end: number; term: Term }[] = []
  for (const [term, pattern] of TERMS) {
    const m = pattern.exec(text)
    if (!m) continue
    const start = m.index
    const end = start + m[0].length
    if (found.some((f) => start < f.end && end > f.start)) continue
    found.push({ start, end, term })
  }
  if (!found.length) return <>{text}</>
  found.sort((a, b) => a.start - b.start)
  const parts: ReactNode[] = []
  let last = 0
  for (const f of found) {
    parts.push(<Fragment key={`t${f.start}`}>{text.slice(last, f.start)}</Fragment>)
    const word = text.slice(f.start, f.end)
    parts.push(
      <Popover key={`g${f.start}`}>
        <PopoverTrigger
          render={<button type="button" />}
          aria-label={t("explain", { term: word })}
          className="cursor-help underline decoration-dotted underline-offset-2 hover:decoration-solid"
        >
          {word}
        </PopoverTrigger>
        <PopoverContent className="w-72 text-sm">
          <p className="font-medium">{word}</p>
          <p className="mt-1 text-muted-foreground">{t(f.term)}</p>
        </PopoverContent>
      </Popover>,
    )
    last = f.end
  }
  parts.push(<Fragment key="end">{text.slice(last)}</Fragment>)
  return <>{parts}</>
}
