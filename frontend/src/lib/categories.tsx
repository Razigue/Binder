import { BackpackIcon, BriefcaseIcon, CarIcon, FileTextIcon, HeartbeatIcon, HouseIcon, IdentificationCardIcon, BankIcon, ReceiptIcon, ShieldCheckIcon, ShoppingBagIcon, DeviceMobileIcon, UsersIcon, LightningIcon, type Icon } from "@phosphor-icons/react"
import type { Category } from "./api"

export const CATEGORY_STYLE: Record<Category, { icon: Icon; tone: string; color: string }> = {
  taxes: { icon: BankIcon, tone: "bg-red-50 text-red-500 dark:bg-red-500/15 dark:text-red-400", color: "#ef4444" },
  energy: { icon: LightningIcon, tone: "bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-400", color: "#0284c7" },
  insurance: { icon: ShieldCheckIcon, tone: "bg-orange-50 text-orange-500 dark:bg-orange-500/15 dark:text-orange-400", color: "#f97316" },
  bank: { icon: ReceiptIcon, tone: "bg-indigo-50 text-indigo-500 dark:bg-indigo-500/15 dark:text-indigo-300", color: "#6366f1" },
  housing: { icon: HouseIcon, tone: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400", color: "#10b981" },
  health: { icon: HeartbeatIcon, tone: "bg-pink-50 text-pink-500 dark:bg-pink-500/15 dark:text-pink-400", color: "#ec4899" },
  social: { icon: UsersIcon, tone: "bg-violet-50 text-violet-500 dark:bg-violet-500/15 dark:text-violet-300", color: "#8b5cf6" },
  work: { icon: BriefcaseIcon, tone: "bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-400", color: "#d97706" },
  telecom: { icon: DeviceMobileIcon, tone: "bg-cyan-50 text-cyan-600 dark:bg-cyan-500/15 dark:text-cyan-400", color: "#0891b2" },
  identity: { icon: IdentificationCardIcon, tone: "bg-teal-50 text-teal-600 dark:bg-teal-500/15 dark:text-teal-400", color: "#0d9488" },
  vehicle: { icon: CarIcon, tone: "bg-lime-50 text-lime-700 dark:bg-lime-500/15 dark:text-lime-400", color: "#4d7c0f" },
  family: { icon: BackpackIcon, tone: "bg-rose-50 text-rose-500 dark:bg-rose-500/15 dark:text-rose-400", color: "#f43f5e" },
  purchases: { icon: ShoppingBagIcon, tone: "bg-yellow-50 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400", color: "#a16207" },
  other: { icon: FileTextIcon, tone: "bg-slate-100 text-slate-500 dark:bg-slate-500/20 dark:text-slate-300", color: "#64748b" },
}
