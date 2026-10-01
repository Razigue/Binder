import { defineMessages } from "@/i18n/core"

// The Documents page: every document, searched by its content.
export const documents = defineMessages({
  en: {
    title: "Documents",
    subtitle: "Everything Binder has filed, searched by its content.",
    search: "Search a sender, a reference, a word in the document…",
    all: "All",
    count_one: "{count} document",
    count_other: "{count} documents",
    empty: "No documents yet.",
    emptyHint: "Drop a document anywhere: Binder reads it and files it in the right place.",
    noMatch: "No document matches.",
    askInstead: "Ask Binder: “{query}”",
  },
  fr: {
    title: "Documents",
    subtitle: "Tout ce que Binder a rangé, cherché jusque dans le contenu.",
    search: "Chercher un émetteur, une référence, un mot du document…",
    all: "Tous",
    count_one: "{count} document",
    count_other: "{count} documents",
    empty: "Aucun document pour l'instant.",
    emptyHint: "Déposez un document n'importe où : Binder le lit et le range au bon endroit.",
    noMatch: "Aucun document ne correspond.",
    askInstead: "Demander à Binder : « {query} »",
  },
})
