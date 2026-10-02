import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { useT } from "@/i18n"
import { common } from "@/i18n/messages/common"

/** Asks for explicit consent before an irreversible action. With `typeToConfirm`, the user must
 * also type that word: for actions too heavy for a single click. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  destructive = true,
  typeToConfirm,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: React.ReactNode
  confirmLabel: string
  /** Instead of "Cancel", when the action itself is a cancellation. */
  cancelLabel?: string
  destructive?: boolean
  typeToConfirm?: string
  onConfirm: () => Promise<unknown> | void
}) {
  const t = useT(common)
  const [busy, setBusy] = useState(false)
  const [typed, setTyped] = useState("")
  const confirmed = !typeToConfirm || typed.trim().toLocaleUpperCase() === typeToConfirm.toLocaleUpperCase()
  const changeOpen = (next: boolean) => {
    if (!next) setTyped("")
    onOpenChange(next)
  }
  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {typeToConfirm && (
          <div className="grid gap-2">
            <Label htmlFor="confirm-word">{t("confirm.type", { word: typeToConfirm })}</Label>
            <Input
              id="confirm-word"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
            />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => changeOpen(false)} disabled={busy}>
            {cancelLabel ?? t("action.cancel")}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            disabled={busy || !confirmed}
            onClick={async () => {
              setBusy(true)
              try {
                await onConfirm()
                changeOpen(false)
              } finally {
                setBusy(false)
              }
            }}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
