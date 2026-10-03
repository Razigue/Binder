import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent } from "react"

export interface Selection {
  /** Selected ids, in display order (ids no longer shown are dropped). */
  ids: number[]
  /** Rows shown. */
  size: number
  has: (id: number) => boolean
  toggle: (id: number) => void
  /** Shift: from the last row clicked to this one; `add` (Ctrl too) keeps the rest. */
  extend: (id: number, add: boolean) => void
  only: (id: number) => void
  all: () => void
  clear: () => void
}

/** Multiple selection over rows shown in `order`, the way a file manager does it. */
export function useSelection(order: number[]): Selection {
  const [picked, setPicked] = useState<ReadonlySet<number>>(() => new Set())
  const anchor = useRef<number | null>(null)
  const ids = useMemo(() => order.filter((id) => picked.has(id)), [order, picked])

  const toggle = useCallback((id: number) => {
    anchor.current = id
    setPicked((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }, [])
  const only = useCallback((id: number) => {
    anchor.current = id
    setPicked(new Set([id]))
  }, [])
  const extend = useCallback(
    (id: number, add: boolean) => {
      const from = anchor.current === null ? -1 : order.indexOf(anchor.current)
      const to = order.indexOf(id)
      if (from < 0 || to < 0) return only(id)
      const range = order.slice(Math.min(from, to), Math.max(from, to) + 1)
      setPicked((prev) => new Set(add ? [...prev, ...range] : range))
    },
    [order, only],
  )
  const all = useCallback(() => setPicked(new Set(order)), [order])
  const clear = useCallback(() => {
    anchor.current = null
    setPicked(new Set())
  }, [])
  const has = useCallback((id: number) => picked.has(id), [picked])

  return { ids, size: order.length, has, toggle, extend, only, all, clear }
}

const editable = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))

/** Ctrl+A selects every row, Escape clears, Delete runs `onDelete`; not while typing or in a dialog. */
export function useSelectionKeys(selection: Selection, onDelete?: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || editable(e.target)) return
      if (e.target instanceof Element && e.target.closest("[role=dialog],[role=menu],[role=alertdialog]")) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && selection.size) {
        e.preventDefault()
        selection.all()
      } else if (e.key === "Escape" && selection.ids.length) {
        selection.clear()
      } else if (e.key === "Delete" && selection.ids.length && onDelete) {
        e.preventDefault()
        onDelete()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [selection, onDelete])
}

/** Spread on a row: Ctrl/Cmd+click toggles it, Shift+click selects a range, a right click selects
 * it for the context menu, Space toggles it from the keyboard. A plain click still opens it. */
export function selectableRow(selection: Selection, id: number) {
  return {
    "data-selected": selection.has(id) || undefined,
    onMouseDown: (e: MouseEvent) => {
      // Shift+click would otherwise select the text between the two rows.
      if (e.shiftKey) e.preventDefault()
    },
    onClick: (e: MouseEvent) => {
      if (e.shiftKey) {
        e.preventDefault()
        selection.extend(id, e.ctrlKey || e.metaKey)
      } else if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        selection.toggle(id)
      }
    },
    onContextMenu: () => {
      if (!selection.has(id)) selection.only(id)
    },
    onKeyDown: (e: ReactKeyboardEvent) => {
      if (e.key !== " ") return
      e.preventDefault()
      if (e.shiftKey) selection.extend(id, true)
      else selection.toggle(id)
    },
  }
}

/** Row background: selected rows keep the accent fill. */
export const selectedRowClass = "data-selected:bg-accent/70 data-selected:hover:bg-accent"
