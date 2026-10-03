// Bridge to the desktop shell (`window.pywebview.api`). In a browser there is no
// `window.pywebview`: every call does nothing.

export interface WindowState {
  custom: boolean
  maximized: boolean
}

export interface DesktopApi {
  set_title_bar?: (background: string, foreground: string, dark: boolean) => Promise<void>
  window_state?: () => Promise<WindowState>
  drag?: () => Promise<void>
  minimize?: () => Promise<void>
  toggle_maximize?: () => Promise<void>
  snap_layouts?: () => Promise<void>
  close?: () => Promise<void>
  choose_folder?: (initial: string) => Promise<string | null>
  open_external?: (url: string) => Promise<void>
}

declare global {
  interface Window {
    pywebview?: { api?: DesktopApi }
  }
}

/** Calls a window command of the shell, ignoring a closing window or an older shell. */
export function callDesktop(method: "drag" | "minimize" | "toggle_maximize" | "snap_layouts" | "close") {
  window.pywebview?.api?.[method]?.().catch(() => {
    // The window is closing, or an older shell: nothing to do.
  })
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
  const rgb = [...canvas.getImageData(0, 0, 1, 1).data.slice(0, 3)]
  return `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("")}`
}

/** A colour of the theme (`--sidebar`) as #rrggbb, for the native title bar. */
export function themeColor(name: string): string | null {
  return toHex(getComputedStyle(document.documentElement).getPropertyValue(name).trim())
}
