import { Suspense, useEffect } from "react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { VaultIcon, RobotIcon, FilesIcon, ClockCounterClockwiseIcon, CompassIcon, GearSixIcon, CheckSquareIcon, TrashIcon, PlusIcon, DeviceMobileIcon, UploadSimpleIcon, UserCircleIcon, type Icon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAgent } from "@/components/agent"
import { TitleBar, useDesktopWindow } from "@/components/layout/TitleBar"
import { useUpload } from "@/components/upload"
import { useFeed, useProfile } from "@/hooks/queries"
import { useT } from "@/i18n"
import { layout } from "@/i18n/messages/layout"
import { cn } from "@/lib/utils"

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-[15px] font-medium transition-colors",
    isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/60",
  )

/** Three places, and one button to add a paper or ask Binder, everywhere. */
export function AppLayout() {
  const t = useT(layout)
  const desktop = useDesktopWindow()
  const titleBar = desktop?.custom === true
  const feed = useFeed()
  useNoFocusOnLaunch()
  // What needs the user: the to-do cards that are not merely for information.
  const waiting = feed.data?.items.filter((i) => i.tone !== "info").length ?? 0

  const nav = [
    { to: "/", label: t("nav.todo"), icon: CheckSquareIcon, end: true, count: waiting },
    { to: "/papers", label: t("nav.papers"), icon: FilesIcon, end: false, count: 0 },
    { to: "/procedures", label: t("nav.procedures"), icon: CompassIcon, end: false, count: 0 },
  ]

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
          <AddMenu>
            <Button className="mb-5 h-11 w-full justify-start gap-2.5 px-3 text-[15px]">
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
            <button className="mt-4 flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground">
              <UserCircleIcon className="size-5" />
              <ProfileName />
            </button>
          </ProfileMenu>
        </aside>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phone: the brand and the profile on top, the three places and ＋ at the bottom. */}
        <header className="flex items-center gap-3 border-b bg-sidebar px-4 py-2.5 md:hidden">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <VaultIcon className="size-4" />
          </span>
          <p className="flex-1 text-[15px] font-semibold">Binder</p>
          <ProfileMenu>
            <Button variant="ghost" size="icon" aria-label={t("profile")}>
              <UserCircleIcon className="size-6" />
            </Button>
          </ProfileMenu>
        </header>
        <main className="w-full flex-1 px-4 pt-6 pb-28 md:px-8 md:pt-8 md:pb-12 2xl:px-12">
          {/* Pages load on first visit: the menu stays in place meanwhile. */}
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </main>
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
              <item.icon className="size-6" />
              <span className="truncate">{item.label}</span>
              {item.count > 0 && (
                <span className="absolute top-1.5 left-1/2 ml-2 min-w-5 rounded-full bg-amber-100 px-1.5 text-center text-[11px] font-semibold text-amber-800 tabular-nums dark:bg-amber-500/15 dark:text-amber-300">
                  {item.count}
                </span>
              )}
            </NavLink>
          ))}
          <AddMenu>
            <button aria-label={t("add")} className="flex min-h-16 flex-col items-center justify-center gap-1 text-xs font-medium text-primary">
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
      <TitleBar maximized={desktop.maximized} />
      <div className="min-h-0 flex-1 overflow-y-auto">{shell}</div>
    </div>
  )
}

/** ＋: add a paper (the phone scan first: the easiest for most papers) or ask Binder. */
function AddMenu({ children }: { children: React.ReactElement }) {
  const t = useT(layout)
  const upload = useUpload()
  const agent = useAgent()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={children} />
      <DropdownMenuContent align="start" side="bottom" className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel>{t("add.paper")}</DropdownMenuLabel>
          <MenuChoice icon={DeviceMobileIcon} title={t("add.scan")} hint={t("add.scanHint")} onClick={upload.scanWithPhone} featured />
          <MenuChoice icon={UploadSimpleIcon} title={t("add.file")} hint={t("add.fileHint")} onClick={upload.open} />
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <MenuChoice icon={RobotIcon} title={t("add.ask")} hint={t("add.askHint")} onClick={() => agent.open()} />
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
        <Icon className="size-4" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
    </DropdownMenuItem>
  )
}

/** History, trash and settings: out of the way, one tap from the profile. */
function ProfileMenu({ children }: { children: React.ReactElement }) {
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
      <Icon className="size-5" />
      <span className="flex-1">{label}</span>
      {count > 0 && (
        <span className="min-w-5 rounded-full bg-amber-100 px-1.5 text-center text-[11px] font-semibold text-amber-800 tabular-nums dark:bg-amber-500/15 dark:text-amber-300">
          {count}
        </span>
      )}
    </NavLink>
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
