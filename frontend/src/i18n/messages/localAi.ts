import { defineMessages } from "@/i18n/core"

// The local AI model: the upgrade Binder offers when a better one suits the machine, and the
// Settings card that shows which model runs and which one the machine is suited for.
export const localAi = defineMessages({
  en: {
    "offer.title": "A better AI model suits this computer",
    "offer.text": "{label} reads your documents more accurately. Download: {size}. The current model keeps working meanwhile, then is removed to free the space.",
    "offer.accept": "Download",
    "offer.decline": "No thanks",
    "offer.downloading": "Improving your local AI: {label}…",
    "offer.switch": "Your current AI keeps working. Binder switches as soon as the new one is ready and removes the former one.",
    "offer.stop": "Stop",
    "offer.progress": "{done} of {total}",
    "offer.failed": "Download failed: {error}",
    "offer.retry": "Try again",
    "offer.declined": "Binder will improve it again only if a better model suits this computer.",

    "card.title": "Local AI",
    "card.description": "The model that reads your documents runs on this computer. Binder picks the best one it runs, and checks again at each launch.",
    "card.active": "Model in use",
    "card.recommended": "Best suited to this computer",
    "card.automatic": "Chosen by Binder: when a better model suits this computer, Binder offers it.",
    "card.manual": "Chosen by you: Binder does not change it.",
    "card.notInstalled": "Not installed yet",
    "card.disabled": "The local AI is turned off on this computer.",
  },
  fr: {
    "offer.title": "Un meilleur modèle d'IA convient à cet ordinateur",
    "offer.text": "{label} lit vos documents plus précisément. Téléchargement : {size}. Le modèle actuel continue de fonctionner en attendant, puis est supprimé pour libérer la place.",
    "offer.accept": "Télécharger",
    "offer.decline": "Non merci",
    "offer.downloading": "Amélioration de votre IA locale : {label}…",
    "offer.switch": "Votre IA actuelle continue de fonctionner. Binder passe au nouveau modèle dès qu'il est prêt et supprime l'ancien.",
    "offer.stop": "Arrêter",
    "offer.progress": "{done} sur {total}",
    "offer.failed": "Échec du téléchargement : {error}",
    "offer.retry": "Réessayer",
    "offer.declined": "Binder ne l'améliorera à nouveau que si un meilleur modèle convient à cet ordinateur.",

    "card.title": "IA locale",
    "card.description": "Le modèle qui lit vos documents tourne sur cet ordinateur. Binder choisit le meilleur qu'il fait tourner, et revérifie à chaque lancement.",
    "card.active": "Modèle utilisé",
    "card.recommended": "Le mieux adapté à cet ordinateur",
    "card.automatic": "Choisi par Binder : quand un meilleur modèle convient à cet ordinateur, Binder le propose.",
    "card.manual": "Choisi par vous : Binder n'y touche pas.",
    "card.notInstalled": "Pas encore installé",
    "card.disabled": "L'IA locale est désactivée sur cet ordinateur.",
  },
})
