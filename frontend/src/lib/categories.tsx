import {
  Briefcase, FileText, HeartPulse, Home, Landmark, Receipt, ShieldCheck, Smartphone, Users, Zap,
  type LucideIcon,
} from "lucide-react"
import type { Category } from "./api"

export const CATEGORY_STYLE: Record<Category, { icon: LucideIcon; tone: string; color: string }> = {
  Impôts: { icon: Landmark, tone: "bg-red-50 text-red-500", color: "#ef4444" },
  Énergie: { icon: Zap, tone: "bg-sky-50 text-sky-600", color: "#0284c7" },
  Assurance: { icon: ShieldCheck, tone: "bg-orange-50 text-orange-500", color: "#f97316" },
  Banque: { icon: Receipt, tone: "bg-indigo-50 text-indigo-500", color: "#6366f1" },
  Logement: { icon: Home, tone: "bg-emerald-50 text-emerald-600", color: "#10b981" },
  Santé: { icon: HeartPulse, tone: "bg-pink-50 text-pink-500", color: "#ec4899" },
  Social: { icon: Users, tone: "bg-violet-50 text-violet-500", color: "#8b5cf6" },
  Travail: { icon: Briefcase, tone: "bg-amber-50 text-amber-600", color: "#d97706" },
  Télécom: { icon: Smartphone, tone: "bg-cyan-50 text-cyan-600", color: "#0891b2" },
  Autre: { icon: FileText, tone: "bg-slate-100 text-slate-500", color: "#64748b" },
}
