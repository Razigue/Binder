import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { ClockCounterClockwiseIcon, PlusIcon, RobotIcon } from "@phosphor-icons/react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { useT } from "@/i18n"
import { agent as messages } from "@/i18n/messages/agent"
import { api } from "@/lib/api"
import { AgentContext, type Viewing } from "./agent/context"
import { useAgentChat } from "./agent/useAgentChat"

// The conversation itself loads apart from the app shell, ahead of its first opening.
const loadPanel = () => import("./agent/AgentPanel")
const AgentPanel = lazy(() => loadPanel().then((m) => ({ default: m.AgentPanel })))

export function AgentProvider({ children }: { children: ReactNode }) {
  const t = useT(messages)
  const [isOpen, setOpen] = useState(false)
  const chat = useAgentChat()

  // A question sent from a page (shortcut, card, step) starts its own conversation.
  const open = (question?: string) => {
    setOpen(true)
    if (question) chat.ask(question, [], chat.turns.length, true)
  }

  // The context hands out stable functions that call the latest ones: pages using the agent do
  // not render again with every word of an answer.
  const latest = useRef({ open, view: chat.view, leave: chat.leave })
  useLayoutEffect(() => {
    latest.current = { open, view: chat.view, leave: chat.leave }
  })
  const value = useMemo(
    () => ({
      open: (question?: string) => latest.current.open(question),
      view: (doc: Viewing) => latest.current.view(doc),
      leave: (id: number) => latest.current.leave(id),
    }),
    [],
  )

  // Opening the chat brings the model back into memory while the question is typed.
  useEffect(() => {
    if (isOpen) api.warmModel().catch(() => {})
  }, [isOpen])

  useEffect(() => {
    const timer = setTimeout(() => void loadPanel(), 1500)
    return () => clearTimeout(timer)
  }, [])

  // Ctrl K (Cmd K) opens the agent from anywhere, ready to type.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <AgentContext value={value}>
      {children}
      <Sheet open={isOpen} onOpenChange={setOpen}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-lg">
          <SheetHeader className="flex-row items-center gap-2 border-b px-5 py-3.5 pr-12">
            <SheetTitle className="flex flex-1 items-center gap-2.5 text-lg">
              <RobotIcon className="size-5 text-primary" />
              {t("title")}
            </SheetTitle>
            <SheetDescription className="sr-only">{t("description")}</SheetDescription>
            <Button
              variant={chat.showHistory ? "secondary" : "ghost"}
              size="sm"
              onClick={() => chat.setShowHistory(!chat.showHistory)}
              aria-pressed={chat.showHistory}
            >
              <ClockCounterClockwiseIcon /> {t("history")}
            </Button>
            {(chat.turns.length > 0 || chat.showHistory) && (
              <Button variant="outline" size="sm" onClick={() => chat.begin()} title={t("newChat")}>
                <PlusIcon /> {t("newChatShort")}
              </Button>
            )}
          </SheetHeader>
          <Suspense fallback={<div className="flex-1" />}>
            <AgentPanel chat={chat} onNavigate={() => setOpen(false)} />
          </Suspense>
        </SheetContent>
      </Sheet>
    </AgentContext>
  )
}
