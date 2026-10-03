import { createContext, use } from "react"
import type { Letter } from "@/lib/api"

export interface Panels {
  showLetter: (letter: Letter) => void
  showReport: (batch: string) => void
  showJourney: (id: number) => void
  /** The question panel: every question, or those about these documents. */
  showQuestions: (documentIds?: number[]) => void
}

export const PanelsContext = createContext<Panels | null>(null)

export function usePanels() {
  const ctx = use(PanelsContext)
  if (!ctx) throw new Error("usePanels must be used inside PanelsProvider")
  return ctx
}
