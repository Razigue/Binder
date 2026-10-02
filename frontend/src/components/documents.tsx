import { useCallback, useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { ArchiveIcon, SealCheckIcon, CaretRightIcon, DownloadSimpleIcon, ArrowSquareOutIcon, TrayArrowDownIcon, HourglassIcon, CircleNotchIcon, ArrowsClockwiseIcon, TrashIcon } from "@phosphor-icons/react"
import { CategoryIcon } from "@/components/CategoryIcon"
import {
  RowCheckbox, SelectionBar, SelectionMenu, selectableRow, selectedRowClass, useSelection, useSelectionKeys,
  type SelectionAction,
} from "@/components/selection"
import { useBulkDocuments } from "@/hooks/queries"
import { useT } from "@/i18n"
import { area as messages } from "@/i18n/messages/area"
import { selection as selectionMessages } from "@/i18n/messages/selection"
import { CATEGORIES, selectionExportUrl, type BulkPatch, type Doc } from "@/lib/api"
import { categoryLabel, docTypeLabel, formatAmount, formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

const fold = (text: string) => text.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "")

/** Whether a document matches every word typed, accents and case aside. */
export function matches(d: Doc, filter: string): boolean {
  const words = fold(filter).split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const hay = fold(`${d.title} ${d.issuer ?? ""} ${d.reference ?? ""} ${docTypeLabel(d.doc_type)} ${d.person ?? ""}`)
  return words.every((w) => hay.includes(w))
}

/** Documents by year, most recent first, as rows inside a card. Several can be selected (tick
 * boxes, Ctrl/Shift+click, right click) and handled together. */
export function DocumentsByYear({ docs }: { docs: Doc[] }) {
  const t = useT(messages)
  const years = useMemo(() => {
    const groups = new Map<string, Doc[]>()
    for (const d of docs) {
      const year = (d.issue_date ?? d.due_date ?? d.created_at).slice(0, 4)
      groups.set(year, [...(groups.get(year) ?? []), d])
    }
    return [...groups.entries()].sort((a, b) => b[0].localeCompare(a[0]))
  }, [docs])
  // Shift+click ranges follow the rows as displayed, year after year.
  const order = useMemo(() => years.flatMap(([, list]) => list.map((d) => d.id)), [years])
  const selection = useSelection(order)
  const actions = useDocumentActions(docs, selection.ids, selection.clear)
  useSelectionKeys(selection, actions.find((a) => a.key === "trash")?.onSelect)

  return (
    <>
      <SelectionMenu selection={selection} actions={actions}>
        {years.map(([year, list]) => (
          <div key={year}>
            <p className="border-b bg-muted/30 px-5 py-1.5 text-xs font-medium text-muted-foreground">{year}</p>
            <ul className="divide-y">
              {list.map((d) => (
                <li key={d.id} className="group/row relative">
                  <Link
                    to={`/documents/${d.id}`}
                    {...selectableRow(selection, d.id)}
                    className={cn(
                      "grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3 hover:bg-muted/40",
                      selectedRowClass,
                    )}
                  >
                    {/* The category tile sits over this space, as the row's checkbox. */}
                    <span className="size-9" />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {d.status === "processing" ? (
                          <span className="flex items-center gap-1.5 text-muted-foreground">
                            <CircleNotchIcon className="size-3.5 animate-spin" /> {t("analysing")}
                          </span>
                        ) : d.status === "waiting" ? (
                          <span className="flex items-center gap-1.5 text-muted-foreground">
                            <HourglassIcon className="size-3.5" /> {d.filename} · {t("waiting")}
                          </span>
                        ) : (
                          d.title
                        )}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {[
                          formatDate(d.issue_date ?? d.created_at),
                          d.issuer,
                          d.person,
                          d.superseded_by !== null ? t("oldVersion") : null,
                          d.source_letter_id !== null ? t("sentByYou") : null,
                          d.status === "to_review" ? t("question") : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="text-sm tabular-nums">{d.amount !== null ? formatAmount(d.amount) : ""}</span>
                    <CaretRightIcon className="size-4 text-muted-foreground" />
                  </Link>
                  <RowCheckbox selection={selection} id={d.id} label={d.title || d.filename}>
                    <CategoryIcon category={d.category} />
                  </RowCheckbox>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </SelectionMenu>
      <SelectionBar selection={selection} actions={actions} />
    </>
  )
}

/** What can be done to the selected documents at once. */
function useDocumentActions(docs: Doc[], ids: number[], clear: () => void): SelectionAction[] {
  const t = useT(selectionMessages)
  const navigate = useNavigate()
  const bulk = useBulkDocuments()
  const fail = useCallback((e: Error) => toast.error(e.message), [])
  const chosen = docs.filter((d) => ids.includes(d.id))
  if (!chosen.length) return []
  // The backend's answer shows its own toast with "Undo"; only what it cannot undo needs one here.
  const update = (patch: BulkPatch) => bulk.update.mutate({ ids, patch }, { onError: fail })
  const kept = chosen.every((d) => d.keep_forever)
  const actions: (SelectionAction | false)[] = [
    chosen.length === 1 && {
      key: "open",
      label: t("open"),
      icon: ArrowSquareOutIcon,
      menuOnly: true,
      onSelect: () => navigate(`/documents/${chosen[0].id}`),
    },
    {
      key: "category",
      label: t("category"),
      icon: TrayArrowDownIcon,
      primary: true,
      items: CATEGORIES.map((c) => ({
        key: c,
        label: categoryLabel(c),
        icon: <CategoryIcon category={c} size="sm" />,
        onSelect: () => update({ category: c }),
      })),
    },
    chosen.some((d) => d.status === "to_review") && {
      key: "validate",
      label: t("validate"),
      icon: SealCheckIcon,
      onSelect: () => update({ validated: true }),
    },
    {
      key: "keep",
      label: kept ? t("keepNoLonger") : t("keepForever"),
      icon: ArchiveIcon,
      onSelect: () => update({ keep_forever: !kept }),
    },
    {
      key: "reanalyze",
      label: t("reanalyze"),
      icon: ArrowsClockwiseIcon,
      onSelect: () => bulk.reanalyze.mutate(ids, { onSuccess: (r) => toast.success(r.message), onError: fail }),
    },
    {
      key: "download",
      label: t("download"),
      icon: DownloadSimpleIcon,
      primary: true,
      onSelect: () => {
        window.location.href = selectionExportUrl(ids)
      },
    },
    {
      key: "trash",
      label: t("trash"),
      icon: TrashIcon,
      primary: true,
      destructive: true,
      shortcut: t("shortcutDelete"),
      onSelect: () => bulk.trash.mutate(ids, { onSuccess: clear, onError: fail }),
    },
  ]
  return actions.filter((a): a is SelectionAction => a !== false)
}
