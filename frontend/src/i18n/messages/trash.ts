import { defineMessages } from "@/i18n/core"

export const trash = defineMessages({
  en: {
    title: "Trash",
    subtitle: "Deleted documents stay here, restorable, until you erase them for good.",
    empty: "The trash is empty.",
    deletedOn: "deleted on {date}",
    restore: "Restore",
    restored: "“{title}” restored",
    purge: "Delete permanently",
    confirmTitle: "Delete permanently?",
    confirmDescription: "“{title}” and its file will be erased from your computer. This cannot be undone.",
    purged: "Document permanently deleted",
  },
  fr: {
    title: "Corbeille",
    subtitle: "Les documents supprimés restent ici, restaurables, tant que vous ne les effacez pas définitivement.",
    empty: "La corbeille est vide.",
    deletedOn: "supprimé le {date}",
    restore: "Restaurer",
    restored: "« {title} » restauré",
    purge: "Supprimer définitivement",
    confirmTitle: "Supprimer définitivement ?",
    confirmDescription: "« {title} » et son fichier seront effacés de votre machine. Cette action est irréversible.",
    purged: "Document supprimé définitivement",
  },
})
