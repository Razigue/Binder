import { useT } from "@/i18n"
import { statusDot } from "@/i18n/messages/statusDot"
import { cn } from "@/lib/utils"

export function LocalBadge({ className }: { className?: string }) {
  const t = useT(statusDot)
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground", className)}>
      <span className="size-2 rounded-full bg-emerald-500 ring-4 ring-emerald-500/15" />
      {t("local")}
    </span>
  )
}

