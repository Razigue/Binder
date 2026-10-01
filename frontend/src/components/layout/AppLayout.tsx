import { Suspense, useEffect, useRef } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import {
  Archive, BookLock, Bot, CalendarDays, FileText, FolderCheck, History, Home, Mail, Repeat, Search, Settings,
  Trash2, type LucideIcon,
} from "lucide-react"
import { useAgent } from "@/components/agent"
import { LocalBadge } from "@/components/StatusDot"
import { useDesktopTitleBar } from "@/components/layout/TitleBar"
import { useT } from "@/i18n"
import type { MessageKey } from "@/i18n/core"
import { layout } from "@/i18n/messages/layout"
import { cn } from "@/lib/utils"

type NavKey = MessageKey<typeof layout.en>
type NavItem = { to: string; label: NavKey; icon: LucideIcon; end?: boolean } | { agent: true; label: NavKey; icon: LucideIcon }

// Grouped by use: the essentials first, then tracking, paperwork, and keeping the binder tidy.
const NAV: { title?: NavKey; items: NavItem[] }[] = [
  {
    items: [
      { to: "/", label: "nav.home", icon: Home, end: true },
      { to: "/documents", label: "nav.documents", icon: FileText },
      { to: "/search", label: "nav.search", icon: Search },
      { agent: true, label: "nav.agent", icon: Bot },
    ],
  },
  {
    title: "section.tracking",
    items: [
      { to: "/deadlines", label: "nav.deadlines", icon: CalendarDays },
      { to: "/subscriptions", label: "nav.subscriptions", icon: Repeat },
    ],
  },
  {
    title: "section.paperwork",
    items: [
      { to: "/folders", label: "nav.folders", icon: FolderCheck },
      { to: "/letters", label: "nav.letters", icon: Mail },
    ],
  },
  {
    title: "section.upkeep",
    items: [
      { to: "/sorting", label: "nav.sorting", icon: Archive },
      { to: "/history", label: "nav.history", icon: History },
      { to: "/trash", label: "nav.trash", icon: Trash2 },
    ],
  },
]

const SETTINGS: NavItem & { to: string } = { to: "/settings", label: "nav.settings", icon: Settings }
const FLAT_NAV = [...NAV.flatMap((s) => s.items), SETTINGS]

const itemClass = "flex w-full items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
const idleClass = "text-sidebar-foreground hover:bg-sidebar-accent/60"
const mobileItemClass = "shrink-0 rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition-colors"
const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(itemClass, isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : idleClass)

export function AppLayout() {
  const agent = useAgent()
  const t = useT(layout)
  const { pathname } = useLocation()
  const mobileNav = useRef<HTMLElement>(null)
  useDesktopTitleBar()

  // The phone bar scrolls sideways: keep the current page's tab in view.
  useEffect(() => {
    mobileNav.current?.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView({ block: "nearest", inline: "center" })
  }, [pathname])
  return (
    <div className="flex min-h-svh">
      <div className="hidden w-60 shrink-0 border-r bg-sidebar md:block">
      <aside className="sticky top-0 flex h-svh flex-col px-3 py-5 select-none">
        <div className="mb-8 flex items-center gap-3 px-2">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <BookLock className="size-4" />
          </span>
          <p className="text-[15px] font-semibold">Binder</p>
        </div>
        <nav className="-mx-1 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-1">
          {NAV.map((section, i) => (
            <div key={section.title ?? i} className="flex flex-col gap-0.5">
              {section.title && (
                <p className="mb-1 px-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{t(section.title)}</p>
              )}
              {section.items.map((item) =>
                "agent" in item ? (
                  <button key="agent" onClick={() => agent.open()} className={cn(itemClass, idleClass)}>
                    <item.icon className="size-4" /> {t(item.label)}
                  </button>
                ) : (
                  <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                    <item.icon className="size-4" /> {t(item.label)}
                  </NavLink>
                ),
              )}
            </div>
          ))}
        </nav>
        <NavLink to={SETTINGS.to} className={(state) => cn(linkClass(state), "mt-4")}>
          <SETTINGS.icon className="size-4" /> {t(SETTINGS.label)}
        </NavLink>
      </aside>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile navigation */}
        <nav
          ref={mobileNav}
          aria-label={t("navigation")}
          className="flex gap-1 overflow-x-auto border-b bg-sidebar px-3 py-2 pr-8 [scrollbar-width:none] select-none mask-r-from-[calc(100%-2rem)] md:hidden"
        >
          {FLAT_NAV.map((item) =>
            "agent" in item ? (
              <button key="agent" onClick={() => agent.open()} className={cn(mobileItemClass, "hover:bg-sidebar-accent/60")}>
                {t(item.label)}
              </button>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(mobileItemClass, isActive ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60")
                }
              >
                {t(item.label)}
              </NavLink>
            ),
          )}
        </nav>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-10 md:py-8">
          {/* Pages load on first visit: the menu stays in place meanwhile. */}
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
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
