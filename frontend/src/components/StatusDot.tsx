import { useStatus } from "@/hooks/queries"
import { cn } from "@/lib/utils"

export function LocalBadge({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground", className)}>
      <span className="size-2 rounded-full bg-emerald-500 ring-4 ring-emerald-500/15" />
      Local
    </span>
  )
}

export function EngineInfo() {
  const { data } = useStatus()
  if (!data) return null
  return (
    <p className="text-[11px] leading-snug text-muted-foreground">
      {data.llm_available ? `IA locale : ${data.llm_model}` : "IA locale inactive · règles"}
      {" · "}
      {data.ocr_engine ? `OCR ${data.ocr_engine}` : "sans OCR"}
    </p>
  )
}
