import { Suspense, useEffect, useRef, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowUp, BookLock, Bot, History, Mail, Sun, Trash2 } from "lucide-react"
import { useAgent } from "@/components/agent"
import { LocalBadge } from "@/components/StatusDot"
import { useDesktopTitleBar } from "@/components/layout/TitleBar"
import { useT } from "@/i18n"
import { area as areaMessages } from "@/i18n/messages/area"
import { layout } from "@/i18n/messages/layout"
import { AREAS, api } from "@/lib/api"
import { AREA_STYLE } from "@/lib/areas"
import { cn } from "@/lib/utils"

const itemClass = "flex w-full items-center gap-3 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
const idleClass = "text-sidebar-foreground hover:bg-sidebar-accent/60"
const smallClass = "flex items-center gap-2 rounded-md px-3 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
const mobileItemClass = "shrink-0 rounded-md px-3 py-1.5 text-sm whitespace-nowrap transition-colors"
const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(itemClass, isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : idleClass)

export function AppLayout() {
  const agent = useAgent()
  const t = useT(layout)
  const ta = useT(areaMessages)
  const { pathname } = useLocation()
  const mobileNav = useRef<HTMLElement>(null)
  const areas = useQuery({ queryKey: ["areas"], queryFn: api.areas, refetchInterval: 30_000 })
  const attention = new Map(areas.data?.map((a) => [a.area, a.attention]))
  useDesktopTitleBar()

  // The phone bar scrolls sideways: keep the current page's tab in view.
  useEffect(() => {
    mobileNav.current?.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView({ block: "nearest", inline: "center" })
  }, [pathname])

  const nav = [
    { to: "/", label: t("nav.today"), icon: Sun, end: true, count: 0 },
    ...AREAS.map((a) => ({ to: `/area/${a}`, label: ta(`area.${a}`), icon: AREA_STYLE[a].icon, end: false, count: attention.get(a) ?? 0 })),
  ]

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
          <nav className="-mx-1 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-1">
            {nav.map((item, i) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={(s) => cn(linkClass(s), i === 1 && "mt-4")}>
                <item.icon className="size-4" />
                <span className="flex-1">{item.label}</span>
                {item.count > 0 && (
                  <span className="min-w-5 rounded-full bg-amber-100 px-1.5 text-center text-[11px] font-semibold text-amber-800 tabular-nums dark:bg-amber-500/15 dark:text-amber-300">
                    {item.count}
                  </span>
                )}
              </NavLink>
            ))}
            <button onClick={() => agent.open()} className={cn(itemClass, idleClass, "mt-4")}>
              <Bot className="size-4" /> {t("nav.ask")}
            </button>
          </nav>
          <div className="mt-4 flex flex-col gap-0.5">
            <NavLink to="/settings" className={smallClass}>
              <Mail className="size-3.5" /> {t("nav.mail")}
            </NavLink>
            <NavLink to="/history" className={smallClass}>
              <History className="size-3.5" /> {t("nav.history")}
            </NavLink>
            <NavLink to="/trash" className={smallClass}>
              <Trash2 className="size-3.5" /> {t("nav.trash")}
            </NavLink>
          </div>
        </aside>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile navigation */}
        <nav
          ref={mobileNav}
          aria-label={t("navigation")}
          className="flex gap-1 overflow-x-auto border-b bg-sidebar px-3 py-2 pr-8 [scrollbar-width:none] select-none mask-r-from-[calc(100%-2rem)] md:hidden"
        >
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(mobileItemClass, isActive ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60")
              }
            >
              {item.label}
            </NavLink>
          ))}
          <NavLink to="/settings" className={cn(mobileItemClass, "hover:bg-sidebar-accent/60")}>
            {t("nav.mail")}
          </NavLink>
        </nav>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-28 md:px-10 md:pt-8">
          {/* Pages load on first visit: the menu stays in place meanwhile. */}
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </main>
        <AskBar />
      </div>
    </div>
  )
}

/** Binder is one sentence away on every page: type, press Enter, the agent answers. */
function AskBar() {
  const t = useT(layout)
  const agent = useAgent()
  const [text, setText] = useState("")
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 px-4 pb-4 md:left-60">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          const q = text.trim()
          agent.open(q || undefined)
          setText("")
        }}
        className="pointer-events-auto mx-auto flex max-w-2xl items-center gap-2 rounded-xl border bg-card p-1.5 pl-4"
      >
        <Bot className="size-4 shrink-0 text-primary" />
        <input
          ref={input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("askPlaceholder")}
          aria-label={t("nav.ask")}
          className="h-8 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground md:text-sm"
        />
        <kbd className="hidden rounded border px-1.5 font-sans text-[11px] text-muted-foreground sm:inline">{t("askShortcut")}</kbd>
        <button
          type="submit"
          aria-label={t("nav.ask")}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-80"
        >
          <ArrowUp className="size-4" />
        </button>
      </form>
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
