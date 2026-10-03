import { useEffect, useState } from "react"
import { useLocale } from "@/i18n"
import { themeColor, type WindowState } from "@/lib/desktop"

// Same height as the `h-9` bar: full-window layers (dialogs, sheets) start below it.
const TITLE_BAR_HEIGHT = "2.25rem"

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
