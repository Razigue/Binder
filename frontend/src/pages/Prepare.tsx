import { useState } from "react"
import { Bot, FilePen, FolderPlus, ListChecks, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAgent } from "@/components/agent"
import { PageHeader } from "@/components/layout/AppLayout"
import { FinishedLetters, Ongoing, useOngoing } from "@/components/ongoing"
import { PrepareDialog, type Task } from "@/components/prepare"
import { usePanels } from "@/components/panels"
import { useJourneyKinds, useJourneys, useLetters } from "@/hooks/queries"
import { useT } from "@/i18n"
import { journey as journeyMessages } from "@/i18n/messages/journey"
import { prepare as messages } from "@/i18n/messages/prepare"
import { FOLDER_KINDS, LETTER_KINDS } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Everything Binder prepares on request, and what it is following: the agent's catalogue. */
export function PreparePage() {
  const t = useT(messages)
  const tj = useT(journeyMessages)
  const agent = useAgent()
  const panels = usePanels()
  const [task, setTask] = useState<Task | null>(null)
  const kinds = useJourneyKinds().data ?? []
  const active = (useJourneys().data ?? []).filter((j) => !j.closed)
  // The side column only when Binder is following something.
  const ongoing = useOngoing().count
  const letters = useLetters().data ?? []
  const side = ongoing > 0 || letters.some((l) => l.answered)

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("pageSubtitle")} />
      <div className={cn("grid items-start gap-8", side && "xl:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]")}>
        <div className="min-w-0 space-y-8">
          <Section title={tj("group")} hint={t("journeysHint")}>
            {kinds.map((info) => {
              const ongoing = active.find((j) => j.kind === info.kind)
              return (
                <Tile
                  key={info.kind}
                  icon={ListChecks}
                  title={info.title}
                  hint={ongoing ? tj("progress", { done: ongoing.done, total: ongoing.total }) : tj(`kind.${info.kind}Hint`)}
                  onClick={() => (ongoing ? panels.showJourney(ongoing.id) : setTask({ type: "journey", info }))}
                />
              )
            })}
          </Section>
          <Section title={t("letters")} hint={t("lettersHint")}>
            {LETTER_KINDS.map((kind) => (
              <Tile
                key={kind}
                icon={FilePen}
                title={t(`letter.${kind}`)}
                hint={t(`letter.${kind}Hint`)}
                onClick={() => setTask({ type: "letter", kind })}
              />
            ))}
            <Tile
              icon={FilePen}
              title={t("letter.custom")}
              hint={t("letter.customHint")}
              onClick={() => setTask({ type: "letter", kind: null })}
            />
          </Section>
          <Section title={t("folders")} hint={t("foldersHint")}>
            {FOLDER_KINDS.map((kind) => (
              <Tile
                key={kind}
                icon={FolderPlus}
                title={t(`folder.${kind}`)}
                hint={t(`folder.${kind}Hint`)}
                onClick={() => setTask({ type: "folder", kind })}
              />
            ))}
            <Tile
              icon={FolderPlus}
              title={t("folder.custom")}
              hint={t("folder.customHint")}
              onClick={() => setTask({ type: "folder", kind: null })}
            />
          </Section>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-card px-5 py-4 ring-1 ring-foreground/10">
            <p className="text-sm text-muted-foreground">{t("otherwise")}</p>
            <Button variant="outline" onClick={() => agent.open()}>
              <Bot /> {t("askAgent")}
            </Button>
          </div>
        </div>
        {side && (
          <aside className="space-y-6 xl:order-none order-first">
            <Ongoing />
            <FinishedLetters />
          </aside>
        )}
      </div>
      <PrepareDialog task={task} onClose={() => setTask(null)} />
    </>
  )
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-semibold">{title}</h2>
      <p className="mb-3 text-sm text-muted-foreground">{hint}</p>
      <ul className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">{children}</ul>
    </section>
  )
}

function Tile({ icon: Icon, title, hint, onClick }: { icon: LucideIcon; title: string; hint: string; onClick: () => void }) {
  return (
    <li>
      <button
        onClick={onClick}
        className="flex h-full w-full items-start gap-3 rounded-xl bg-card px-4 py-3.5 text-left ring-1 ring-foreground/10 transition-shadow hover:shadow-sm"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="size-4" />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-medium">{title}</span>
          <span className="block text-xs text-muted-foreground">{hint}</span>
        </span>
      </button>
    </li>
  )
}
