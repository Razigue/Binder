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
import type { Selection } from "@/hooks/useSelection"
import { cn } from "@/lib/utils"

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
    <div className="pointer-events-none fixed inset-x-0 bottom-40 z-20 flex justify-center px-4 md:bottom-24 md:left-60">
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
