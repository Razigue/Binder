import { defineMessages } from "@/i18n/core"

export const expirations = defineMessages({
  en: {
    title: "Document validity",
    validUntil: "Valid until {date}",
    expired: "Expired",
    renew_one: "Renew · expires in {count} day",
    renew_other: "Renew · expires in {count} days",
    valid: "Valid · renew from {date}",
  },
  fr: {
    title: "Validité de vos documents",
    validUntil: "Valable jusqu'au {date}",
    expired: "Expiré",
    renew_one: "À renouveler · expire dans {count} j",
    renew_other: "À renouveler · expire dans {count} j",
    valid: "Valide · à renouveler dès le {date}",
  },
})
