import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CheckSquareIcon, DotsThreeIcon, XIcon, type Icon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@/components/ui/context-menu"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuSub,
  DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useT } from "@/i18n"
import { selection as messages } from "@/i18n/messages/selection"
import { cn } from "@/lib/utils"

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
    onMouseDown: (e: React.MouseEvent) => {
      // Shift+click would otherwise select the text between the two rows.
      if (e.shiftKey) e.preventDefault()
    },
    onClick: (e: React.MouseEvent) => {
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
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key !== " ") return
      e.preventDefault()
      if (e.shiftKey) selection.extend(id, true)
      else selection.toggle(id)
    },
  }
}

/** Row background: selected rows keep the accent fill. */
export const selectedRowClass = "data-selected:bg-accent/70 data-selected:hover:bg-accent"

/** The row's tile turns into a checkbox on hover and while something is selected. A tap on it
 * (phone) selects instead of opening. Sits over the row, not inside its link. */
export function RowCheckbox({
  selection,
  id,
  label,
  children,
}: {
  selection: Selection
  id: number
  label: string
  children: React.ReactNode
}) {
  const checked = selection.has(id)
  const active = selection.ids.length > 0
  return (
    <span className="pointer-events-none absolute top-3 left-5 flex size-9 items-center justify-center">
      <span className={cn("transition-opacity", active ? "opacity-0" : "group-hover/row:opacity-0")}>{children}</span>
      <Checkbox
        checked={checked}
        aria-label={label}
        onMouseDown={(e) => e.shiftKey && e.preventDefault()}
        onClick={(e) => {
          e.preventDefault()
          if (e.shiftKey) selection.extend(id, true)
          else selection.toggle(id)
        }}
        className={cn(
          "pointer-events-auto absolute size-5 after:-inset-2 [&_svg]:size-4",
          active ? "opacity-100" : "opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100",
        )}
      />
    </span>
  )
}

export interface SelectionAction {
  key: string
  label: string
  icon: Icon
  onSelect?: () => void
  /** A submenu instead of a direct action (e.g. one entry per category). */
  items?: { key: string; label: string; icon?: React.ReactNode; onSelect: () => void }[]
  destructive?: boolean
  shortcut?: string
  /** Shown as a button in the bar; the others go to its "More" menu. */
  primary?: boolean
  /** Context menu only, e.g. "Open" for a single document. */
  menuOnly?: boolean
}

function MenuEntries({ actions }: { actions: SelectionAction[] }) {
  return actions.map((a) =>
    a.items ? (
      <DropdownMenuSub key={a.key}>
        <DropdownMenuSubTrigger>
          <a.icon /> {a.label}
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent className="max-h-80 min-w-48">
          {a.items.map((item) => (
            <DropdownMenuItem key={item.key} onClick={item.onSelect}>
              {item.icon} {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuSubContent>
      </DropdownMenuSub>
    ) : (
      <DropdownMenuItem key={a.key} onClick={a.onSelect} variant={a.destructive ? "destructive" : "default"}>
        <a.icon /> {a.label}
        {a.shortcut && <DropdownMenuShortcut>{a.shortcut}</DropdownMenuShortcut>}
      </DropdownMenuItem>
    ),
  )
}

/** Right click (or a long press on a phone) anywhere on the list opens the actions for the
 * selection. */
export function SelectionMenu({
  selection,
  actions,
  children,
}: {
  selection: Selection
  actions: SelectionAction[]
  children: React.ReactNode
}) {
  const t = useT(messages)
  const main = actions.filter((a) => !a.destructive)
  const destructive = actions.filter((a) => a.destructive)
  return (
    <ContextMenu>
      <ContextMenuTrigger>{children}</ContextMenuTrigger>
      <ContextMenuContent>
        {selection.ids.length > 0 && (
          <>
            <MenuEntries actions={main} />
            {destructive.length > 0 && <DropdownMenuSeparator />}
            <MenuEntries actions={destructive} />
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onClick={selection.all}>
          <CheckSquareIcon /> {t("selectAll")}
          <DropdownMenuShortcut>Ctrl A</DropdownMenuShortcut>
        </DropdownMenuItem>
        {selection.ids.length > 0 && (
          <DropdownMenuItem onClick={selection.clear}>
            <XIcon /> {t("clear")}
            <DropdownMenuShortcut>Esc</DropdownMenuShortcut>
          </DropdownMenuItem>
        )}
      </ContextMenuContent>
    </ContextMenu>
  )
}

/** Floats at the bottom of the page, above the ask bar (same placement), while rows are selected. */
export function SelectionBar({ selection, actions }: { selection: Selection; actions: SelectionAction[] }) {
  const t = useT(messages)
  const count = selection.ids.length
  const total = selection.size
  if (!count) return null
  const shown = actions.filter((a) => !a.menuOnly)
  const primary = shown.filter((a) => a.primary)
  const more = shown.filter((a) => !a.primary)
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-20 flex justify-center px-4 md:left-60">
      <div
        role="toolbar"
        aria-label={t("selected", { count })}
        className="pointer-events-auto flex max-w-full items-center gap-1 rounded-xl border bg-card p-1.5 pl-3 shadow-md animate-in fade-in-0 slide-in-from-bottom-2"
      >
        <Checkbox
          checked={count === total}
          indeterminate={count > 0 && count < total}
          onCheckedChange={(checked) => (checked && count < total ? selection.all() : selection.clear())}
          aria-label={count === total ? t("clear") : t("selectAll")}
        />
        <span className="mr-1 ml-2 text-sm font-medium whitespace-nowrap tabular-nums">{t("selected", { count })}</span>
        {primary.map((a) =>
          a.items ? (
            <DropdownMenu key={a.key}>
              <DropdownMenuTrigger render={<Button variant="ghost" size="sm" aria-label={a.label} />}>
                <a.icon /> <span className="hidden sm:inline">{a.label}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" className="max-h-80 w-56">
                {a.items.map((item) => (
                  <DropdownMenuItem key={item.key} onClick={item.onSelect}>
                    {item.icon} {item.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button
              key={a.key}
              variant="ghost"
              size="sm"
              onClick={a.onSelect}
              aria-label={a.label}
              className={cn(a.destructive && "text-destructive hover:bg-destructive/10 hover:text-destructive")}
            >
              <a.icon /> <span className="hidden sm:inline">{a.label}</span>
            </Button>
          ),
        )}
        {more.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={t("more")} />}>
              <DotsThreeIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="end" className="w-64">
              <MenuEntries actions={more} />
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <Button variant="ghost" size="icon-sm" onClick={selection.clear} aria-label={t("clear")}>
          <XIcon />
        </Button>
      </div>
    </div>
  )
}
