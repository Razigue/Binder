import { useEffect } from "react"
import { toast } from "sonner"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { api, onUndoable } from "@/lib/api"

/** Every change the backend can undo shows a toast with "Undo" for a few seconds. */
export function UndoToasts() {
  const t = useT(feed)
  const invalidate = useInvalidateAll()
  useEffect(() => {
    onUndoable((token, body) => {
      const message =
        body && typeof body === "object" && "message" in body && typeof body.message === "string" ? body.message : t("done")
      toast.success(message, {
        duration: 15000,
        action: {
          label: t("undo"),
          onClick: () =>
            api
              .undo(token)
              .then(() => {
                invalidate()
                toast(t("undone"))
              })
              .catch((e: Error) => toast.error(e.message)),
        },
      })
    })
    return () => onUndoable(null)
  }, [t, invalidate])
  return null
}
