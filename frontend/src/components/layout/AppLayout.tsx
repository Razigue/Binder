import { NavLink, Outlet } from "react-router-dom"
import {
  Archive, Bot, CalendarDays, FileText, FolderCheck, History, Home, Lock, Mail, Repeat, Search, Settings,
  Trash2,
} from "lucide-react"
import { useAgent } from "@/components/agent"
import { EngineInfo, LocalBadge } from "@/components/StatusDot"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Accueil", icon: Home, end: true },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/echeances", label: "Échéances", icon: CalendarDays },
  { to: "/recherche", label: "Recherche", icon: Search },
  { to: "/abonnements", label: "Abonnements", icon: Repeat },
  { to: "/dossiers", label: "Dossiers", icon: FolderCheck },
  { to: "/courriers", label: "Courriers", icon: Mail },
  { to: "/tri", label: "Tri", icon: Archive },
  { to: "/historique", label: "Historique", icon: History },
  { to: "/corbeille", label: "Corbeille", icon: Trash2 },
  { to: "/reglages", label: "Réglages", icon: Settings },
]

const itemClass = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors"

export function AppLayout() {
  const agent = useAgent()
  return (
    <div className="flex min-h-svh">
      <div className="hidden w-60 shrink-0 border-r bg-sidebar md:block">
      <aside className="sticky top-0 flex h-svh flex-col px-3 py-5">
        <div className="mb-8 flex items-center gap-3 px-2">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Lock className="size-4" />
          </span>
          <div>
            <p className="text-[15px] leading-tight font-semibold">Coffre-fort</p>
            <p className="text-[11px] text-muted-foreground">Vos documents, vos échéances</p>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  itemClass,
                  isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/60",
                )
              }
            >
              <Icon className="size-4" /> {label}
            </NavLink>
          ))}
          <button onClick={() => agent.open()} className={cn(itemClass, "text-sidebar-foreground hover:bg-sidebar-accent/60")}>
            <Bot className="size-4" /> Agent
          </button>
        </nav>
        <div className="mt-auto space-y-1 px-2">
          <LocalBadge className="text-foreground" />
          <p className="text-[11px] text-muted-foreground">Vos données restent sur votre machine</p>
          <EngineInfo />
        </div>
      </aside>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Navigation mobile */}
        <nav className="flex gap-1 overflow-x-auto border-b bg-sidebar px-3 py-2 md:hidden">
          {NAV.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => cn("rounded-md px-3 py-1.5 text-sm whitespace-nowrap", isActive && "bg-sidebar-accent font-medium")}
            >
              {label}
            </NavLink>
          ))}
          <button onClick={() => agent.open()} className="rounded-md px-3 py-1.5 text-sm">
            Agent
          </button>
        </nav>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-10 md:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-4">
        {actions}
        <LocalBadge />
      </div>
    </div>
  )
}
