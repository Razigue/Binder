import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useNavigationType } from "react-router-dom"
import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react"
import { useT } from "@/i18n"
import { layout } from "@/i18n/messages/layout"
import { cn } from "@/lib/utils"

export interface HistoryPosition {
  canBack: boolean
  canForward: boolean
}

// React Router numbers its history entries (`state.idx`); the furthest one reached tells whether
// there is somewhere to go forward.
const indexOf = (state: unknown) => (state as { idx?: number } | null)?.idx ?? 0

/** Where the window stands in its history. Use it once. */
export function useHistoryPosition(): HistoryPosition {
  const { key } = useLocation()
  const type = useNavigationType()
  const idx = indexOf(window.history.state)
  const [seen, setSeen] = useState({ key, idx, furthest: idx })
  // A new page drops the entries ahead of it; going back and forth keeps them.
  if (seen.key !== key) setSeen({ key, idx, furthest: type === "PUSH" ? idx : Math.max(seen.furthest, idx) })
  return { canBack: seen.idx > 0, canForward: seen.idx < seen.furthest }
}

/**
 * A new page opens at its top; going back returns where the user was. `scroller` is the element
 * that scrolls (the area under the desktop title bar), or null for the window.
 */
export function useScrollMemory(scroller: React.RefObject<HTMLElement | null>) {
  const location = useLocation()
  const type = useNavigationType()
  const positions = useRef(new Map<string, number>())
  const shown = useRef({ key: location.key, pathname: location.pathname })

  useEffect(() => {
    const save = (e: Event) => {
      const el = scroller.current
      if (el ? e.target === el : e.target === document) {
        positions.current.set(shown.current.key, el ? el.scrollTop : window.scrollY)
      }
    }
    document.addEventListener("scroll", save, { capture: true, passive: true })
    return () => document.removeEventListener("scroll", save, { capture: true })
  }, [scroller])

  useLayoutEffect(() => {
    const previous = shown.current
    shown.current = { key: location.key, pathname: location.pathname }
    if (previous.key === location.key) return
    // A filter or a tab kept in the address stays where it is.
    if (type !== "POP" && previous.pathname === location.pathname) {
      positions.current.set(location.key, positions.current.get(previous.key) ?? 0)
      return
    }
    const top = type === "POP" ? (positions.current.get(location.key) ?? 0) : 0
    const target = scroller.current ?? window
    target.scrollTo({ top })
  }, [location.key, location.pathname, type, scroller])
}

/** Back and forward, as in a browser: also Alt + ← / → and the mouse side buttons. */
export function HistoryButtons({ position, className, buttonClassName }: {
  position: HistoryPosition
  className?: string
  buttonClassName?: string
}) {
  const t = useT(layout)
  const navigate = useNavigate()
  const button = cn(
    "flex items-center justify-center rounded-md text-foreground/80 outline-none transition-colors hover:bg-foreground/[0.07] hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring active:bg-foreground/[0.12] disabled:pointer-events-none disabled:text-foreground/25",
    buttonClassName,
  )
  // Nowhere to go yet (the first page): two dead arrows would only read as broken. The space is
  // kept, so nothing moves when they appear.
  const idle = !position.canBack && !position.canForward
  return (
    <div className={cn("flex items-center gap-0.5", idle && "invisible", className)}>
      <button
        type="button"
        className={button}
        disabled={!position.canBack}
        onClick={() => navigate(-1)}
        aria-label={t("history.back")}
        title={t("history.backHint")}
      >
        <ArrowLeftIcon className="size-4" weight="bold" />
      </button>
      <button
        type="button"
        className={button}
        disabled={!position.canForward}
        onClick={() => navigate(1)}
        aria-label={t("history.forward")}
        title={t("history.forwardHint")}
      >
        <ArrowRightIcon className="size-4" weight="bold" />
      </button>
    </div>
  )
}
