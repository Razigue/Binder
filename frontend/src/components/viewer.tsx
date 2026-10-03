import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { ArrowsInLineHorizontalIcon, CornersOutIcon, MagnifyingGlassMinusIcon, MagnifyingGlassPlusIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { viewer } from "@/i18n/messages/viewer"
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

// Zoom is relative to "fit to width" (1): the content is laid out at `zoom × 100%` of the pane.
const MIN = 0.4
const MAX = 5
const STEPS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5]
// The pane's padding (`p-4`), kept out of the anchor maths.
const PAD = 16

const clamp = (z: number) => Math.min(MAX, Math.max(MIN, z))

/**
 * A page shown on a grey desk, at the width of the pane, with zoom (buttons, Ctrl + wheel or
 * pinch, double-click, + / − / 0 keys) that keeps the point under the cursor in place, and
 * drag to move around (`pan`; off where text must stay selectable). `aspect` (height / width of
 * the content) enables "Whole page". `extra` goes at the right of the toolbar (a pager).
 */
export function Viewer({
  children,
  aspect,
  pan = true,
  extra,
  className,
}: {
  children: ReactNode
  aspect?: number
  pan?: boolean
  extra?: ReactNode
  className?: string
}) {
  const t = useT(viewer)
  const pane = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const current = useRef(1)
  // Where to scroll once the new size is laid out, so the anchor point stays under the cursor.
  const anchor = useRef<{ x: number; y: number; cx: number; cy: number; f: number } | null>(null)
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const hintId = useId()

  const zoomTo = useCallback((value: number, at?: { x: number; y: number }) => {
    const el = pane.current
    const next = clamp(value)
    if (!el || Math.abs(next - current.current) < 0.001) return
    const p = at ?? { x: el.clientWidth / 2, y: el.clientHeight / 2 }
    anchor.current = { x: p.x, y: p.y, cx: el.scrollLeft + p.x - PAD, cy: el.scrollTop + p.y - PAD, f: next / current.current }
    current.current = next
    setZoom(next)
  }, [])

  useLayoutEffect(() => {
    const a = anchor.current
    const el = pane.current
    if (!a || !el) return
    anchor.current = null
    el.scrollLeft = a.cx * a.f + PAD - a.x
    el.scrollTop = a.cy * a.f + PAD - a.y
  }, [zoom])

  // Ctrl + wheel (and a trackpad pinch, which browsers report the same way). Not passive: the
  // browser would zoom the whole page otherwise.
  useEffect(() => {
    const el = pane.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return
      e.preventDefault()
      const delta = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY
      const r = el.getBoundingClientRect()
      zoomTo(current.current * Math.exp(-delta * 0.0015), { x: e.clientX - r.left, y: e.clientY - r.top })
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [zoomTo])

  const step = (direction: 1 | -1) => {
    const z = current.current
    const next = direction > 0 ? STEPS.find((s) => s > z + 0.01) : [...STEPS].reverse().find((s) => s < z - 0.01)
    zoomTo(next ?? (direction > 0 ? MAX : MIN))
  }

  const fitPage = () => {
    const el = pane.current
    if (!el || !aspect) return
    const w = el.clientWidth - 2 * PAD
    const h = el.clientHeight - 2 * PAD
    zoomTo(Math.min(1, h / (w * aspect)))
    el.scrollTo({ top: 0, left: 0 })
  }

  // Where the pointer is, inside the pane (the element the handler is on).
  const point = (e: React.MouseEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  const percent = formatNumber(zoom, { style: "percent", maximumFractionDigits: 0 })

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div
        ref={pane}
        tabIndex={0}
        role="region"
        aria-label={t("pane")}
        aria-describedby={hintId}
        className={cn(
          "min-h-0 flex-1 overflow-auto bg-muted/50 p-4 outline-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-inset",
          pan && (dragging ? "cursor-grabbing select-none" : "cursor-grab"),
        )}
        onKeyDown={(e) => {
          if (e.ctrlKey || e.metaKey || e.altKey) return
          if (e.key === "+" || e.key === "=") step(1)
          else if (e.key === "-") step(-1)
          else if (e.key === "0") zoomTo(1)
          else return
          e.preventDefault()
        }}
        onDoubleClick={(e) => (current.current < 1.5 ? zoomTo(2, point(e)) : zoomTo(1, point(e)))}
        onPointerDown={(e) => {
          // A finger scrolls the pane natively; the mouse drags it.
          if (!pan || e.button !== 0 || e.pointerType === "touch") return
          const el = pane.current!
          drag.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop }
          el.setPointerCapture(e.pointerId)
          setDragging(true)
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (!d) return
          const el = pane.current!
          el.scrollLeft = d.left - (e.clientX - d.x)
          el.scrollTop = d.top - (e.clientY - d.y)
        }}
        onPointerUp={() => {
          drag.current = null
          setDragging(false)
        }}
        onPointerCancel={() => {
          drag.current = null
          setDragging(false)
        }}
      >
        <div className="relative mx-auto" style={{ width: `${zoom * 100}%` }}>
          {children}
        </div>
        <span id={hintId} className="sr-only">
          {t("keysHint")}
        </span>
      </div>
      <div className="flex items-center gap-1 border-t px-2 py-1.5 text-sm">
        <Button variant="ghost" size="icon-sm" onClick={() => step(-1)} disabled={zoom <= MIN} aria-label={t("zoomOut")} title={t("zoomOut")}>
          <MagnifyingGlassMinusIcon />
        </Button>
        <button
          type="button"
          onClick={() => zoomTo(1)}
          className="min-w-14 rounded-md px-1.5 py-1 text-center text-xs font-medium tabular-nums text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label={t("zoomLevel", { value: percent })}
          title={`${t("zoomReset")} · ${t("zoomHint")}`}
        >
          {percent}
        </button>
        <Button variant="ghost" size="icon-sm" onClick={() => step(1)} disabled={zoom >= MAX} aria-label={t("zoomIn")} title={t("zoomIn")}>
          <MagnifyingGlassPlusIcon />
        </Button>
        <Button variant="ghost" size="icon-sm" onClick={() => zoomTo(1)} aria-label={t("zoomReset")} title={t("zoomReset")}>
          <ArrowsInLineHorizontalIcon />
        </Button>
        {aspect && (
          <Button variant="ghost" size="icon-sm" onClick={fitPage} aria-label={t("fitPage")} title={t("fitPage")}>
            <CornersOutIcon />
          </Button>
        )}
        {extra && <div className="ml-auto flex items-center gap-2">{extra}</div>}
      </div>
    </div>
  )
}
