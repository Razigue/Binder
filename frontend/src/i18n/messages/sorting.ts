import { defineMessages } from "@/i18n/core"

export const sorting = defineMessages({
  en: {
    title: "Sorting",
    subtitle: "Documents you no longer have to keep. Binder never deletes anything without you.",
    trashSelected_one: "Move {count} document to the trash",
    trashSelected_other: "Move {count} documents to the trash",
    empty: "Nothing to sort: all your documents are still within their retention period.",
    select: "Select {title}",
    keep: "Keep",
    kept: "“{title}” will be kept",
    footnote:
      "Indicative retention periods for individuals, based on service-public.fr. A document moved to the trash can still be restored.",
    confirmTitle_one: "Move {count} document to the trash?",
    confirmTitle_other: "Move {count} documents to the trash?",
    confirmDescription: "You can restore them from the trash as long as you don't delete them permanently.",
    confirmLabel: "Move to trash",
    trashed_one: "{count} document moved to the trash",
    trashed_other: "{count} documents moved to the trash",
  },
  fr: {
    title: "Tri",
    subtitle: "Documents que vous n'êtes plus tenu de conserver. Binder ne supprime rien sans vous.",
    trashSelected_one: "Mettre {count} document à la corbeille",
    trashSelected_other: "Mettre {count} documents à la corbeille",
    empty: "Rien à trier : tous vos documents sont encore dans leur durée de conservation.",
    select: "Sélectionner {title}",
    keep: "Garder",
    kept: "« {title} » sera conservé",
    footnote:
      "Durées indicatives pour un particulier, d'après service-public.fr. Un document mis à la corbeille reste restaurable.",
    confirmTitle_one: "Mettre {count} document à la corbeille ?",
    confirmTitle_other: "Mettre {count} documents à la corbeille ?",
    confirmDescription: "Vous pourrez les restaurer depuis la corbeille tant que vous ne les supprimez pas définitivement.",
    confirmLabel: "Mettre à la corbeille",
    trashed_one: "{count} document mis à la corbeille",
    trashed_other: "{count} documents mis à la corbeille",
  },
})
