import { Suspense, useEffect, useRef, useState, type ReactElement } from "react"
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom"
import { ArrowUpIcon, RobotIcon, FilesIcon, ClockCounterClockwiseIcon, CompassIcon, GearSixIcon, CheckSquareIcon, TrashIcon, PlusIcon, DeviceMobileIcon, UploadSimpleIcon, UserCircleIcon, type Icon } from "@phosphor-icons/react"
import { BinderMark } from "@/components/layout/BinderMark"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAgent } from "@/components/agent/context"
import { TitleBar } from "@/components/layout/TitleBar"
import { useDesktopWindow } from "@/components/layout/useDesktopWindow"
import { HistoryButtons } from "@/components/layout/HistoryNav"
import { useHistoryPosition, useScrollMemory } from "@/components/layout/history"
import { useUpload } from "@/components/upload/context"
import { useFeed, useLiveChanges, useProfile } from "@/hooks/queries"
import { useT } from "@/i18n"
import { layout } from "@/i18n/messages/layout"
import { cn } from "@/lib/utils"

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-[0.9375rem] font-medium transition-colors",
    isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/60",
  )

/** Three places, one button to add a paper and one bar to ask Binder, everywhere. */
export function AppLayout() {
  const t = useT(layout)
  const desktop = useDesktopWindow()
  const titleBar = desktop?.custom === true
  const location = useLocation()
  const history = useHistoryPosition()
  const scroller = useRef<HTMLDivElement>(null)
  useScrollMemory(scroller)
  const feed = useFeed()
  useNoFocusOnLaunch()
  useLiveChanges()
  // What needs the user: the to-do cards that are not merely for information.
  const waiting = feed.data?.items.filter((i) => i.tone !== "info").length ?? 0

  const nav = [
    { to: "/", label: t("nav.todo"), icon: CheckSquareIcon, end: true, count: waiting },
    { to: "/papers", label: t("nav.papers"), icon: FilesIcon, end: false, count: 0 },
    { to: "/procedures", label: t("nav.procedures"), icon: CompassIcon, end: false, count: 0 },
  ]

  const shell = (
    <div className={cn("flex", titleBar ? "min-h-full" : "min-h-svh")}>
      <a
        href="#main"
        onClick={(e) => {
          e.preventDefault()
          document.getElementById("main")?.focus()
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-background focus:px-4 focus:py-2.5 focus:text-sm focus:font-medium focus:shadow-sm"
      >
        {t("skipToContent")}
      </a>
      <div className="hidden w-60 shrink-0 border-r bg-sidebar md:block">
        <aside className="sticky top-0 flex h-[calc(100svh-var(--titlebar-height,0px))] flex-col px-3 py-5 select-none">
          {/* The desktop title bar already carries the logo and name. */}
          {!titleBar && (
            <div className="mb-6 flex items-center gap-3 px-2">
              <span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <BinderMark className="size-5" />
              </span>
              <p className="flex-1 text-[0.9375rem] font-semibold">Binder</p>
            </div>
          )}
          <AddMenu>
            <Button className="mb-5 h-11 w-full justify-start gap-2.5 px-3 text-[0.9375rem]">
              <PlusIcon className="size-4" weight="bold" /> {t("add")}
            </Button>
          </AddMenu>
          {/* The negative margin and padding leave room for focus rings, which overflow clips. */}
          <nav aria-label={t("navigation")} className="-m-1 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-1">
            {nav.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </nav>
          <ProfileMenu>
            <button type="button" className="mt-4 flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground">
              <UserCircleIcon className="size-5" />
              <ProfileName />
            </button>
          </ProfileMenu>
        </aside>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phone: the brand and the profile on top, the three places and ＋ at the bottom. */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b bg-sidebar px-4 py-2.5 md:hidden">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <BinderMark className="size-5" />
          </span>
          <p className="flex-1 text-[0.9375rem] font-semibold">Binder</p>
          <HistoryButtons position={history} buttonClassName="size-9" />
          <ProfileMenu>
            <Button variant="ghost" size="icon" aria-label={t("profile")}>
              <UserCircleIcon className="size-6" />
            </Button>
          </ProfileMenu>
        </header>
        {/* Without the desktop title bar, back and forward sit top left of the content and stay
            there while the page scrolls. */}
        {!titleBar && (
          <div className="sticky top-0 z-20 hidden h-12 shrink-0 items-center bg-background px-6 md:flex 2xl:px-10">
            <HistoryButtons position={history} buttonClassName="size-8" />
          </div>
        )}
        <main id="main" tabIndex={-1} className={cn("w-full flex-1 outline-none px-4 pt-6 pb-44 md:px-8 md:pb-28 2xl:px-12", titleBar ? "md:pt-8" : "md:pt-2")}>
          {/* Pages load on first visit: the menu stays in place meanwhile. */}
          <Suspense fallback={null}>
            {/* Each page fades in; a filter kept in the address does not replay it. */}
            <div key={location.pathname} className="animate-page">
              <Outlet />
            </div>
          </Suspense>
        </main>
        <AskBar />
        <nav
          aria-label={t("navigation")}
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t bg-sidebar pb-[env(safe-area-inset-bottom)] select-none md:hidden"
        >
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "relative flex min-h-16 flex-col items-center justify-center gap-1 px-1 text-xs font-medium",
                  isActive ? "text-primary" : "text-muted-foreground",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className="size-6" weight={isActive ? "fill" : "regular"} />
                  <span className="truncate">{item.label}</span>
                  {item.count > 0 && <CountBadge count={item.count} className="absolute top-1.5 left-1/2 ml-2" />}
                </>
              )}
            </NavLink>
          ))}
          <AddMenu>
            <button type="button" aria-label={t("add")} className="flex min-h-16 flex-col items-center justify-center gap-1 text-xs font-medium text-primary">
              <span className="flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <PlusIcon className="size-5" weight="bold" />
              </span>
              {t("add")}
            </button>
          </AddMenu>
        </nav>
      </div>
    </div>
  )

  if (!titleBar) return shell
  // Desktop window: the page scrolls under the title bar, whose buttons keep the window corner.
  return (
    <div className="flex h-svh flex-col">
      <TitleBar maximized={desktop.maximized} history={history} />
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
        {shell}
      </div>
    </div>
  )
}

