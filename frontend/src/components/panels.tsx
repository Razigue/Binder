import { useMemo, useState, type ReactNode } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { JourneyDialog } from "@/components/journey"
import { QuestionsDialog, type QuestionsRequest } from "@/components/questions"
import { useInvalidateAll } from "@/hooks/queries"
import { useT } from "@/i18n"
import { feed } from "@/i18n/messages/feed"
import { api, type Letter } from "@/lib/api"
import { PanelsContext, type Panels } from "./panels/context"
import { LetterView } from "./panels/LetterView"
import { ReportView } from "./panels/ReportView"

/** Letter, import report and journey, opened from anywhere (feed, agent, upload, Prepare). */
export function PanelsProvider({ children }: { children: ReactNode }) {
  const t = useT(feed)
  const [letter, setLetter] = useState<Letter | null>(null)
  const [batch, setBatch] = useState<string | null>(null)
  const [journeyId, setJourneyId] = useState<number | null>(null)
  const [asking, setAsking] = useState<QuestionsRequest | null>(null)
  // Setters only: the value never changes, pages using it do not render again.
  const panels = useMemo<Panels>(
    () => ({
      showLetter: setLetter,
      showReport: setBatch,
      showJourney: setJourneyId,
      showQuestions: (documentIds) => setAsking({ documentIds }),
    }),
    [],
  )
  const invalidate = useInvalidateAll()

  return (
    <PanelsContext value={panels}>
      {children}
      <QuestionsDialog request={asking} onClose={() => setAsking(null)} />
      <JourneyDialog id={journeyId} onClose={() => setJourneyId(null)} />
      <Dialog open={letter !== null} onOpenChange={(open) => !open && setLetter(null)}>
        <DialogContent className="flex h-[92vh] max-h-[92vh] flex-col gap-4 sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle className="text-lg">{letter && t("letterTitle", { recipient: letter.recipient })}</DialogTitle>
            <DialogDescription className="sr-only">{letter?.subject}</DialogDescription>
          </DialogHeader>
          {letter && <LetterView key={letter.id ?? letter.subject} letter={letter} onCancelled={() => setLetter(null)} />}
        </DialogContent>
      </Dialog>
      <Dialog
        open={batch !== null}
        onOpenChange={(open) => {
          if (open || batch === null) return
          void api.reportSeen(batch).finally(invalidate)
          setBatch(null)
        }}
      >
        <DialogContent className="max-h-[90vh] gap-4 overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg">{t("reportTitle")}</DialogTitle>
            <DialogDescription className="sr-only">{t("reportTitle")}</DialogDescription>
          </DialogHeader>
          {batch && <ReportView batch={batch} onNavigate={() => setBatch(null)} />}
        </DialogContent>
      </Dialog>
    </PanelsContext>
  )
}
