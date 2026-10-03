import { defineMessages } from "@/i18n/core"

export const phoneScan = defineMessages({
  en: {
    title: "Scan with your phone",
    description: "Scan the QR code with your phone to photograph your documents page by page.",
    opening: "Opening the scanner…",
    qrAlt: "QR code: scan it with your phone to open the scanner",
    stepWifi: "Connect your phone to the same Wi-Fi as this computer.",
    stepScan: "Scan this QR code with the phone's camera.",
    stepWarning:
      "The phone warns that the connection is not private: that's expected. The page comes from Binder on your network and the connection stays encrypted. Tap “Advanced”, then “Proceed”.",
    stepShoot: "Frame each page: it is taken automatically when you hold still.",
    waiting: "Waiting for the phone…",
    connected: "Phone connected",
    document: "Document {n}",
    pages_one: "{count} page",
    pages_other: "{count} pages",
    noOutline: "Outline not found: whole photo kept",
    deletePage: "Delete page {n}",
    unreachableTitle: "Is the page loading endlessly on the phone?",
    unreachable:
      "Check that the phone is on the same Wi-Fi as this computer, then that this computer's firewall lets Binder receive connections from the local network.",
    unreachableWindows:
      "Check that the phone is on the same Wi-Fi as this computer. Otherwise the Windows firewall is blocking it: Windows Security › Firewall & network protection › Allow an app through firewall, then tick “Private” for Binder (or Python).",
    cancel: "Cancel",
    import_one: "Import {count} document",
    import_other: "Import {count} documents",
    importEmpty: "Import",
    retry: "Try again",
  },
  fr: {
    title: "Scanner avec votre téléphone",
    description: "Scannez le QR code avec votre téléphone pour photographier vos documents page par page.",
    opening: "Ouverture du scanner…",
    qrAlt: "QR code : scannez-le avec votre téléphone pour ouvrir le scanner",
    stepWifi: "Connectez le téléphone au même Wi-Fi que cet ordinateur.",
    stepScan: "Scannez ce QR code avec l'appareil photo du téléphone.",
    stepWarning:
      "Le téléphone signale une connexion non privée : c'est normal. La page vient de Binder sur votre réseau et la connexion reste chiffrée. Touchez « Paramètres avancés » puis « Continuer ».",
    stepShoot: "Cadrez chaque page : la prise est automatique dès que vous ne bougez plus.",
    waiting: "En attente du téléphone…",
    connected: "Téléphone connecté",
    document: "Document {n}",
    pages_one: "{count} page",
    pages_other: "{count} pages",
    noOutline: "Bords non trouvés : photo gardée entière",
    deletePage: "Supprimer la page {n}",
    unreachableTitle: "La page charge sans fin sur le téléphone ?",
    unreachable:
      "Vérifiez que le téléphone est sur le même Wi-Fi que cet ordinateur, puis que le pare-feu de l'ordinateur laisse Binder recevoir les connexions du réseau local.",
    unreachableWindows:
      "Vérifiez que le téléphone est sur le même Wi-Fi que cet ordinateur. Sinon, c'est le pare-feu Windows qui bloque : Sécurité Windows › Pare-feu et protection du réseau › Autoriser une application via le pare-feu, puis cochez « Privé » pour Binder (ou Python).",
    cancel: "Annuler",
    import_one: "Importer {count} document",
    import_other: "Importer {count} documents",
    importEmpty: "Importer",
    retry: "Réessayer",
  },
})
