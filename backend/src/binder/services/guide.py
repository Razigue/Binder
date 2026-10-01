"""How to use Binder: the guide the agent reads to help the user with the app itself (mailbox
setup, phone scan, backups…), in the user's language.

Each topic names its words (normalized, French and English) so a question finds it without a
model; texts use the interface's own labels.
"""

import re

from binder import i18n
from binder.services.rules import normalize

# (topic, words that point to it)
TOPICS: list[tuple[str, tuple[str, ...]]] = [
    (
        "mailbox",
        (
            "mail", "e-mail", "email", "courriel", "boite mail", "imap", "gmail", "outlook",
            "hotmail", "yahoo", "icloud", "orange", "free", "sfr", "laposte", "mot de passe",
            "password", "piece jointe", "pieces jointes", "attachment", "serveur", "server",
        ),
    ),
    (
        "add",
        (
            "ajouter", "importer", "import", "glisser", "deposer", "add", "upload", "drag",
            "drop", "format", "pdf", "jpg", "png", "fichier", "file",
        ),
    ),
    (
        "phone",
        (
            "telephone", "phone", "mobile", "smartphone", "scan", "scanner", "qr", "photo",
            "wi-fi", "wifi", "connexion non privee", "not private",
        ),
    ),
    (
        "today",
        (
            "aujourd'hui", "today", "accueil", "home", "question", "semaine", "week",
            "notification", "alerte", "alert",
        ),
    ),
    (
        "areas",
        (
            "espace", "area", "logement", "argent", "travail", "sante", "identite", "vehicule",
            "housing", "money", "health", "identity", "vehicle", "corriger", "correct",
            "modifier", "edit", "mauvais", "wrong", "erreur", "mistake", "classe", "categorie",
        ),
    ),
    (
        "ask",
        (
            "demander", "ask", "agent", "assistant", "chat", "ctrl", "que peux-tu",
            "que sais-tu", "what can you", "aide", "help", "comment marche", "how does",
            "comment utiliser", "how to use", "fonctionne", "work",
        ),
    ),
    (
        "letters",
        ("lettre", "courrier", "letter", "resilier", "reclamation", "cancel", "complaint"),
    ),
    (
        "folders",
        ("dossier", "zip", "exporter", "export", "location", "rental", "caf", "pack"),
    ),
    (
        "undo",
        (
            "annuler", "undo", "historique", "history", "corbeille", "trash", "supprimer",
            "delete", "restaurer un document", "restore a document", "efface",
        ),
    ),
    (
        "backup",
        (
            "sauvegarde", "backup", "code de recuperation", "recovery code", "restaurer",
            "restore", "nouvel ordinateur", "new computer", "dossier de donnees", "data folder",
        ),
    ),
    (
        "privacy",
        (
            "internet", "confidential", "prive", "private", "privacy", "securite", "security",
            "chiffre", "encrypt", "donnees", "data", "ia", "ollama", "modele", "model",
            "mise a jour", "update", "cloud",
        ),
    ),
]  # fmt: skip

