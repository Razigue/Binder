import { defineMessages } from "@/i18n/core"

// The question panel: one question per screen, the document next to it.
export const questions = defineMessages({
  en: {
    title: "I have a question",
    progress: "Question {current} of {total}",
    documentN: "Document {n} of {total}",
    skip: "Later",
    openDocument: "Open the document",
    loading: "Loading the questions…",
    doneTitle: "All in order ✓",
    doneHint: "I have filed everything. I’ll only ask again when the answer changes something.",
    close: "Close",
    readHere: "Highlighted: where I read it.",
  },
  fr: {
    title: "J’ai une question",
    progress: "Question {current} sur {total}",
    documentN: "Document {n} sur {total}",
    skip: "Plus tard",
    openDocument: "Ouvrir le document",
    loading: "Chargement des questions…",
    doneTitle: "Tout est en ordre ✓",
    doneHint: "J’ai tout rangé. Je ne reposerai de question que si la réponse change quelque chose.",
    close: "Fermer",
    readHere: "Surligné : là où je l’ai lu.",
  },
})
