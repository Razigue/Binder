import { defineMessages } from "@/i18n/core"

// The deadline timeline on Today and on each life area.
export const timeline = defineMessages({
  en: {
    today: "Today",
    more: "+{count}",
    done: "Done",
    moreLabel_one: "{count} more deadline",
    moreLabel_other: "{count} more deadlines",
    label: "Deadlines from {start} to {end}",
  },
  fr: {
    today: "Aujourd'hui",
    more: "+{count}",
    done: "Réglée",
    moreLabel_one: "{count} autre échéance",
    moreLabel_other: "{count} autres échéances",
    label: "Échéances du {start} au {end}",
  },
})
