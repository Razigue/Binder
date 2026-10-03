import { useEffect, useRef, useState } from "react"
import { BinderMark } from "@/components/layout/BinderMark"
import { useT } from "@/i18n"
import { layout } from "@/i18n/messages/layout"
import { HistoryButtons } from "@/components/layout/HistoryNav"
import type { HistoryPosition } from "@/components/layout/history"
import { callDesktop as call } from "@/lib/desktop"
import { cn } from "@/lib/utils"

// Desktop window title bar. On Windows the shell keeps the native frame (Snap, Win + arrows,
// shadow, resizing) but hides its caption: the app draws this bar and hands dragging, the window
// buttons and the Snap Layouts flyout back to Windows through `window.pywebview.api`. Elsewhere
// the native title bar stays and only takes the app's colours. In a browser there is no
// `window.pywebview`: nothing happens.

// Windows' default double-click time.
const DOUBLE_CLICK_MS = 500
// Hover delay before the Snap Layouts flyout, as on the native maximise button.
const SNAP_LAYOUTS_DELAY_MS = 400

/** Whether this window is the active one: the title dims otherwise, as in native captions. */
function useWindowActive() {
  const [active, setActive] = useState(() => document.hasFocus())
  useEffect(() => {
    const on = () => setActive(true)
    const off = () => setActive(false)
    window.addEventListener("focus", on)
    window.addEventListener("blur", off)
    return () => {
      window.removeEventListener("focus", on)
      window.removeEventListener("blur", off)
    }
  }, [])
  return active
}

const buttonClass =
  "flex h-full w-[46px] items-center justify-center text-sidebar-foreground transition-colors duration-100 hover:bg-foreground/[0.07] active:bg-foreground/[0.12]"

export function TitleBar({ maximized, history }: { maximized: boolean; history: HistoryPosition }) {
  const t = useT(layout)
  const active = useWindowActive()
  const lastPress = useRef(0)
  const snapTimer = useRef(0)

  useEffect(() => () => clearTimeout(snapTimer.current), [])

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0 || (e.target instanceof Element && e.target.closest("button, a, input, select, textarea"))) return
    e.preventDefault()
    // Windows' move loop swallows the first click's mouseup, so `dblclick` never fires: spot the
    // second press ourselves.
    if (e.timeStamp - lastPress.current < DOUBLE_CLICK_MS) {
      lastPress.current = 0
      call("toggle_maximize")
    } else {
      lastPress.current = e.timeStamp
      call("drag")
    }
  }

  const cancelSnap = () => clearTimeout(snapTimer.current)

  return (
    <div onMouseDown={onMouseDown} className="flex h-9 shrink-0 items-center border-b bg-sidebar select-none">
      <div className={cn("flex items-center gap-2 px-3.5 transition-opacity", !active && "opacity-55")}>
        <span className="flex size-5 items-center justify-center rounded-[5px] bg-primary text-primary-foreground">
          <BinderMark className="size-3.5" />
        </span>
        <span className="text-[13px] font-medium text-sidebar-foreground">Binder</span>
      </div>
      {/* Back and forward where a browser has them: top left. */}
      <HistoryButtons position={history} buttonClassName="h-7 w-8" />
      {/* Native caption buttons are not in the tab order either: Win + arrows and Alt + F4 remain. */}
      <div className="ml-auto flex h-full">
        <button type="button" tabIndex={-1} aria-label={t("window.minimize")} className={buttonClass} onClick={() => call("minimize")}>
          <Glyph d="M0 5.5h10" />
        </button>
        <button
          type="button"
          tabIndex={-1}
          aria-label={t(maximized ? "window.restore" : "window.maximize")}
          className={buttonClass}
          onClick={() => {
            cancelSnap()
            call("toggle_maximize")
          }}
          onMouseEnter={() => {
            cancelSnap()
            snapTimer.current = window.setTimeout(() => call("snap_layouts"), SNAP_LAYOUTS_DELAY_MS)
          }}
          onMouseLeave={cancelSnap}
          onMouseDown={cancelSnap}
        >
          <Glyph d={maximized ? "M2.5 2.5V.5h7v7h-2M.5 2.5h7v7h-7z" : "M.5.5h9v9h-9z"} />
        </button>
        {/* Windows' own close-hover red, so the bar reads as the system's. */}
        <button
          type="button"
          tabIndex={-1}
          aria-label={t("window.close")}
          className={cn(buttonClass, "hover:bg-[#c42b1c] hover:text-white active:bg-[#c42b1c]/85")}
          onClick={() => call("close")}
        >
          <Glyph d="M.5.5l9 9M9.5.5l-9 9" />
        </button>
      </div>
    </div>
  )
}

/** 10px line glyphs, the size of the native caption icons. */
function Glyph({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 10 10" className="size-2.5" fill="none" stroke="currentColor" strokeWidth={1} aria-hidden="true">
      <path d={d} />
    </svg>
  )
}