/** ＋: add a paper, the phone scan first: the easiest for most papers. */
function AddMenu({ children }: { children: ReactElement }) {
  const t = useT(layout)
  const upload = useUpload()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={children} />
      <DropdownMenuContent align="start" side="bottom" className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel>{t("add.paper")}</DropdownMenuLabel>
          <MenuChoice icon={DeviceMobileIcon} title={t("add.scan")} hint={t("add.scanHint")} onClick={upload.scanWithPhone} featured />
          <MenuChoice icon={UploadSimpleIcon} title={t("add.file")} hint={t("add.fileHint")} onClick={upload.open} />
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function MenuChoice({
  icon: Icon,
  title,
  hint,
  onClick,
  featured,
}: {
  icon: Icon
  title: string
  hint: string
  onClick: () => void
  featured?: boolean
}) {
  return (
    <DropdownMenuItem onClick={onClick} className="items-start gap-3 py-2.5">
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          featured ? "bg-primary text-primary-foreground" : "bg-accent text-primary",
        )}
      >
        {/* The menu item recolours every descendant on hover: keep the icon readable on its chip. */}
        <Icon className={cn("size-4", featured ? "text-primary-foreground!" : "text-primary!")} />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
    </DropdownMenuItem>
  )
}

/**
 * Binder is one sentence away on every page: type, press Enter, the agent answers. On a phone it
 * sits just above the bottom bar.
 */
function AskBar() {
  const t = useT(layout)
  const agent = useAgent()
  const [text, setText] = useState("")
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-20 px-4 pb-3 md:bottom-0 md:left-60 md:pb-4">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          agent.open(text.trim() || undefined)
          setText("")
        }}
        className="pointer-events-auto mx-auto flex max-w-2xl items-center gap-2 rounded-xl border bg-card p-1.5 pl-4 shadow-sm transition-colors focus-within:border-primary/40"
      >
        <RobotIcon className="size-5 shrink-0 text-primary" />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("askPlaceholder")}
          aria-label={t("ask")}
          className="h-10 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground md:text-sm"
        />
        <kbd className="hidden rounded border px-1.5 font-sans text-[0.6875rem] text-muted-foreground sm:inline">{t("askShortcut")}</kbd>
        <button
          type="submit"
          aria-label={t("ask")}
          className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-80"
        >
          <ArrowUpIcon className="size-4" weight="bold" />
        </button>
      </form>
    </div>
  )
}

/** History, trash and settings: out of the way, one tap from the profile. */
function ProfileMenu({ children }: { children: ReactElement }) {
  const t = useT(layout)
  const navigate = useNavigate()
  const items = [
    { to: "/settings", label: t("nav.settings"), icon: GearSixIcon },
    { to: "/history", label: t("nav.history"), icon: ClockCounterClockwiseIcon },
    { to: "/trash", label: t("nav.trash"), icon: TrashIcon },
  ]
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={children} />
      <DropdownMenuContent align="end" side="top" className="w-56">
        {items.map(({ to, label, icon: Icon }) => (
          <DropdownMenuItem key={to} onClick={() => navigate(to)} className="min-h-10">
            <Icon /> {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function ProfileName() {
  const t = useT(layout)
  const name = useProfile().data?.name.trim()
  return <span className="min-w-0 flex-1 truncate">{name || t("profile")}</span>
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
      {({ isActive }) => (
        <>
          <Icon className="size-5" weight={isActive ? "fill" : "regular"} />
          <span className="flex-1">{label}</span>
          {count > 0 && <CountBadge count={count} />}
        </>
      )}
    </NavLink>
  )
}

/** The number of cards waiting: it fades in again when it changes, so a new one is noticed. */
function CountBadge({ count, className }: { count: number; className?: string }) {
  const t = useT(layout)
  return (
    <span
      key={count}
      className={cn(
        "animate-pop min-w-5 rounded-full bg-amber-100 px-1.5 text-center text-[0.6875rem] font-semibold text-amber-800 tabular-nums dark:bg-amber-500/15 dark:text-amber-300",
        className,
      )}
    >
      <span aria-hidden>{count}</span>
      <span className="sr-only">{t("waiting", { count })}</span>
    </span>
  )
}
