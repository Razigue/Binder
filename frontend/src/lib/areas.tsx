import { BackpackIcon, BriefcaseIcon, CarIcon, HeartbeatIcon, HouseIcon, IdentificationCardIcon, WalletIcon, type Icon } from "@phosphor-icons/react"
import type { Area } from "./api"
import { cn } from "./utils"

// Same hues as the categories they gather (lib/categories.tsx): colour says where it lives.
const AREA_STYLE: Record<Area, { icon: Icon; tone: string }> = {
  housing: { icon: HouseIcon, tone: "bg-emerald-50 text-emerald-600 dark:bg-emerald-400/12 dark:text-emerald-300" },
  money: { icon: WalletIcon, tone: "bg-indigo-50 text-indigo-500 dark:bg-indigo-400/12 dark:text-indigo-300" },
  work: { icon: BriefcaseIcon, tone: "bg-amber-50 text-amber-600 dark:bg-amber-400/12 dark:text-amber-300" },
  family: { icon: BackpackIcon, tone: "bg-rose-50 text-rose-500 dark:bg-rose-400/12 dark:text-rose-300" },
  health: { icon: HeartbeatIcon, tone: "bg-pink-50 text-pink-500 dark:bg-pink-400/12 dark:text-pink-300" },
  identity: { icon: IdentificationCardIcon, tone: "bg-teal-50 text-teal-600 dark:bg-teal-400/12 dark:text-teal-300" },
  vehicle: { icon: CarIcon, tone: "bg-lime-50 text-lime-700 dark:bg-lime-400/12 dark:text-lime-300" },
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
