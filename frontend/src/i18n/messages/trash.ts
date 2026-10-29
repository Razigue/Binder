import { defineMessages } from "@/i18n/core"

export const trash = defineMessages({
  en: {
    title: "Trash",
    subtitle: "Deleted documents and journeys stay here until you restore or permanently delete them.",
    empty: "No deleted documents.",
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
    subtitle: "Les documents et démarches supprimés restent ici jusqu’à leur restauration ou leur suppression définitive.",
    empty: "Aucun document supprimé.",
    deletedOn: "supprimé le {date}",
    restore: "Restaurer",
    restored: "« {title} » restauré",
    purge: "Supprimer définitivement",
    confirmTitle: "Supprimer définitivement ?",
    confirmDescription: "« {title} » et son fichier seront effacés de votre machine. Cette action est irréversible.",
    purged: "Document supprimé définitivement",
  },
})
