import { useEffect, useState, type ReactNode } from "react"
import { CheckIcon, CopyIcon, FileTextIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { cn } from "@/lib/utils"

/** The small buttons under a message: shown on hover or focus, always on touch screens. */
export function MessageActions({ children, visible = false }: { children: ReactNode; visible?: boolean }) {
  return (
    <div
      className={cn(
        "mt-1 flex gap-0.5 transition-opacity select-none group-hover/answer:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100",
        visible ? "opacity-100" : "opacity-0",
      )}
    >
      {children}
    </div>
  )
}

export function ActionButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      onClick={onClick}
      title={label}
      aria-label={label}
      className="text-muted-foreground"
    >
      {children}
    </Button>
  )
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const t = useT(messages)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])
  return (
    <ActionButton
      label={copied ? t("copied") : (label ?? t("copy"))}
      onClick={() => void navigator.clipboard.writeText(text).then(() => setCopied(true))}
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
    </ActionButton>
  )
}

/** Preview of a document, or a file icon when there is none. */
export function Thumbnail({ src, className }: { src?: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <span
      className={cn(
        "flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted text-muted-foreground",
        className,
      )}
    >
      {src && !failed ? (
        <img src={src} alt="" onError={() => setFailed(true)} className="size-full object-cover" />
      ) : (
        <FileTextIcon className="size-4" />
      )}
    </span>
  )
}
