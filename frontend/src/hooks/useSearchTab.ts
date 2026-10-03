import { useSearchParams } from "react-router-dom"
import { oneOf } from "@/lib/utils"

/** The tab shown, kept in the address (`?tab=`) so that back and bookmarks return to it. */
export function useSearchTab<const T extends string>(tabs: readonly T[], fallback: T) {
  const [params, setParams] = useSearchParams()
  const tab = oneOf(tabs, params.get("tab")) ?? fallback
  const setTab = (next: T) =>
    setParams((p) => {
      p.set("tab", next)
      return p
    })
  return [tab, setTab] as const
}
