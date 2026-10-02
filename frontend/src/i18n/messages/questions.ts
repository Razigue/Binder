import { defineMessages } from "@/i18n/core"

// The question panel: one question per screen, the document next to it.
export const questions = defineMessages({
  en: {
    title: "Binder has a question",
    progress: "Question {current} of {total}",
    skip: "Later",
    openDocument: "Open the document",
    loading: "Loading the questions…",
    doneTitle: "All in order ✓",
    doneHint: "Binder has filed everything. It will only ask again when the answer changes something.",
    close: "Close",
    readHere: "Highlighted: where Binder read it.",
  },
  fr: {
    title: "Binder a une question",
    progress: "Question {current} sur {total}",
    skip: "Plus tard",
    openDocument: "Ouvrir le document",
    loading: "Chargement des questions…",
    doneTitle: "Tout est en ordre ✓",
    doneHint: "Binder a tout rangé. Il ne reposera de question que si la réponse change quelque chose.",
    close: "Fermer",
    readHere: "Surligné : là où Binder l'a lu.",
  },
})
