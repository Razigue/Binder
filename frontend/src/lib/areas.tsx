import { Briefcase, Car, HeartPulse, Home, IdCard, Wallet, type LucideIcon } from "lucide-react"
import type { Area } from "./api"
import { cn } from "./utils"

// Same hues as the categories they gather (lib/categories.tsx): colour says where it lives.
export const AREA_STYLE: Record<Area, { icon: LucideIcon; tone: string }> = {
  housing: { icon: Home, tone: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400" },
  money: { icon: Wallet, tone: "bg-indigo-50 text-indigo-500 dark:bg-indigo-500/15 dark:text-indigo-300" },
  work: { icon: Briefcase, tone: "bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-400" },
  health: { icon: HeartPulse, tone: "bg-pink-50 text-pink-500 dark:bg-pink-500/15 dark:text-pink-400" },
  identity: { icon: IdCard, tone: "bg-teal-50 text-teal-600 dark:bg-teal-500/15 dark:text-teal-400" },
  vehicle: { icon: Car, tone: "bg-lime-50 text-lime-700 dark:bg-lime-500/15 dark:text-lime-400" },
}

export function AreaIcon({ area, size = "md" }: { area: Area; size?: "sm" | "md" }) {
  const { icon: Icon, tone } = AREA_STYLE[area]
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg",
        tone,
        size === "sm" ? "size-7 [&_svg]:size-3.5" : "size-9 [&_svg]:size-4",
      )}
    >
      <Icon />
    </span>
  )
}
