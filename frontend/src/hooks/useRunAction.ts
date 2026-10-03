import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"
import { useAgent } from "@/components/agent/context"
import { usePanels } from "@/components/panels/context"
import { useUpload } from "@/components/upload/context"
import { useInvalidateAll } from "@/hooks/queries"
import { api, type FeedAction } from "@/lib/api"
import { openExternal } from "@/lib/external"

// Identifies one action among a card's actions, to spot which button is running.
const actionKey = (action: FeedAction) => `${action.type}:${JSON.stringify(action.params)}`

/** Runs a card's action: on the server (with undo), or in the interface (open, ask, add…). */
export function useRunAction() {
  const navigate = useNavigate()
  const agent = useAgent()
  const upload = useUpload()
  const panels = usePanels()
  const invalidate = useInvalidateAll()
  const [runningKey, setRunningKey] = useState<string | null>(null)
  const server = useMutation({
    mutationFn: api.act,
    onSuccess: (result) => {
      void invalidate()
      if (result.letter) panels.showLetter(result.letter)
    },
    onError: (e) => toast.error(e.message),
    onSettled: () => setRunningKey(null),
  })
  const run = (action: FeedAction) => {
    const p = action.params
    switch (action.type) {
      case "open":
        navigate(String(p.url))
        return
      case "agent":
        agent.open(String(p.prompt))
        return
      case "upload":
        upload.open()
        return
      case "report":
        panels.showReport(String(p.batch))
        return
      case "journey":
        panels.showJourney(Number(p.journey_id))
        return
      case "ask":
        panels.showQuestions(Array.isArray(p.document_ids) ? p.document_ids.map(Number) : [])
        return
      case "triage":
        panels.showQuestions()
        return
      case "pdf":
        window.location.assign(String(p.url))
        return
      case "link":
        openExternal(String(p.url))
        return
      default:
        setRunningKey(actionKey(action))
        server.mutate({ type: action.type, params: p })
    }
  }
  const isRunning = (action: FeedAction) => server.isPending && runningKey === actionKey(action)
  return { run, pending: server.isPending, isRunning }
}
