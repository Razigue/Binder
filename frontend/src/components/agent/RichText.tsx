import { Link } from "react-router-dom"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import type { Doc } from "@/lib/api"

/** Minimal rendering of the agent's text: links [text](url), citations [#id] and **bold**. */
export function RichText({ text, docs, onNavigate }: { text: string; docs: Doc[]; onNavigate: () => void }) {
  const t = useT(messages)
  const parts = text.split(/(\[[^\]]+\]\([^)]+\)|\s?\[#\d+\]|\*\*[^*\n]+\*\*)/g)
  const order = [...new Set([...text.matchAll(/\[#(\d+)\]/g)].map((m) => Number(m[1])))]
  return (
    <>
      {parts.map((part, i) => {
        const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
        // Internal links only ("/documents/3"): the text comes from the model, which a booby-trapped
        // document can influence (javascript:, external site…).
        if (link?.[1] && link[2] && /^\/(?![/\\])/.test(link[2]))
          return (
            <a key={i} href={link[2]} className="font-medium text-primary underline underline-offset-2">
              {link[1]}
            </a>
          )
        const bold = part.match(/^\*\*([^*\n]+)\*\*$/)
        if (bold)
          return (
            <strong key={i} className="font-semibold">
              {bold[1]}
            </strong>
          )
        const cite = part.match(/^\s?\[#(\d+)\]$/)
        if (cite) {
          const id = Number(cite[1])
          const doc = docs.find((d) => d.id === id)
          const label = doc ? t("sourceOf", { title: doc.title }) : t("source")
          return (
            <Link
              key={i}
              to={`/documents/${id}`}
              onClick={onNavigate}
              title={label}
              aria-label={label}
              className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-primary/10 px-1 align-super text-[0.625rem] font-semibold text-primary select-none hover:bg-primary/20 dark:text-foreground"
            >
              {order.indexOf(id) + 1}
            </Link>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}
