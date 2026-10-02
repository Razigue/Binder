import { Suspense, useEffect, useRef, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ArrowUpIcon, VaultIcon, RobotIcon, FilesIcon, ClockCounterClockwiseIcon, ListChecksIcon, GearSixIcon, SunIcon, TrashIcon, type Icon } from "@phosphor-icons/react"
import { useAgent } from "@/components/agent"
import { TitleBar, useDesktopWindow } from "@/components/layout/TitleBar"
import { useT } from "@/i18n"
import { area as areaMessages } from "@/i18n/messages/area"
import { layout } from "@/i18n/messages/layout"
import { AREAS, api } from "@/lib/api"
import { AREA_STYLE } from "@/lib/areas"
import { cn } from "@/lib/utils"

const itemClass = "flex min-h-10 w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors"
const idleClass = "text-sidebar-foreground hover:bg-sidebar-accent/60"
const smallClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-9 items-center gap-3 rounded-lg px-3 py-1.5 text-sm transition-colors",
    isActive ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
  )
const mobileItemClass = "shrink-0 rounded-lg px-3.5 py-2 text-sm whitespace-nowrap transition-colors"
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
  const desktop = useDesktopWindow()
  const titleBar = desktop?.custom === true
  useNoFocusOnLaunch()

  // The phone bar scrolls sideways: keep the current page's tab in view.
  useEffect(() => {
    mobileNav.current?.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView({ block: "nearest", inline: "center" })
  }, [pathname])

  const main = [
    { to: "/", label: t("nav.today"), icon: SunIcon, end: true, count: 0 },
    { to: "/prepare", label: t("nav.prepare"), icon: ListChecksIcon, end: false, count: 0 },
    { to: "/documents", label: t("nav.documents"), icon: FilesIcon, end: false, count: 0 },
  ]
  const lifeAreas = AREAS.map((a) => ({
    to: `/area/${a}`,
    label: ta(`area.${a}`),
    icon: AREA_STYLE[a].icon,
    end: false,
    count: attention.get(a) ?? 0,
  }))
  const mobile = [main[0], ...lifeAreas, main[1], main[2], { to: "/settings", label: t("nav.settings"), icon: GearSixIcon, end: false, count: 0 }]
  // The ask bar sits on every page but Today, which opens on its own composer.
  const askBar = pathname !== "/"

  const shell = (
    <div className={cn("flex", titleBar ? "min-h-full" : "min-h-svh")}>
      <div className="hidden w-60 shrink-0 border-r bg-sidebar md:block">
        <aside className="sticky top-0 flex h-[calc(100svh-var(--titlebar-height,0px))] flex-col px-3 py-5 select-none">
          {/* The desktop title bar already carries the logo and name. */}
          {!titleBar && (
            <div className="mb-6 flex items-center gap-3 px-2">
              <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <VaultIcon className="size-4" />
              </span>
              <p className="text-[15px] font-semibold">Binder</p>
            </div>
          )}
          {/* The agent first: one click, or Ctrl K, from anywhere. */}
          <button
            onClick={() => agent.open()}
            title={t("askShortcut")}
            className="mb-5 flex h-10 w-full items-center gap-2.5 rounded-lg border bg-card px-3 text-left text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <RobotIcon className="size-4 text-primary" />
            <span className="flex-1 truncate">{t("nav.ask")}</span>
          </button>
          {/* The negative margin and padding leave room for focus rings, which overflow clips. */}
          <nav aria-label={t("navigation")} className="-m-1 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-1">
            {main.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
            <p className="mt-5 mb-1 px-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{t("nav.areas")}</p>
            {lifeAreas.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </nav>
          <div className="mt-4 flex flex-col gap-0.5">
            <NavLink to="/history" className={smallClass}>
              <ClockCounterClockwiseIcon className="size-4" /> {t("nav.history")}
            </NavLink>
            <NavLink to="/trash" className={smallClass}>
              <TrashIcon className="size-4" /> {t("nav.trash")}
            </NavLink>
            <NavLink to="/settings" className={smallClass}>
              <GearSixIcon className="size-4" /> {t("nav.settings")}
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
          <button onClick={() => agent.open()} aria-label={t("nav.ask")} className={cn(mobileItemClass, "flex items-center gap-1.5 bg-primary text-primary-foreground")}>
            <RobotIcon className="size-4" /> {t("nav.ask")}
          </button>
          {mobile.map((item) => (
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
        </nav>
        <main className={cn("w-full flex-1 px-4 pt-6 md:px-8 md:pt-8 2xl:px-12", askBar ? "pb-28" : "pb-12")}>
          {/* Pages load on first visit: the menu stays in place meanwhile. */}
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </main>
        {askBar && <AskBar />}
      </div>
    </div>
  )

  if (!titleBar) return shell
  // Desktop window: the page scrolls under the title bar, whose buttons keep the window corner.
  return (
    <div className="flex h-svh flex-col">
      <TitleBar maximized={desktop.maximized} />
      <div className="min-h-0 flex-1 overflow-y-auto">{shell}</div>
    </div>
  )
}

/**
 * The desktop shell hands keyboard focus to the page when its window opens, which lands on the
 * first menu link and draws its focus ring. Focus that arrives before the user has pressed a key
 * or clicked is not theirs: drop it.
 */
function useNoFocusOnLaunch() {
  useEffect(() => {
    const blur = () => {
      const active = document.activeElement
      if (active instanceof HTMLElement && active !== document.body) active.blur()
    }
    const stop = () => {
      window.removeEventListener("focusin", blur, true)
      window.removeEventListener("keydown", stop, true)
      window.removeEventListener("pointerdown", stop, true)
    }
    blur()
    window.addEventListener("focusin", blur, true)
    window.addEventListener("keydown", stop, true)
    window.addEventListener("pointerdown", stop, true)
    return stop
  }, [])
}

function NavItem({ to, label, icon: Icon, end, count }: { to: string; label: string; icon: Icon; end: boolean; count: number }) {
  return (
    <NavLink to={to} end={end} className={linkClass}>
      <Icon className="size-4" />
      <span className="flex-1">{label}</span>
      {count > 0 && (
        <span className="min-w-5 rounded-full bg-amber-100 px-1.5 text-center text-[11px] font-semibold text-amber-800 tabular-nums dark:bg-amber-500/15 dark:text-amber-300">
          {count}
        </span>
      )}
    </NavLink>
  )
}

/** Binder is one sentence away on every page: type, press Enter, the agent answers. */
function AskBar() {
  const t = useT(layout)
  const agent = useAgent()
  const [text, setText] = useState("")

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 px-4 pb-4 md:left-60">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          const q = text.trim()
          agent.open(q || undefined)
          setText("")
        }}
        className="pointer-events-auto mx-auto flex max-w-2xl items-center gap-2 rounded-xl border bg-card p-2 pl-4"
      >
        <RobotIcon className="size-4 shrink-0 text-primary" />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("askPlaceholder")}
          aria-label={t("nav.ask")}
          className="h-10 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground md:text-sm"
        />
        <kbd className="hidden rounded border px-1.5 font-sans text-[11px] text-muted-foreground sm:inline">{t("askShortcut")}</kbd>
        <button
          type="submit"
          aria-label={t("nav.ask")}
          className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-80"
        >
          <ArrowUpIcon className="size-4" />
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
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  )
}
