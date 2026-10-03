import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/** A page's tabs: arrow keys, Home and End move between them; Tab goes on to the panel. */
export function TabList<T extends string>({
  id,
  label,
  tabs,
  value,
  onChange,
  labelOf,
  className,
}: {
  /** Prefix of the tab and panel ids. */
  id: string
  label: string
  tabs: readonly T[]
  value: T
  onChange: (tab: T) => void
  labelOf: (tab: T) => string
  className?: string
}) {
  return (
    <div role="tablist" aria-label={label} className={cn("flex gap-1 border-b", className)}>
      {tabs.map((key, i) => (
        <button
          key={key}
          type="button"
          id={`${id}-tab-${key}`}
          role="tab"
          aria-selected={value === key}
          aria-controls={`${id}-panel`}
          tabIndex={value === key ? 0 : -1}
          onClick={() => onChange(key)}
          onKeyDown={(e) => {
            const next =
              e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length]
              : e.key === "ArrowLeft" ? tabs[(i - 1 + tabs.length) % tabs.length]
              : e.key === "Home" ? tabs[0]
              : e.key === "End" ? tabs[tabs.length - 1]
              : undefined
            if (next === undefined) return
            e.preventDefault()
            onChange(next)
            document.getElementById(`${id}-tab-${next}`)?.focus()
          }}
          className={cn(
            "-mb-px min-h-11 shrink-0 border-b-2 px-3 py-2 text-[0.9375rem] font-medium transition-colors",
            value === key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {labelOf(key)}
        </button>
      ))}
    </div>
  )
}

/** The panel of the tab shown, named by its tab. */
export function TabPanel({ id, value, className, children }: { id: string; value: string; className?: string; children: ReactNode }) {
  return (
    <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-tab-${value}`} className={className}>
      {children}
    </div>
  )
}
