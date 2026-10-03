import { cloneElement, isValidElement, type KeyboardEvent, type ReactNode } from "react"
import type { Icon } from "@phosphor-icons/react"
import { Label } from "@/components/ui/label"
import { useT } from "@/i18n"
import { settings as messages } from "@/i18n/messages/settings"
import { formatDateTime } from "@/lib/format"
import { cn } from "@/lib/utils"

/** A settings group: what it is about on the left, its cards on the right (stacked on small screens). */
export function Section({ id, title, description, action, children }: { id?: string; title: string; description: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 grid gap-4 py-8 first:pt-0 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-10 xl:grid-cols-[20rem_minmax(0,1fr)]">
      <div className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
        {action}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}

/** The icon tile of a card, beside the line that names it. */
export function IconTile({ icon: Icon, tone = "accent" }: { icon: Icon; tone?: "accent" | "destructive" }) {
  return (
    <span
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-lg",
        tone === "accent" ? "bg-accent text-primary" : "bg-destructive/10 text-destructive",
      )}
    >
      <Icon className="size-5" />
    </span>
  )
}

export function CardHeading({ icon, title, description }: { icon: Icon; title: string; description?: string }) {
  return (
    <div className="flex items-start gap-3">
      <IconTile icon={icon} />
      <div className="min-w-0">
        <h3 className="font-semibold">{title}</h3>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
    </div>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex min-h-10 cursor-pointer items-center gap-3 text-sm font-medium">
      <input type="checkbox" className="size-5 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

export function Field({ id, label, hint, className, children }: { id: string; label: string; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {/* The hint is read with the field, not only seen under it. */}
      {hint && isValidElement<{ "aria-describedby"?: string }>(children)
        ? cloneElement(children, { "aria-describedby": `${id}-hint` })
        : children}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}

export function LastCheck({ at, error }: { at: string | null; error: string | null }) {
  const t = useT(messages)
  if (error) return <p className="text-xs text-red-600 dark:text-red-400">{t("lastCheck.error", { error })}</p>
  return (
    <p className="text-xs text-muted-foreground">{at ? t("lastCheck.at", { date: formatDateTime(at) }) : t("lastCheck.never")}</p>
  )
}

/** Segmented choice (a radio group): arrows move to the next choice and pick it, like native
 * radio buttons. */
export function ChoiceGroup<V extends string>({
  labelId,
  label,
  value,
  options,
  onChange,
}: {
  labelId: string
  label: string
  value: V
  options: { value: V; content: ReactNode }[]
  onChange: (value: V) => void
}) {
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0
    if (!step) return
    e.preventDefault()
    const i = (options.findIndex((o) => o.value === value) + step + options.length) % options.length
    const next = options[i]
    if (next) onChange(next.value)
    e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[i]?.focus()
  }
  return (
    <div className="space-y-2">
      <p id={labelId} className="text-sm font-medium">
        {label}
      </p>
      <div role="radiogroup" aria-labelledby={labelId} className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            tabIndex={value === option.value ? 0 : -1}
            onKeyDown={onKeyDown}
            onClick={() => value !== option.value && onChange(option.value)}
            className={cn(
              "flex min-h-10 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring",
              value === option.value
                ? "bg-card text-foreground shadow-sm ring-1 ring-foreground/5"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.content}
          </button>
        ))}
      </div>
    </div>
  )
}
