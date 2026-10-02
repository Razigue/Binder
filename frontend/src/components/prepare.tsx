import { useEffect, useRef, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { CircleNotchIcon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { JourneyStart } from "@/components/journey"
import { FolderView, usePanels } from "@/components/panels"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { prepare as messages } from "@/i18n/messages/prepare"
import { api, type Folder, type FolderKind, type JourneyKindInfo, type LetterKind } from "@/lib/api"

export type Task =
  | { type: "folder"; kind: FolderKind | null }
  | { type: "letter"; kind: LetterKind | null }
  | { type: "journey"; info: JourneyKindInfo }

export function PrepareDialog({ task, onClose }: { task: Task | null; onClose: () => void }) {
  const t = useT(messages)
  const panels = usePanels()
  const title = !task
    ? ""
    : task.type === "journey"
      ? task.info.title
      : task.type === "letter"
        ? t(`letter.${task.kind ?? "custom"}`)
        : task.kind
          ? t(`folder.${task.kind}`)
          : t("folder.custom")
  return (
    <Dialog open={task !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] gap-4 overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-lg">{title}</DialogTitle>
          <DialogDescription>{task?.type === "journey" ? task.info.description : t("hint")}</DialogDescription>
        </DialogHeader>
        {task?.type === "journey" && (
          <JourneyStart
            key={task.info.kind}
            info={task.info}
            onStarted={(j) => {
              onClose()
              panels.showJourney(j.id)
            }}
          />
        )}
        {task?.type === "folder" && <FolderTask key={task.kind ?? "custom"} kind={task.kind} />}
        {task?.type === "letter" && <LetterTask key={task.kind ?? "custom"} kind={task.kind} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function FolderTask({ kind }: { kind: FolderKind | null }) {
  const t = useT(messages)
  const [purpose, setPurpose] = useState("")
  const [folder, setFolder] = useState<Folder | null>(null)
  const invalidate = useInvalidateAll()
  const run = useMutation({
    mutationFn: (what: string) => api.prepareFolder(what),
    onSuccess: (f) => {
      setFolder(f)
      invalidate()
    },
    onError: (e) => toast.error(e.message),
  })
  // A known file needs no question: Binder starts at once (once, even in strict mode).
  const started = useRef(false)
  const { mutate } = run
  useEffect(() => {
    if (kind && !started.current) {
      started.current = true
      mutate(kind)
    }
  }, [kind, mutate])

  if (folder) return <FolderView folder={folder} />
  if (run.isPending || kind) return <Working />
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (purpose.trim()) run.mutate(purpose.trim())
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="folder-purpose">{t("purpose")}</Label>
        <Textarea id="folder-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder={t("purpose.folder")} rows={2} autoFocus />
      </div>
      <Button type="submit" disabled={!purpose.trim()}>
        {t("prepare")}
      </Button>
    </form>
  )
}

function LetterTask({ kind, onDone }: { kind: LetterKind | null; onDone: () => void }) {
  const t = useT(messages)
  const panels = usePanels()
  const invalidate = useInvalidateAll()
  const [purpose, setPurpose] = useState("")
  const write = useMutation({
    mutationFn: () => api.writeLetter({ kind: kind ?? undefined, purpose: purpose.trim() }),
    onSuccess: (letter) => {
      invalidate()
      onDone()
      panels.showLetter(letter)
    },
    onError: (e) => toast.error(e.message),
  })
  if (write.isPending) return <Working />
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        // Without a kind, the purpose is all Binder has to go on.
        if (kind || purpose.trim()) write.mutate()
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="letter-purpose">{t("purpose")}</Label>
        <Textarea id="letter-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder={t(`purpose.${kind ?? "custom"}`)} rows={3} autoFocus />
        {kind && <p className="text-xs text-muted-foreground">{t("letterHint")}</p>}
      </div>
      <Button type="submit" disabled={!kind && !purpose.trim()}>
        {t("write")}
      </Button>
    </form>
  )
}

function Working() {
  const t = useT(messages)
  return (
    <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
      <CircleNotchIcon className="size-4 animate-spin" /> {t("working")}
    </p>
  )
}
