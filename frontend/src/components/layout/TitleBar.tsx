import { useEffect, useState } from "react"
import { useLocale } from "@/i18n"

// Desktop window title bar. The app keeps the native frame (resizing, Snap layouts, dragging
// and the system window buttons all keep working) and asks the desktop shell to paint it in the
// app's colours: on Windows 11 the caption takes the sidebar colour, on macOS the window follows
// the app's light/dark choice. In a browser there is no `window.pywebview`: nothing happens.

interface DesktopApi {
  set_title_bar?: (background: string, foreground: string, dark: boolean) => Promise<void>
}

declare global {
  interface Window {
    pywebview?: { api?: DesktopApi }
  }
}

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

export function useDesktopTitleBar() {
  const { resolvedTheme } = useLocale()
  const [ready, setReady] = useState(() => Boolean(window.pywebview?.api))

  useEffect(() => {
    if (ready) return
    const onReady = () => setReady(true)
    window.addEventListener("pywebviewready", onReady)
    return () => window.removeEventListener("pywebviewready", onReady)
  }, [ready])

  useEffect(() => {
    const api = window.pywebview?.api
    if (!ready || !api?.set_title_bar) return
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
  }, [ready, resolvedTheme])
}
