import { useState } from "react"
import { RobotIcon, NotePencilIcon, FolderPlusIcon, ListChecksIcon, CaretDownIcon, type Icon } from "@phosphor-icons/react"
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

type Category = "journeys" | "letters" | "folders"

/** Everything Binder prepares on request, and what it is following: the agent's catalogue.
 * Two steps: pick a category, then one of its actions. */
export function PreparePage() {
  const t = useT(messages)
  const tj = useT(journeyMessages)
  const agent = useAgent()
  const panels = usePanels()
  const [task, setTask] = useState<Task | null>(null)
  const [open, setOpen] = useState<Category | null>(null)
  const kinds = useJourneyKinds().data ?? []
  const active = (useJourneys().data ?? []).filter((j) => !j.closed)
  // The side column only when Binder is following something.
  const ongoing = useOngoing().count
  const letters = useLetters().data ?? []
  const side = ongoing > 0 || letters.some((l) => l.answered)

  const categories: { id: Category; icon: Icon; title: string; hint: string; tiles: React.ReactNode[] }[] = [
    {
      id: "journeys",
      icon: ListChecksIcon,
      title: tj("group"),
      hint: t("journeysHint"),
      tiles: kinds.map((info) => {
        const ongoing = active.find((j) => j.kind === info.kind)
        return (
          <Tile
            key={info.kind}
            icon={ListChecksIcon}
            title={info.title}
            hint={ongoing ? tj("progress", { done: ongoing.done, total: ongoing.total }) : tj(`kind.${info.kind}Hint`)}
            onClick={() => (ongoing ? panels.showJourney(ongoing.id) : setTask({ type: "journey", info }))}
          />
        )
      }),
    },
    {
      id: "letters",
      icon: NotePencilIcon,
      title: t("letters"),
      hint: t("lettersHint"),
      tiles: [
        ...LETTER_KINDS.map((kind) => (
          <Tile
            key={kind}
            icon={NotePencilIcon}
            title={t(`letter.${kind}`)}
            hint={t(`letter.${kind}Hint`)}
            onClick={() => setTask({ type: "letter", kind })}
          />
        )),
        <Tile
          key="custom"
          icon={NotePencilIcon}
          title={t("letter.custom")}
          hint={t("letter.customHint")}
          onClick={() => setTask({ type: "letter", kind: null })}
        />,
      ],
    },
    {
      id: "folders",
      icon: FolderPlusIcon,
      title: t("folders"),
      hint: t("foldersHint"),
      tiles: [
        ...FOLDER_KINDS.map((kind) => (
          <Tile
            key={kind}
            icon={FolderPlusIcon}
            title={t(`folder.${kind}`)}
            hint={t(`folder.${kind}Hint`)}
            onClick={() => setTask({ type: "folder", kind })}
          />
        )),
        <Tile
          key="custom"
          icon={FolderPlusIcon}
          title={t("folder.custom")}
          hint={t("folder.customHint")}
          onClick={() => setTask({ type: "folder", kind: null })}
        />,
      ],
    },
  ]
  const current = categories.find((c) => c.id === open)

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("pageSubtitle")} />
      <div className={cn("grid items-start gap-8", side && "xl:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_28rem]")}>
        <div className="min-w-0 space-y-8">
          <section>
            <h2 className="mb-3 font-semibold">{t("step1")}</h2>
            <div className="grid gap-3 md:grid-cols-3">
              {categories.map((c) => (
                <CategoryCard
                  key={c.id}
                  icon={c.icon}
                  title={c.title}
                  hint={c.hint}
                  count={t("choices", { count: c.tiles.length })}
                  expanded={open === c.id}
                  controls={`prepare-${c.id}`}
                  onClick={() => setOpen(open === c.id ? null : c.id)}
                />
              ))}
            </div>
          </section>
          {current && (
            <section id={`prepare-${current.id}`}>
              <h2 className="mb-3 font-semibold">
                {t("step2")} · <span className="text-muted-foreground">{current.title}</span>
              </h2>
              <ul className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">{current.tiles}</ul>
            </section>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-card px-5 py-4 ring-1 ring-foreground/10">
            <p className="text-sm text-muted-foreground">{t("otherwise")}</p>
            <Button variant="outline" onClick={() => agent.open()}>
              <RobotIcon /> {t("askAgent")}
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

function CategoryCard({
  icon: Icon,
  title,
  hint,
  count,
  expanded,
  controls,
  onClick,
}: {
  icon: Icon
  title: string
  hint: string
  count: string
  expanded: boolean
  controls: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      aria-expanded={expanded}
      aria-controls={controls}
      className={cn(
        "group flex h-full w-full flex-col gap-3 rounded-xl bg-card p-4 text-left ring-1 ring-foreground/10 transition-[background-color,box-shadow] outline-none hover:bg-accent/40 hover:shadow-sm hover:ring-foreground/20 focus-visible:ring-3 focus-visible:ring-ring/50",
        expanded && "bg-accent/40 shadow-sm ring-2 ring-primary hover:ring-primary",
      )}
    >
      <span className="flex w-full items-center gap-3">
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground",
            expanded && "bg-primary text-primary-foreground",
          )}
        >
          <Icon className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-medium">{title}</span>
          <span className="block text-xs text-muted-foreground">{count}</span>
        </span>
        <CaretDownIcon className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")} />
      </span>
      <span className="text-sm text-muted-foreground">{hint}</span>
    </button>
  )
}

function Tile({ icon: Icon, title, hint, onClick }: { icon: Icon; title: string; hint: string; onClick: () => void }) {
  return (
    <li>
      <button
        onClick={onClick}
        className="group flex h-full w-full items-start gap-3 rounded-xl bg-card px-4 py-3.5 text-left ring-1 ring-foreground/10 transition-[background-color,box-shadow] outline-none hover:bg-accent/40 hover:shadow-sm hover:ring-foreground/20 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
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