T = i18n.catalog(
    "guide",
    {
        "mailbox": {
            "en": "Mailbox (bottom of the menu): Binder imports the attachments of your new "
            "emails every 5 minutes, read only (nothing is moved, deleted or marked as read). "
            "Tick “Import attachments from my emails”, enter your email address and an app "
            "password, then Save; “Check now” tests it at once. IMAP is the standard way a "
            "program reads a mailbox: the server is filled in from your address (Advanced "
            "shows server, port, folder and how far back the first check goes). An app password "
            "is a separate password for one program, created in your email account's security "
            "settings. Gmail: turn on 2-Step Verification, then open "
            "myaccount.google.com/apppasswords, create one named “Binder” and paste the 16 "
            "letters (spaces do not matter). Yahoo: Account security, Generate app password. "
            "iCloud: account.apple.com, Sign-In and Security, App-Specific Passwords. Other "
            "providers often accept your usual password. The password stays encrypted on this "
            "computer.",
            "fr": "Boîte mail (en bas du menu) : Binder importe les pièces jointes de vos "
            "nouveaux e-mails toutes les 5 minutes, en lecture seule (rien n'est déplacé, "
            "supprimé ni marqué comme lu). Cochez « Importer les pièces jointes de mes "
            "e-mails », saisissez votre adresse et un mot de passe d'application, puis "
            "Enregistrer ; « Vérifier maintenant » teste tout de suite. L'IMAP est la façon "
            "standard dont un logiciel lit une boîte mail : le serveur est rempli d'après votre "
            "adresse (Avancé montre le serveur, le port, le dossier et jusqu'où remonte la "
            "première vérification). Un mot de passe d'application est un mot de passe à part, "
            "réservé à un logiciel, créé dans les réglages de sécurité de votre compte e-mail. "
            "Gmail : activez la validation en deux étapes, puis ouvrez "
            "myaccount.google.com/apppasswords, créez-en un nommé « Binder » et collez les 16 "
            "lettres (les espaces ne comptent pas). Yahoo : Sécurité du compte, Générer un mot "
            "de passe d'application. iCloud : account.apple.com, Connexion et sécurité, Mots de "
            "passe pour app. Les autres fournisseurs acceptent souvent votre mot de passe "
            "habituel. Il reste chiffré, sur cet ordinateur uniquement.",
        },
        "add": {
            "en": "Adding documents: drag and drop PDF, JPG or PNG files anywhere in the window, "
            "or use “Add documents”. You can also scan with your phone or import your email "
            "attachments. After each import, Binder says what it did: where each document "
            "went, what it asks of you and the questions it still has. Exact copies are "
            "ignored; an older version of a certificate is kept and marked as replaced.",
            "fr": "Ajouter des documents : glissez des fichiers PDF, JPG ou PNG n'importe où "
            "dans la fenêtre, ou cliquez sur « Ajouter des documents ». Vous pouvez aussi "
            "scanner avec votre téléphone ou importer les pièces jointes de vos e-mails. Après "
            "chaque import, Binder dit ce qu'il a fait : où va chaque document, ce qu'il vous "
            "demande et les questions qui restent. Les copies exactes sont ignorées ; "
            "l'ancienne version d'une attestation est gardée et marquée comme remplacée.",
        },
        "phone": {
            "en": "Scan with your phone: in the “Add documents” window, click “Scan with my "
            "phone”, connect the phone to the same Wi-Fi as this computer and scan the QR code "
            "with its camera. Each page is captured automatically when you hold still. The "
            "phone warns that the connection is not private: that is expected, the page comes "
            "from Binder on your own network; tap “Advanced”, then “Proceed” (once per phone).",
            "fr": "Scanner avec votre téléphone : dans la fenêtre « Ajouter des documents », "
            "cliquez sur « Scanner avec mon téléphone », connectez le téléphone au même Wi-Fi "
            "que cet ordinateur et scannez le QR code avec l'appareil photo. Chaque page est "
            "prise automatiquement dès que vous ne bougez plus. Le téléphone signale une "
            "connexion non privée : c'est normal, la page vient de Binder sur votre réseau ; "
            "touchez « Paramètres avancés » puis « Continuer » (une fois par téléphone).",
        },
        "today": {
            "en": "Today shows what needs you, most urgent first, with one-tap actions: "
            "payments due or late (“It's paid”), documents to renew, anomalies (billed twice, "
            "price rise, overpayment), missing documents, suggestions, and Binder's short "
            "questions when it is unsure about a document. Every Monday it sums up your week. "
            "While Binder is open, urgent deadlines and new documents also arrive as system "
            "notifications.",
            "fr": "Aujourd'hui montre ce qui vous attend, le plus urgent d'abord, avec des "
            "actions en un geste : paiements à venir ou en retard (« C'est payé »), papiers à "
            "renouveler, anomalies (facturé deux fois, hausse de prix, trop-perçu), documents "
            "manquants, suggestions, et les courtes questions de Binder quand il hésite sur un "
            "document. Chaque lundi, il résume votre semaine. Tant que Binder est ouvert, les "
            "échéances urgentes et les nouveaux documents arrivent aussi en notifications.",
        },
        "areas": {
            "en": "Areas (Housing, Money, Work & benefits, Health, Identity, Vehicle) show what "
            "to do, what is coming up, recurring bills with their yearly cost and documents by "
            "year, filtered by household member or by word. Open a document to see its "
            "preview; hovering a field highlights where Binder read it, and “In short” "
            "explains it plainly. Something wrong? Correct the field, then “Save and "
            "validate”: Binder applies the correction to the next documents from that sender. "
            "You can also ask me to correct it.",
            "fr": "Les espaces (Logement, Argent, Travail & aides, Santé, Identité, Véhicule) "
            "montrent ce qu'il y a à faire, ce qui arrive, les factures récurrentes avec leur "
            "coût annuel et les documents par année, filtrables par membre du foyer ou par "
            "mot. Ouvrez un document pour voir son aperçu ; survolez un champ pour voir où "
            "Binder l'a lu, et « En bref » l'explique simplement. Une erreur ? Corrigez le "
            "champ puis « Enregistrer et valider » : Binder appliquera la correction aux "
            "prochains documents du même expéditeur. Vous pouvez aussi me demander de la "
            "corriger.",
        },
        "ask": {
            "en": "Ask Binder: the bar at the bottom of every page (Ctrl K) or this panel. Ask "
            "in your own words: questions on your documents (“What is my reference tax "
            "income?”), follow-up (“Do I have papers to renew?”, “Is anything wrong or "
            "missing?”), actions (“Remind me to renew my ID card”, “I paid the income tax”), "
            "complete letters, application files with a ZIP, and help with the app itself. "
            "Each answer cites its documents: click a citation to open it. You can attach a "
            "document to the message with the paperclip.",
            "fr": "Demander à Binder : la barre en bas de chaque page (Ctrl K) ou ce panneau. "
            "Demandez avec vos mots : questions sur vos documents (« Quel est mon revenu "
            "fiscal de référence ? »), suivi (« Ai-je des papiers à renouveler ? », « Y a-t-il "
            "un problème ou un document manquant ? »), actions (« Rappelle-moi de renouveler "
            "ma carte d'identité », « J'ai payé mes impôts »), courriers complets, "
            "dossiers avec un ZIP, et aide sur l'app elle-même. Chaque réponse cite ses "
            "documents : cliquez sur une citation pour l'ouvrir. Le trombone joint un document "
            "au message.",
        },
        "letters": {
            "en": "Letters: ask for one in your words (“Write to EDF to pay the catch-up bill in "
            "three instalments”, “Dispute the CAF overpayment”). Binder writes it complete, "
            "with your details and the organisation's found in your documents; download the "
            "PDF, tell Binder you sent it, and it suggests a follow-up if no answer comes.",
            "fr": "Courriers : demandez-en un avec vos mots (« Écris à EDF pour payer la "
            "régularisation en trois fois », « Conteste le trop-perçu de la CAF »). Binder le "
            "rédige en entier, avec vos coordonnées et celles de l'organisme trouvées dans vos "
            "documents ; téléchargez le PDF, dites à Binder que vous l'avez envoyé, et il "
            "proposera une relance sans réponse.",
        },
        "folders": {
            "en": "Application files: ask “Prepare my rental application” or “the file for the "
            "nursery”. Binder lists what is ready, missing or too old, and gives a ZIP of the "
            "documents. You can also export all documents or one area as a ZIP.",
            "fr": "Dossiers : demandez « Prépare mon dossier de location » ou « le dossier pour "
            "la crèche ». Binder liste les pièces prêtes, manquantes ou trop anciennes, et "
            "donne un ZIP des documents. Vous pouvez aussi exporter tous les documents ou un "
            "espace en ZIP.",
        },
        "undo": {
            "en": "Undo: every action, yours or Binder's, can be undone right after with “Undo” "
            "on the message that confirms it, or by asking “undo that”. History (bottom of "
            "the menu) lists what happened; Trash keeps deleted documents, restorable until "
            "you delete them permanently. Binder never deletes anything silently.",
            "fr": "Annuler : chaque action, la vôtre ou celle de Binder, s'annule juste après "
            "avec « Annuler » sur le message qui la confirme, ou en demandant « annule ça ». "
            "L'Historique (en bas du menu) liste ce qui s'est passé ; la Corbeille garde les "
            "documents supprimés, restaurables tant que vous ne les supprimez pas "
            "définitivement. Binder ne supprime jamais rien en silence.",
        },
        "backup": {
            "en": "Backups: once a day, when something changed, Binder saves an encrypted copy "
            "of your library in Documents/Binder backups (the last 7 are kept). The first time, "
            "Today shows your recovery code: write it down and keep it away from the computer. "
            "On another computer, click “Restore a backup” on the welcome screen and type that "
            "code; without it nobody can open the backup.",
            "fr": "Sauvegardes : une fois par jour, si quelque chose a changé, Binder enregistre "
            "une copie chiffrée de vos documents dans Documents/Binder backups (les 7 "
            "dernières sont gardées). La première fois, Aujourd'hui affiche votre code de "
            "récupération : notez-le et gardez-le loin de l'ordinateur. Sur un autre "
            "ordinateur, cliquez sur « Restaurer une sauvegarde » à l'accueil et tapez ce "
            "code ; sans lui, personne ne peut ouvrir la sauvegarde.",
        },
        "privacy": {
            "en": "Privacy: everything stays on this computer. Documents and the database are "
            "encrypted and the AI runs locally (Ollama); nothing is sent to an online service. "
            "Internet is only used to check for updates (Binder updates itself at launch) and, "
            "the first time, to download the AI engine and its model.",
            "fr": "Confidentialité : tout reste sur cet ordinateur. Les documents et la base "
            "sont chiffrés et l'IA tourne en local (Ollama) ; rien n'est envoyé à un service en "
            "ligne. Internet ne sert qu'à vérifier les mises à jour (Binder se met à jour au "
            "lancement) et, la première fois, à télécharger le moteur d'IA et son modèle.",
        },
    },
)

NAMES = [name for name, _ in TOPICS]


def _hits(norm: str, words: tuple[str, ...]) -> int:
    # Long words match their forms ("scann" in "scanner"), short ones only themselves ("ia").
    return sum(
        1
        for w in words
        if re.search(rf"(?<!\w){re.escape(w)}" + ("" if len(w) > 4 else r"s?(?!\w)"), norm)
    )


def find(question: str, limit: int = 2) -> list[str]:
    """Topics matching a question or a topic name, best first."""
    norm = normalize(question)
    if norm.strip() in NAMES:
        return [norm.strip()]
    scored = [(_hits(norm, words), name) for name, words in TOPICS]
    ranked = sorted((s for s in scored if s[0]), key=lambda s: -s[0])
    return [name for _, name in ranked[:limit]]


def text(topic: str) -> str:
    return T.get(topic)
