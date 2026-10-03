import { useMemo, type ReactNode } from "react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useLocale } from "@/i18n"
import { glossary } from "@/i18n/messages/glossary"

interface Entry {
  id: string
  def: string
}

// Per language: the matcher over every term (longest first, so that "recommandé avec accusé de
// réception" wins over "recommandé") and the entry of each lower-cased term.
const cache = new Map<string, { pattern: RegExp; entries: Map<string, Entry> }>()

function matcher(language: "en" | "fr") {
  let found = cache.get(language)
  if (found) return found
  const dict = glossary[language] as Record<string, string>
  const entries = new Map<string, Entry>()
  for (const [key, value] of Object.entries(dict)) {
    if (!key.endsWith(".terms")) continue
    const id = key.slice(0, -".terms".length)
    for (const term of value.split("|")) entries.set(term.toLowerCase(), { id, def: dict[`${id}.def`] ?? "" })
  }
  const escaped = [...entries.keys()]
    .sort((a, b) => b.length - a.length)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
  // Whole words only: "TVA" in "TVA", not in "TVAX"; letters include accents.
  found = { pattern: new RegExp(`(?<![\\p{L}\\d])(?:${escaped.join("|")})(?![\\p{L}\\d])`, "giu"), entries }
  cache.set(language, found)
  return found
}

/** An administrative word, dotted: tap it for its explanation in one sentence. */
export function Term({ children, definition }: { children: ReactNode; definition: string }) {
  return (
    <Popover>
      <PopoverTrigger
        className="cursor-help rounded-sm underline decoration-primary/70 decoration-dotted decoration-2 underline-offset-[3px] outline-none hover:decoration-primary focus-visible:ring-2 focus-visible:ring-ring"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3 text-sm leading-snug font-normal text-popover-foreground">
        {definition}
      </PopoverContent>
    </Popover>
  )
}

/** `text` with the glossary's words made tappable (the first time each one appears). Do not use
 * inside a button or a link: the words are buttons themselves. */
export function Glossed({ text }: { text: string }) {
  const { language } = useLocale()
  const parts = useMemo(() => {
    const { pattern, entries } = matcher(language)
    const seen = new Set<string>()
    const out: ReactNode[] = []
    let last = 0
    for (const match of text.matchAll(pattern)) {
      const entry = entries.get(match[0].toLowerCase())
      if (!entry || seen.has(entry.id)) continue
      seen.add(entry.id)
      out.push(text.slice(last, match.index))
      out.push(
        <Term key={match.index} definition={entry.def}>
          {match[0]}
        </Term>,
      )
      last = match.index + match[0].length
    }
    out.push(text.slice(last))
    return out
  }, [text, language])
  return <>{parts}</>
}
