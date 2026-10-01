import { defineMessages } from "@/i18n/core"

// Folder titles, pieces, hints and notes come from the backend, already translated.
export const folders = defineMessages({
  en: {
    title: "Folders",
    subtitle: "Gather the documents a procedure needs and see what's missing.",
    complete: "Folder complete",
    ready_one: "{count} of {total} documents ready",
    ready_other: "{count} of {total} documents ready",
    export: "Export the folder",
    optional: "optional",
    document: "Document {id}",
    "status.ok": "Ready",
    "status.partial": "Incomplete",
    "status.outdated": "Needs renewing",
    "status.missing": "Missing",
  },
  fr: {
    title: "Dossiers",
    subtitle: "Rassemblez les pièces d'une démarche et voyez ce qui manque.",
    complete: "Dossier complet",
    ready_one: "{count} pièce prête sur {total}",
    ready_other: "{count} pièces prêtes sur {total}",
    export: "Exporter le dossier",
    optional: "facultatif",
    document: "Document {id}",
    "status.ok": "Prêt",
    "status.partial": "Incomplet",
    "status.outdated": "À renouveler",
    "status.missing": "Manquant",
  },
})
