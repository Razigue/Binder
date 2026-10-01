import { defineMessages } from "@/i18n/core"

// App shell: sidebar, mobile navigation, the ask bar.
export const layout = defineMessages({
  en: {
    navigation: "Navigation",
    "nav.today": "Today",
    "nav.ask": "Ask Binder",
    "nav.mail": "Mailbox",
    "nav.history": "History",
    "nav.trash": "Trash",
    askPlaceholder: "Ask Binder anything about your papers…",
    askShortcut: "Ctrl K",
  },
  fr: {
    navigation: "Navigation",
    "nav.today": "Aujourd'hui",
    "nav.ask": "Demander à Binder",
    "nav.mail": "Boîte mail",
    "nav.history": "Historique",
    "nav.trash": "Corbeille",
    askPlaceholder: "Demandez à Binder ce que vous voulez sur vos papiers…",
    askShortcut: "Ctrl K",
  },
})
