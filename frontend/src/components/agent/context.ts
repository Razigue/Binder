import { createContext, use, useEffect } from "react"

/** Document open on screen: questions that name no other document are about it. */
export interface Viewing {
  id: number
  title: string
}

interface AgentContextValue {
  open: (question?: string) => void
  /** A document comes on screen. */
  view: (doc: Viewing) => void
  /** That document leaves the screen. */
  leave: (id: number) => void
}

export const AgentContext = createContext<AgentContextValue | null>(null)

export function useAgent() {
  const ctx = use(AgentContext)
  if (!ctx) throw new Error("useAgent must be used inside AgentProvider")
  return ctx
}

/** Tells the agent which document the page shows, while it is shown. */
export function useAgentViewing(doc: Viewing | undefined) {
  const { view, leave } = useAgent()
  const id = doc?.id
  const title = doc?.title
  useEffect(() => {
    if (id === undefined || title === undefined) return
    view({ id, title })
    return () => leave(id)
  }, [id, title, view, leave])
}
