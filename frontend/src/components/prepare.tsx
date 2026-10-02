import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { CaretRightIcon, NotePencilIcon, FolderPlusIcon, ListChecksIcon, CircleNotchIcon, type Icon } from "@phosphor-icons/react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { JourneyStart } from "@/components/journey"
import { FolderView, usePanels } from "@/components/panels"
import { useInvalidateAll, useJourneyKinds, useJourneys } from "@/hooks/queries"
import { useT } from "@/i18n"
import { journey as journeyMessages } from "@/i18n/messages/journey"
import { prepare as messages } from "@/i18n/messages/prepare"
import { api, type Area, type Folder, type FolderKind, type JourneyKind, type JourneyKindInfo, type LetterKind } from "@/lib/api"

export type Task =
  | { type: "folder"; kind: FolderKind | null }
  | { type: "letter"; kind: LetterKind | null }
  | { type: "journey"; info: JourneyKindInfo }

// What each area usually needs; the Prepare page lists everything, the agent covers the rest.
const FOLDERS: Record<Area, FolderKind[]> = {
  housing: ["rental", "caf"],
  money: ["mortgage"],
  work: ["caf", "retirement"],
  family: ["school"],
  health: [],
  identity: ["identity_renewal", "rental"],
  vehicle: [],
}
const LETTERS: Record<Area, LetterKind[]> = {
  housing: ["termination", "complaint", "formal_notice", "address_change"],
  money: ["payment_plan", "appeal", "complaint", "request"],
  work: ["request", "appeal", "payment_plan"],
  family: ["request"],
  health: ["request", "complaint", "appeal"],
  identity: ["request"],
  vehicle: ["termination", "complaint", "appeal"],
}
const JOURNEYS: Record<Area, JourneyKind[]> = {
  housing: ["moving"],
  money: ["tax_return"],
  work: [],
  family: ["birth"],
  health: [],
  identity: [],
  vehicle: [],
}
/** The files, letters and life events of one area: one tap, then Binder does the work. */
export function PrepareCard({ area }: { area: Area }) {
  const t = useT(messages)
  const tj = useT(journeyMessages)
  const panels = usePanels()
  const [task, setTask] = useState<Task | null>(null)
  const kinds = useJourneyKinds().data ?? []
  const active = (useJourneys().data ?? []).filter((j) => !j.closed)
  const folders = FOLDERS[area]
  const letters = LETTERS[area]
  const wanted = JOURNEYS[area]
  const ongoing = active.filter((j) => wanted.includes(j.kind))
  const startable = kinds.filter((k) => wanted.includes(k.kind) && !ongoing.some((j) => j.kind === k.kind))

  return (
    <Card className="gap-0 p-0">
      <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
        <div>
          <h2 className="font-semibold">{t("title")}</h2>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
        <Link to="/procedures" className="shrink-0 text-sm font-medium text-primary hover:underline">
          {t("seeAll")}
        </Link>
      </div>
      {ongoing.length + startable.length > 0 && (
        <Group label={tj("group")}>
          {ongoing.map((j) => (
            <Row
              key={j.id}
              icon={ListChecksIcon}
              title={j.title}
              hint={tj("progress", { done: j.done, total: j.total })}
              onClick={() => panels.showJourney(j.id)}
            />
          ))}
          {startable.map((info) => (
            <Row
              key={info.kind}
              icon={ListChecksIcon}
              title={info.title}
              hint={tj(`kind.${info.kind}Hint`)}
              onClick={() => setTask({ type: "journey", info })}
            />
          ))}
        </Group>
      )}
      <Group label={t("folders")}>
        {folders.map((kind) => (
          <Row
            key={kind}
            icon={FolderPlusIcon}
            title={t(`folder.${kind}`)}
            hint={t(`folder.${kind}Hint`)}
            onClick={() => setTask({ type: "folder", kind })}
          />
        ))}
        <Row icon={FolderPlusIcon} title={t("folder.custom")} hint={t("folder.customHint")} onClick={() => setTask({ type: "folder", kind: null })} />
      </Group>
      <Group label={t("letters")}>
        {letters.map((kind) => (
          <Row
            key={kind}
            icon={NotePencilIcon}
            title={t(`letter.${kind}`)}
            hint={t(`letter.${kind}Hint`)}
            onClick={() => setTask({ type: "letter", kind })}
          />
        ))}
      </Group>
      <PrepareDialog task={task} onClose={() => setTask(null)} />
    </Card>
  )
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-t">
      <p className="px-5 pt-3 pb-1 text-xs font-medium text-muted-foreground">{label}</p>
      <ul className="pb-2">{children}</ul>
    </div>
  )
}

function Row({ icon: Icon, title, hint, onClick }: { icon: Icon; title: string; hint: string; onClick: () => void }) {
  return (
    <li>
      <button onClick={onClick} className="flex w-full items-center gap-3 px-5 py-2.5 text-left transition-colors hover:bg-muted/40">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{title}</span>
          <span className="block truncate text-xs text-muted-foreground">{hint}</span>
        </span>
        <CaretRightIcon className="size-4 shrink-0 text-muted-foreground" />
      </button>
    </li>
  )
}

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
