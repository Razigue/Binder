import { useState } from "react"
import { useT } from "@/i18n"
import { textSize as messages } from "@/i18n/messages/textSize"
import { cn } from "@/lib/utils"

const SIZES = { normal: "100%", large: "112.5%", larger: "125%" } as const
type Size = keyof typeof SIZES
const KEY = "binder.textSize"

// A display preference of this screen: kept in the browser, not with the documents.
function stored(): Size {
  try {
    const value = localStorage.getItem(KEY)
    return value && value in SIZES ? (value as Size) : "normal"
  } catch {
    return "normal"
  }
}

/** Sets the root font size: everything is sized in rem, so the whole interface follows. */
export function applyTextSize(size: Size = stored()) {
  document.documentElement.style.fontSize = SIZES[size]
}

/** Text size choice (Settings > Appearance). */
export function TextSizeSetting() {
  const t = useT(messages)
  const [size, setSize] = useState<Size>(stored)
  const choose = (next: Size) => {
    setSize(next)
    applyTextSize(next)
    try {
      localStorage.setItem(KEY, next)
    } catch {
      // Private window: the size still applies until the app is closed.
    }
  }
  return (
    <div className="space-y-2">
      <p id="pref-text-size" className="text-sm font-medium">
        {t("label")}
      </p>
      <div role="radiogroup" aria-labelledby="pref-text-size" className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1">
        {(Object.keys(SIZES) as Size[]).map((value, i) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={size === value}
            onClick={() => choose(value)}
            className={cn(
              "flex min-h-10 items-center justify-center gap-2 rounded-md px-3 py-2 font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              size === value ? "bg-card text-foreground shadow-sm ring-1 ring-foreground/5" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span aria-hidden className={["text-sm", "text-base", "text-lg"][i]}>
              A
            </span>
            <span className="text-sm">{t(value)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
