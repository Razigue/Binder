import { defineMessages } from "@/i18n/core"

export const search = defineMessages({
  en: {
    title: "Search",
    subtitle: "Across the text, titles, issuers and references of your documents.",
    placeholder: "e.g. property tax, EDF, tax number…",
    results_one: "{count} result",
    results_other: "{count} results",
    searching: "Searching…",
    askAgent: "Ask the agent",
    empty: "No document contains “{q}”.",
    hint: "Type a keyword. Search ignores accents and matches partial words.",
  },
  fr: {
    title: "Recherche",
    subtitle: "Dans le texte, les titres, émetteurs et références de vos documents.",
    placeholder: "Ex. taxe foncière, EDF, numéro fiscal…",
    results_one: "{count} résultat",
    results_other: "{count} résultats",
    searching: "Recherche…",
    askAgent: "Demander à l'agent",
    empty: "Aucun document ne contient « {q} ».",
    hint: "Tapez un mot-clé. La recherche ignore les accents et trouve les mots partiels.",
  },
})
