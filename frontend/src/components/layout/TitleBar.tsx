import { useEffect, useRef, useState } from "react"
import { VaultIcon } from "@phosphor-icons/react"
import { useLocale, useT } from "@/i18n"
import { layout } from "@/i18n/messages/layout"
import { cn } from "@/lib/utils"

// Desktop window title bar. On Windows the shell keeps the native frame (Snap, Win + arrows,
// shadow, resizing) but hides its caption: the app draws this bar and hands dragging, the window
// buttons and the Snap Layouts flyout back to Windows through `window.pywebview.api`. Elsewhere
// the native title bar stays and only takes the app's colours. In a browser there is no
// `window.pywebview`: nothing happens.

interface WindowState {
  custom: boolean
  maximized: boolean
}

interface DesktopApi {
  set_title_bar?: (background: string, foreground: string, dark: boolean) => Promise<void>
  window_state?: () => Promise<WindowState>
  drag?: () => Promise<void>
  minimize?: () => Promise<void>
  toggle_maximize?: () => Promise<void>
  snap_layouts?: () => Promise<void>
  close?: () => Promise<void>
}

declare global {
  interface Window {
    pywebview?: { api?: DesktopApi }
  }
}

// Same height as the `h-9` bar: full-window layers (dialogs, sheets) start below it.
const TITLE_BAR_HEIGHT = "2.25rem"
// Windows' default double-click time.
const DOUBLE_CLICK_MS = 500
// Hover delay before the Snap Layouts flyout, as on the native maximise button.
const SNAP_LAYOUTS_DELAY_MS = 400

let canvas: CanvasRenderingContext2D | null = null

/** Any CSS colour (oklch included) as #rrggbb, via a 1×1 canvas. */
function toHex(color: string): string | null {
  canvas ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true })
  if (!canvas || !color) return null
  canvas.clearRect(0, 0, 1, 1)
  canvas.fillStyle = "#000"
  canvas.fillStyle = color
  canvas.fillRect(0, 0, 1, 1)
  const [r, g, b] = canvas.getImageData(0, 0, 1, 1).data
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`
}

function themeColor(name: string): string | null {
  return toHex(getComputedStyle(document.documentElement).getPropertyValue(name).trim())
}

const call = (method: keyof Omit<DesktopApi, "set_title_bar" | "window_state">) => {
  window.pywebview?.api?.[method]?.().catch(() => {
    // The window is closing, or an older shell: nothing to do.
  })
}

/** Window state from the desktop shell; null in a browser or until the shell answers. */
export function useDesktopWindow(): WindowState | null {
  const { resolvedTheme } = useLocale()
  const [ready, setReady] = useState(() => Boolean(window.pywebview?.api))
  const [state, setState] = useState<WindowState | null>(null)

  useEffect(() => {
    if (ready) return
    const onReady = () => setReady(true)
    window.addEventListener("pywebviewready", onReady)
    return () => window.removeEventListener("pywebviewready", onReady)
  }, [ready])

  useEffect(() => {
    const api = window.pywebview?.api
    if (!ready || !api) return
    let cancelled = false
    const refresh = () => {
      const pending = api.window_state?.() ?? Promise.resolve({ custom: false, maximized: false })
      pending
        .catch(() => ({ custom: false, maximized: false }))
        .then((next) => {
          if (!cancelled) setState((prev) => (prev?.custom === next.custom && prev.maximized === next.maximized ? prev : next))
        })
    }
    refresh()
    // Maximising, restoring and snapping (buttons, Win + arrows, dragging) all resize the page.
    let timer = 0
    const onResize = () => {
      clearTimeout(timer)
      timer = window.setTimeout(refresh, 50)
    }
    window.addEventListener("resize", onResize)
    return () => {
      cancelled = true
      clearTimeout(timer)
      window.removeEventListener("resize", onResize)
    }
  }, [ready])

  const custom = state?.custom === true
  useEffect(() => {
    if (!custom) return
    document.documentElement.style.setProperty("--titlebar-height", TITLE_BAR_HEIGHT)
    return () => {
      document.documentElement.style.removeProperty("--titlebar-height")
    }
  }, [custom])

  // The shell shows the window once the colours arrive: send them after the bar is in place.
  const known = state !== null
  useEffect(() => {
    const api = window.pywebview?.api
    if (!known || !api?.set_title_bar) return
    // I18nProvider toggles `.dark` in its own effect, which runs after this one (parent effects
    // run last): read the colours on the next frame.
    const frame = requestAnimationFrame(() => {
      const background = themeColor("--sidebar")
      const foreground = themeColor("--sidebar-foreground")
      if (background && foreground) {
        api.set_title_bar?.(background, foreground, resolvedTheme === "dark").catch(() => {
          // Older shell without this API: keep the native colours.
        })
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [known, resolvedTheme])

  return state
}

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

export function TitleBar({ maximized }: { maximized: boolean }) {
  const t = useT(layout)
  const active = useWindowActive()
  const lastPress = useRef(0)
  const snapTimer = useRef(0)

  useEffect(() => () => clearTimeout(snapTimer.current), [])

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0 || (e.target as Element).closest("button, a, input, select, textarea")) return
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
    <header onMouseDown={onMouseDown} className="flex h-9 shrink-0 items-center border-b bg-sidebar select-none">
      <div className={cn("flex items-center gap-2 px-3.5 transition-opacity", !active && "opacity-55")}>
        <span className="flex size-5 items-center justify-center rounded-[5px] bg-primary text-primary-foreground">
          <VaultIcon className="size-3" />
        </span>
        <span className="text-[13px] font-medium text-sidebar-foreground">Binder</span>
      </div>
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
    </header>
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
