import { useNavigate } from "react-router-dom"
import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react"
import { useT } from "@/i18n"
import { layout } from "@/i18n/messages/layout"
import { cn } from "@/lib/utils"
import type { HistoryPosition } from "./history"

/** Back and forward, as in a browser: also Alt + ← / → and the mouse side buttons. */
export function HistoryButtons({ position, className, buttonClassName }: {
  position: HistoryPosition
  className?: string
  buttonClassName?: string
}) {
  const t = useT(layout)
  const navigate = useNavigate()
  const button = cn(
    "flex items-center justify-center rounded-md text-foreground/80 outline-none transition-colors hover:bg-foreground/[0.07] hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring active:bg-foreground/[0.12] disabled:pointer-events-none disabled:text-foreground/25",
    buttonClassName,
  )
  // Nowhere to go yet (the first page): two dead arrows would only read as broken. The space is
  // kept, so nothing moves when they appear.
  const idle = !position.canBack && !position.canForward
  return (
    <div className={cn("flex items-center gap-0.5", idle && "invisible", className)}>
      <button
        type="button"
        className={button}
        disabled={!position.canBack}
        onClick={() => navigate(-1)}
        aria-label={t("history.back")}
        title={t("history.backHint")}
      >
        <ArrowLeftIcon className="size-4" weight="bold" />
      </button>
      <button
        type="button"
        className={button}
        disabled={!position.canForward}
        onClick={() => navigate(1)}
        aria-label={t("history.forward")}
        title={t("history.forwardHint")}
      >
        <ArrowRightIcon className="size-4" weight="bold" />
      </button>
    </div>
  )
}
