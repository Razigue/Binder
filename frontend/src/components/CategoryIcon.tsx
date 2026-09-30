import type { Category } from "@/lib/api"
import { CATEGORY_STYLE } from "@/lib/categories"
import { cn } from "@/lib/utils"

export function CategoryIcon({ category, size = "md" }: { category: Category; size?: "sm" | "md" | "lg" }) {
  const { icon: Icon, tone } = CATEGORY_STYLE[category]
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg",
        tone,
        size === "sm" && "size-7 [&_svg]:size-3.5",
        size === "md" && "size-9 [&_svg]:size-4",
        size === "lg" && "size-11 [&_svg]:size-5",
      )}
    >
      <Icon />
    </span>
  )
}
