import { defineMessages } from "@/i18n/core"

export const documents = defineMessages({
  en: {
    title: "Documents",
    count_one: "{count} document in your Binder",
    count_other: "{count} documents in your Binder",
    "tab.all": "All",
    "tab.to_review": "To check",
    "tab.classified": "Filed",
    allCategories: "All categories",
    exportAll: "Export everything",
    exportCategory: "Export “{category}”",
    empty: "No documents match these filters.",
  },
  fr: {
    title: "Documents",
    count_one: "{count} document dans votre Binder",
    count_other: "{count} documents dans votre Binder",
    "tab.all": "Tous",
    "tab.to_review": "À vérifier",
    "tab.classified": "Classés",
    allCategories: "Toutes catégories",
    exportAll: "Exporter le dossier",
    exportCategory: "Exporter « {category} »",
    empty: "Aucun document ne correspond à ces filtres.",
  },
})
