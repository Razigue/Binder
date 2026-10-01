"""Life events followed step by step: moving, a birth, a death in the family, the tax return.

A journey is the checklist of an event, built from its date and from the user's own documents:
the organisations to tell about a move are the ones that send them bills, the tax return lists
the receipts that lower the tax with their total, the contracts of a deceased relative are the
documents that name them. Each step says what to do and by when, and offers the action that
does it in one tap (a complete letter, a file, a document). Steps are computed again on every
read: a step is done when the user ticks it, or on its own when the proof is there (the letter
was sent, the document arrived). Only the date, what the user told Binder and the ticked steps
are stored (`Journey`).

Time limits and amounts are those of France (service-public.fr, impots.gouv.fr): each step
names the official place to check them.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlmodel import Session, col, select

from binder import i18n
from binder.models import Category, Correspondence, DocType, Document, Journey
from binder.services import activity, folders, household, letters, undo
from binder.services.rules import normalize

T = i18n.catalog(
    "journeys",
    {
        # Kinds.
        "moving_title": {"en": "Moving house", "fr": "Déménagement"},
        "moving_description": {
            "en": "Notice to the landlord, contracts to transfer, everyone to tell: Binder lists "
            "the organisations found in your documents and writes the letters.",
            "fr": "Congé au propriétaire, contrats à transférer, organismes à prévenir : Binder "
            "liste ceux trouvés dans vos documents et rédige les courriers.",
        },
        "moving_event": {"en": "Moving day", "fr": "Date du déménagement"},
        "birth_title": {"en": "A birth", "fr": "Naissance"},
        "birth_description": {
            "en": "Town hall, health insurance, CAF, employer, taxes: every step of a birth, "
            "with its time limit.",
            "fr": "Mairie, Assurance Maladie, CAF, employeur, impôts : chaque démarche d'une "
            "naissance, avec son délai.",
        },
        "birth_event": {
            "en": "Birth date (or expected date)",
            "fr": "Date de naissance (ou prévue)",
        },
        "death_title": {"en": "Death of a relative", "fr": "Décès d'un proche"},
        "death_description": {
            "en": "The steps of the first days and months, and the contracts of your relative "
            "found in your documents.",
            "fr": "Les démarches des premiers jours et des mois suivants, et les contrats de "
            "votre proche trouvés dans vos documents.",
        },
        "death_event": {"en": "Date of death", "fr": "Date du décès"},
        "tax_return_title": {"en": "Income tax return", "fr": "Déclaration de revenus"},
        "tax_return_description": {
            "en": "What to check and declare, with the receipts found in your documents and "
            "their total.",
            "fr": "Ce qu'il faut vérifier et déclarer, avec les justificatifs trouvés dans vos "
            "documents et leur total.",
        },
        "tax_return_event": {
            "en": "Deadline for your département",
            "fr": "Date limite de votre département",
        },
        "field_new_address": {"en": "New address", "fr": "Nouvelle adresse"},
        "field_child": {"en": "Child's first name", "fr": "Prénom de l'enfant"},
        "field_person": {"en": "Name of your relative", "fr": "Nom de votre proche"},
        "titled": {"en": "{title}: {name}", "fr": "{title} : {name}"},
        "started": {"en": "Journey started: {title}", "fr": "Démarche commencée : {title}"},
        "step_done": {"en": "{title}: “{step}” done", "fr": "{title} : « {step} » fait"},
        "step_undone": {
            "en": "{title}: “{step}” to do again",
            "fr": "{title} : « {step} » à refaire",
        },
        "closed": {"en": "Journey closed: {title}", "fr": "Démarche terminée : {title}"},
        "reopened": {"en": "Journey reopened: {title}", "fr": "Démarche rouverte : {title}"},
        # Actions.
        "write_letter": {"en": "Write the letter", "fr": "Rédiger le courrier"},
        "prepare_folder": {"en": "Prepare the file", "fr": "Préparer le dossier"},
        "open_document": {"en": "See the document", "fr": "Voir le document"},
        "letter_sent": {
            "en": "Letter sent on {date:date}.",
            "fr": "Courrier envoyé le {date:date}.",
        },
        "letter_drafted": {
            "en": "Letter drafted: mark it as sent once posted.",
            "fr": "Courrier rédigé : marquez-le comme envoyé une fois posté.",
        },
        # Moving.
        "notice_title": {
            "en": "Give notice to your landlord",
            "fr": "Donner congé au propriétaire",
        },
        "notice_detail": {
            "en": "Three months' notice, one month in high-demand areas, for a furnished flat or "
            "for some reasons (new job, job loss…). By registered letter with acknowledgement "
            "of receipt.",
            "fr": "Préavis de 3 mois, ramené à 1 mois en zone tendue, en meublé ou pour certains "
            "motifs (mutation, perte d'emploi…). Par lettre recommandée avec accusé de "
            "réception.",
        },
        "notice_purpose": {
            "en": "Give notice to end my tenancy, leaving on {date:date}, with the legal notice "
            "period",
            "fr": "Donner congé du logement que je loue, pour un départ le {date:date}, en "
            "respectant le préavis légal",
        },
        "inventory_title": {"en": "Check-out inventory", "fr": "État des lieux de sortie"},
        "inventory_detail": {
            "en": "Compare it with the check-in inventory and take photos: it decides what is "
            "kept from your deposit.",
            "fr": "Comparez-le à l'état des lieux d'entrée et prenez des photos : il décide de ce "
            "qui sera retenu sur le dépôt de garantie.",
        },
        "deposit_title": {"en": "Get your deposit back", "fr": "Récupérer le dépôt de garantie"},
        "deposit_detail": {
            "en": "Due within one month of handing back the keys, two if the inventories differ. "
            "Past that, Binder writes the formal notice.",
            "fr": "À rendre dans le mois qui suit la remise des clés, deux mois si les états des "
            "lieux diffèrent. Au-delà, Binder rédige la mise en demeure.",
        },
        "deposit_purpose": {
            "en": "Return of my rental deposit",
            "fr": "Restitution de mon dépôt de garantie",
        },
        "transfer_title": {
            "en": "Transfer or end: {issuer}",
            "fr": "Transférer ou résilier : {issuer}",
        },
        "transfer_detail": {
            "en": "The contract goes with the home: move it to the new address or end it on "
            "moving day, and read the meter that day.",
            "fr": "Le contrat suit le logement : transférez-le à la nouvelle adresse ou "
            "résiliez-le au jour du départ, et relevez le compteur ce jour-là.",
        },
        "home_insurance_title": {
            "en": "Insure the new home: {issuer}",
            "fr": "Assurer le nouveau logement : {issuer}",
        },
        "home_insurance_detail": {
            "en": "The new home must be insured from the day you get the keys. Moving lets you "
            "end the current contract if you prefer another insurer.",
            "fr": "Le nouveau logement doit être assuré dès la remise des clés. Le déménagement "
            "permet aussi de résilier le contrat actuel si vous changez d'assureur.",
        },
        "tell_title": {"en": "New address for {issuer}", "fr": "Nouvelle adresse pour {issuer}"},
        "tell_detail": {
            "en": "So that its mail and statements reach you.",
            "fr": "Pour que ses courriers et relevés vous parviennent.",
        },
        "public_title": {
            "en": "Declare the new address online",
            "fr": "Déclarer la nouvelle adresse en ligne",
        },
        "public_detail": {
            "en": "One form on service-public.fr (change of details) informs the tax office, "
            "health insurance, CAF, France Travail and pension funds at once.",
            "fr": "Un seul formulaire sur service-public.fr (changement de coordonnées) prévient "
            "à la fois les impôts, l'Assurance Maladie, la CAF, France Travail et les caisses de "
            "retraite.",
        },
        "public_found": {
            "en": "Yours, from your documents: {names}.",
            "fr": "Les vôtres, d'après vos documents : {names}.",
        },
        "mail_title": {"en": "Have your mail forwarded", "fr": "Faire suivre votre courrier"},
        "mail_detail": {
            "en": "La Poste's forwarding service, taken out a few days before leaving: letters "
            "follow you for 6 or 12 months.",
            "fr": "Le contrat de réexpédition de La Poste, à souscrire quelques jours avant le "
            "départ : vos lettres vous suivent 6 ou 12 mois.",
        },
        "vehicle_title": {
            "en": "Change the address on the registration",
            "fr": "Changer l'adresse de la carte grise",
        },
        "vehicle_detail": {
            "en": "Compulsory within a month, free on ants.gouv.fr.",
            "fr": "Obligatoire dans le mois, gratuit sur ants.gouv.fr.",
        },
        "school_title": {
            "en": "Enrol the children in their new school",
            "fr": "Inscrire les enfants dans leur nouvelle école",
        },
        "school_detail": {
            "en": "At the town hall of the new town, then at the school: Binder gathers the "
            "documents.",
            "fr": "À la mairie de la nouvelle commune, puis à l'école : Binder rassemble les "
            "pièces.",
        },
        "electoral_title": {
            "en": "Register to vote in the new town",
            "fr": "S'inscrire sur les listes électorales",
        },
        "electoral_detail": {
            "en": "Online on service-public.fr, up to the sixth Friday before an election.",
            "fr": "En ligne sur service-public.fr, jusqu'au sixième vendredi avant un scrutin.",
        },
        # Birth.
        "childcare_title": {"en": "Look for childcare", "fr": "Chercher un mode de garde"},
        "childcare_detail": {
            "en": "Nursery places are scarce: ask the town hall early, and see monenfant.fr for "
            "nurseries and childminders.",
            "fr": "Les places en crèche sont rares : renseignez-vous tôt à la mairie, et sur "
            "monenfant.fr pour les crèches et assistantes maternelles.",
        },
        "leave_title": {
            "en": "Tell your employer about your leave",
            "fr": "Prévenir l'employeur du congé",
        },
        "leave_detail": {
            "en": "Paternity and childcare leave: 25 days (32 for multiple births), 4 of them "
            "right after the birth; tell the employer at least a month before.",
            "fr": "Congé de paternité et d'accueil de l'enfant : 25 jours (32 pour des naissances "
            "multiples), dont 4 juste après la naissance ; prévenez l'employeur au moins un mois "
            "avant.",
        },
        "leave_purpose": {
            "en": "Inform my employer of my birth leave, the birth being expected on {date:date}",
            "fr": "Informer mon employeur de mon congé de naissance, la naissance étant prévue le "
            "{date:date}",
        },
        "declare_birth_title": {"en": "Register the birth", "fr": "Déclarer la naissance"},
        "declare_birth_detail": {
            "en": "Within 5 days, at the town hall of the place of birth (often possible at the "
            "maternity ward). Bring your identity documents and the family record book if you "
            "have one.",
            "fr": "Dans les 5 jours, à la mairie du lieu de naissance (souvent possible à la "
            "maternité). Apportez vos pièces d'identité et le livret de famille si vous en avez "
            "un.",
        },
        "birth_record_title": {
            "en": "Add the birth certificate to Binder",
            "fr": "Ajouter l'acte de naissance à Binder",
        },
        "birth_record_detail": {
            "en": "Every organisation will ask for it: Binder keeps it with the family papers.",
            "fr": "Chaque organisme le demandera : Binder le range avec les papiers de famille.",
        },
        "health_child_title": {
            "en": "Add the child to your health insurance",
            "fr": "Rattacher l'enfant à l'Assurance Maladie",
        },
        "health_child_detail": {
            "en": "On ameli.fr or at your office, with the birth certificate: the child can be "
            "linked to both parents.",
            "fr": "Sur ameli.fr ou auprès de votre caisse, avec l'acte de naissance : l'enfant "
            "peut être rattaché à ses deux parents.",
        },
        "mutual_title": {"en": "Add the child to {issuer}", "fr": "Ajouter l'enfant chez {issuer}"},
        "mutual_detail": {
            "en": "Your supplementary health cover: the child is covered from the birth if you "
            "tell it quickly.",
            "fr": "Votre complémentaire santé : l'enfant est couvert dès la naissance si vous la "
            "prévenez rapidement.",
        },
        "mutual_purpose": {
            "en": "Add my child, born on {date:date}, as a beneficiary of my health cover",
            "fr": "Ajouter mon enfant, né le {date:date}, comme bénéficiaire de ma complémentaire "
            "santé",
        },
        "caf_birth_title": {
            "en": "Tell the CAF about the birth",
            "fr": "Déclarer la naissance à la CAF",
        },
        "caf_birth_detail": {
            "en": "In your CAF account, with the birth certificate: early childhood benefits "
            "(PAJE) and family allowances if you are entitled. The birth grant is claimed "
            "during pregnancy.",
            "fr": "Dans votre espace Mon Compte, avec l'acte de naissance : prestations de la "
            "PAJE et allocations familiales si vous y avez droit. La prime à la naissance se "
            "demande pendant la grossesse.",
        },
        "tax_birth_title": {"en": "Tell the tax office", "fr": "Signaler la naissance aux impôts"},
        "tax_birth_detail": {
            "en": "In your impots.gouv.fr account (manage my withholding tax) within 60 days, "
            "to lower your rate straight away.",
            "fr": "Dans votre espace impots.gouv.fr (« Gérer mon prélèvement à la source ») dans "
            "les 60 jours, pour baisser votre taux tout de suite.",
        },
        # Death.
        "declare_death_title": {"en": "Register the death", "fr": "Déclarer le décès"},
        "declare_death_detail": {
            "en": "Within 24 hours, at the town hall of the place of death; the funeral director "
            "often does it.",
            "fr": "Dans les 24 heures, à la mairie du lieu du décès ; les pompes funèbres s'en "
            "chargent souvent.",
        },
        "death_copies_title": {
            "en": "Get several copies of the death certificate",
            "fr": "Obtenir plusieurs copies de l'acte de décès",
        },
        "death_copies_detail": {
            "en": "Every organisation asks for one. Free at the town hall or on "
            "service-public.fr; add one to Binder.",
            "fr": "Chaque organisme en demande une. Gratuites à la mairie ou sur "
            "service-public.fr ; ajoutez-en une à Binder.",
        },
        "pension_title": {
            "en": "Tell the employer or pension funds",
            "fr": "Prévenir l'employeur ou les caisses de retraite",
        },
        "pension_detail": {
            "en": "Pensions stop at the death; a survivor's pension may be claimed by the spouse.",
            "fr": "Les pensions s'arrêtent au décès ; le conjoint peut demander une pension de "
            "réversion.",
        },
        "bank_title": {"en": "Tell the bank: {issuer}", "fr": "Prévenir la banque : {issuer}"},
        "bank_detail": {
            "en": "Personal accounts are frozen, joint accounts are not; funeral costs can be "
            "paid from the deceased's account up to a limit. Enclose a death certificate.",
            "fr": "Les comptes personnels sont bloqués, pas les comptes joints ; les frais "
            "d'obsèques peuvent être prélevés sur le compte du défunt dans une certaine limite. "
            "Joignez un acte de décès.",
        },
        "banks_title": {"en": "Tell the deceased's banks", "fr": "Prévenir les banques du défunt"},
        "bank_purpose": {
            "en": "Inform the bank of the death of {person} on {date:date} and ask what is "
            "needed for their accounts",
            "fr": "Informer la banque du décès de {person} survenu le {date:date} et demander "
            "les démarches pour ses comptes",
        },
        "contract_title": {
            "en": "End or transfer: {issuer}",
            "fr": "Clôturer ou transférer : {issuer}",
        },
        "contract_detail": {
            "en": "Contracts in the deceased's name: end them from the date of death, or have "
            "them transferred to whoever keeps the home.",
            "fr": "Contrats au nom du défunt : à clôturer à la date du décès, ou à transférer à "
            "qui garde le logement.",
        },
        "contract_purpose": {
            "en": "Close the contract of {person}, who died on {date:date}, from that date; a "
            "copy of the death certificate is enclosed",
            "fr": "Clôturer le contrat de {person}, décédé(e) le {date:date}, à compter de cette "
            "date ; copie de l'acte de décès jointe",
        },
        "contracts_title": {
            "en": "End the deceased's contracts",
            "fr": "Clôturer les contrats du défunt",
        },
        "contracts_detail": {
            "en": "Energy, phone, insurance, subscriptions. Give your relative's name: Binder "
            "will find their contracts in your documents.",
            "fr": "Énergie, téléphone, assurances, abonnements. Indiquez le nom de votre "
            "proche : Binder retrouvera ses contrats dans vos documents.",
        },
        "health_death_title": {
            "en": "Tell the health insurance",
            "fr": "Prévenir l'Assurance Maladie",
        },
        "health_death_detail": {
            "en": "A death grant may be paid to the relatives of an employee or of a person on "
            "unemployment benefit: claim it from their office.",
            "fr": "Un capital décès peut être versé aux proches d'un salarié ou d'un demandeur "
            "d'emploi indemnisé : il se demande à sa caisse.",
        },
        "caf_death_title": {"en": "Tell the CAF", "fr": "Prévenir la CAF"},
        "caf_death_detail": {
            "en": "Benefits are recalculated; some are paid to the surviving parent.",
            "fr": "Les prestations sont recalculées ; certaines sont versées au parent survivant.",
        },
        "life_insurance_title": {
            "en": "Look for life insurance contracts",
            "fr": "Rechercher les contrats d'assurance vie",
        },
        "life_insurance_detail": {
            "en": "If you may be a beneficiary, ask AGIRA (agira.asso.fr): free.",
            "fr": "Si vous pensez être bénéficiaire, interrogez l'AGIRA (agira.asso.fr) : c'est "
            "gratuit.",
        },
        "notary_title": {"en": "Contact a notary", "fr": "Contacter un notaire"},
        "notary_detail": {
            "en": "Required for property, a will or a gift; for a small estate, a certificate "
            "signed by the heirs may be enough.",
            "fr": "Indispensable s'il y a un bien immobilier, un testament ou une donation ; pour "
            "une petite succession, une attestation signée par les héritiers peut suffire.",
        },
        "estate_title": {
            "en": "File the estate declaration",
            "fr": "Déposer la déclaration de succession",
        },
        "estate_detail": {
            "en": "Within 6 months (12 if the death occurred abroad), with the tax office; the "
            "notary often does it. Not needed for a spouse or children below 50,000 € with no "
            "earlier gift.",
            "fr": "Dans les 6 mois (12 si le décès a eu lieu à l'étranger), auprès des impôts ; "
            "le notaire s'en charge souvent. Inutile pour le conjoint ou les enfants sous "
            "50 000 € sans donation antérieure.",
        },
        "last_return_title": {
            "en": "Declare the deceased's last income",
            "fr": "Déclarer les derniers revenus du défunt",
        },
        "last_return_detail": {
            "en": "The following spring, for 1 January to the date of death.",
            "fr": "Au printemps suivant, pour la période du 1er janvier au décès.",
        },
        "lease_death_title": {
            "en": "End or transfer the lease",
            "fr": "Mettre fin au bail ou le transférer",
        },
        "lease_death_detail": {
            "en": "The lease ends at the tenant's death, unless it passes to the spouse, civil "
            "partner or a relative who lived there.",
            "fr": "Le bail prend fin au décès du locataire, sauf transfert au conjoint, au "
            "partenaire de PACS ou à un proche qui vivait avec lui.",
        },
        # Tax return.
        "salaries_title": {
            "en": "Check the pre-filled salaries",
            "fr": "Vérifier les salaires préremplis",
        },
        "salaries_detail": {
            "en": "Compare them with the cumulative taxable pay on the December {year} payslip.",
            "fr": "Comparez-les au cumul « net imposable » du bulletin de décembre {year}.",
        },
        "investments_title": {
            "en": "Check investment income (IFU)",
            "fr": "Vérifier les revenus de placements (IFU)",
        },
        "investments_detail": {
            "en": "Pre-filled from your banks' statements: {names}.",
            "fr": "Préremplis d'après les imprimés fiscaux de vos banques : {names}.",
        },
        "investments_missing": {
            "en": "Your banks send it in February or March: add it when it comes.",
            "fr": "Vos banques l'envoient en février ou mars : ajoutez-le à son arrivée.",
        },
        "donations_title": {"en": "Donations: {amount:money}", "fr": "Dons : {amount:money}"},
        "donations_detail": {
            "en": "Box 7UF: 66% tax reduction, about {reduction:money}. Gifts to charities "
            "helping people in difficulty (meals, housing, care) go in box 7UD, at 75% up to a "
            "ceiling.",
            "fr": "Case 7UF : réduction de 66 %, soit environ {reduction:money}. Les dons aux "
            "associations d'aide aux personnes en difficulté (repas, logement, soins) vont case "
            "7UD, à 75 % dans la limite d'un plafond.",
        },
        "donations_none_title": {"en": "Donations", "fr": "Dons aux associations"},
        "donations_none_detail": {
            "en": "No {year} donation receipt found: if you gave, add the receipts.",
            "fr": "Aucun reçu de don de {year} trouvé : si vous avez donné, ajoutez les reçus.",
        },
        "childcare_tax_title": {
            "en": "Childcare costs: {amount:money}",
            "fr": "Frais de garde : {amount:money}",
        },
        "childcare_tax_detail": {
            "en": "Children under 6 on 1 January {year}: boxes 7GA to 7GC, one per child. Tax "
            "credit of 50% of the costs minus CAF support, up to 3,500 € of costs per child.",
            "fr": "Enfants de moins de 6 ans au 1er janvier {year} : cases 7GA à 7GC, une par "
            "enfant. Crédit d'impôt de 50 % des frais, aides de la CAF déduites, dans la limite "
            "de 3 500 € de frais par enfant.",
        },
        "childcare_tax_none_title": {"en": "Childcare costs", "fr": "Frais de garde"},
        "childcare_tax_none_detail": {
            "en": "No {year} childcare certificate found: nurseries and childminders' "
            "employers' centre (Pajemploi) provide one.",
            "fr": "Aucune attestation de frais de garde de {year} trouvée : la crèche ou "
            "Pajemploi la fournissent.",
        },
        "other_title": {"en": "Other deductions", "fr": "Autres réductions et charges"},
        "other_detail": {
            "en": "Home help employee (7DB), maintenance paid, actual work expenses instead of "
            "the 10% allowance (1AK), payments into a retirement savings plan.",
            "fr": "Salarié à domicile (7DB), pension alimentaire versée, frais réels au lieu de "
            "l'abattement de 10 % (1AK), versements sur un plan d'épargne retraite.",
        },
        "changes_title": {"en": "Changes in {year}", "fr": "Changements de {year}"},
        "change_birth": {
            "en": "a birth ({date:date}): one more half share",
            "fr": "une naissance ({date:date}) : une demi-part de plus",
        },
        "change_moving": {
            "en": "a move ({date:date}): give the new address",
            "fr": "un déménagement ({date:date}) : indiquez la nouvelle adresse",
        },
        "change_death": {
            "en": "a death ({date:date}): a separate return for the deceased",
            "fr": "un décès ({date:date}) : une déclaration distincte pour le défunt",
        },
        "file_title": {"en": "File the return online", "fr": "Déclarer en ligne"},
        "file_detail": {
            "en": "On impots.gouv.fr before your département's deadline (late May or early June: "
            "check it on the site).",
            "fr": "Sur impots.gouv.fr avant la date limite de votre département (fin mai ou "
            "début juin : vérifiez-la sur le site).",
        },
        "tax_notice_title": {"en": "File the tax notice", "fr": "Ranger l'avis d'impôt"},
        "tax_notice_detail": {
            "en": "It arrives in your account during the summer: add it and Binder follows the "
            "payment or the refund.",
            "fr": "Il arrive dans votre espace pendant l'été : ajoutez-le et Binder suivra le "
            "paiement ou le remboursement.",
        },
        "list_separator": {"en": ", ", "fr": ", "},
        "sentence_separator": {"en": "; ", "fr": " ; "},
        "unknown_kind": {"en": "Unknown journey", "fr": "Démarche inconnue"},
        "unknown_step": {"en": "Unknown step", "fr": "Étape inconnue"},
    },
)

KINDS: tuple[str, ...] = ("moving", "birth", "death", "tax_return")
# What the user can tell Binder when starting a journey (keys of `details`).
FIELDS: dict[str, list[str]] = {
    "moving": ["new_address"],
    "birth": ["child"],
    "death": ["person"],
    "tax_return": [],
}
# Organisations a single online form informs of a new address (normalized issuer words).
PUBLIC_BODIES = (
    "caf",
    "cpam",
    "assurance maladie",
    "dgfip",
    "finances publiques",
    "france travail",
    "urssaf",
    "assurance retraite",
    "msa",
)
# Categories of the organisations the user has a running relationship with.
RELATIONSHIPS = {
    Category.ENERGY,
    Category.TELECOM,
    Category.INSURANCE,
    Category.BANK,
    Category.HEALTH,
    Category.WORK,
}


class UnknownKind(ValueError):
    pass


class UnknownStep(ValueError):
    pass


class StepAction(BaseModel):
    # "letter" (params of POST /api/letters), "folder" (params.kind) or "open" (params.url).
    type: Literal["letter", "folder", "open"]
    label: str
    params: dict[str, Any] = {}


class Step(BaseModel):
    key: str
    title: str
    detail: str
    due: date | None = None
    done: bool = False
    # Done on its own: the letter was sent, the document arrived.
    auto: bool = False
    document_ids: list[int] = []
    amount: float | None = None
    action: StepAction | None = None


class JourneyOut(BaseModel):
    id: int
    kind: str
    title: str
    description: str
    event_label: str
    event_date: date
    details: dict[str, str]
    steps: list[Step]
    done: int
    total: int
    closed: bool
    created_at: datetime


class KindInfo(BaseModel):
    kind: str
    title: str
    description: str
    event_label: str
    default_date: date | None
    # Labels of what can be told when starting ({key: label}).
    fields: dict[str, str]


def default_date(kind: str, today: date | None = None) -> date | None:
    """A sensible starting date: the next return deadline; nothing for the other events."""
    if kind != "tax_return":
        return None
    today = today or date.today()
    # Online deadlines fall between late May and early June depending on the département.
    year = today.year if today < date(today.year, 6, 10) else today.year + 1
    return date(year, 6, 1)


def kinds(today: date | None = None) -> list[KindInfo]:
    return [
        KindInfo(
            kind=k,
            title=T(f"{k}_title"),
            description=T(f"{k}_description"),
            event_label=T(f"{k}_event"),
            default_date=default_date(k, today),
            fields={f: T(f"field_{f}") for f in FIELDS[k]},
        )
        for k in KINDS
    ]


# --- Building the steps ----------------------------------------------------------------------


@dataclass
class _Context:
    journey: Journey
    details: dict[str, str]
    docs: list[Document]
    letters: list[Correspondence]
    done: set[str]
    today: date
    steps: list[Step] = field(default_factory=list)

    @property
    def day(self) -> date:
        return self.journey.event_date

    def of_type(self, *types: DocType) -> list[Document]:
        return sorted((d for d in self.docs if d.doc_type in types), key=_date_of, reverse=True)

    def add(
        self,
        key: str,
        title: str,
        detail: str,
        due: date | None,
        *,
        documents: list[Document] | None = None,
        amount: float | None = None,
        action: StepAction | None = None,
        proof: bool = False,
    ) -> Step:
        letter = self._letter_for(action)
        if letter is not None and letter.sent_on is not None:
            proof = True
            detail = f"{detail} {T('letter_sent', date=letter.sent_on)}"
        elif letter is not None:
            detail = f"{detail} {T('letter_drafted')}"
        step = Step(
            key=key,
            title=title,
            detail=detail,
            due=due,
            done=key in self.done or proof,
            auto=proof and key not in self.done,
            document_ids=[d.id for d in documents or [] if d.id is not None],
            amount=amount,
            action=action,
        )
        self.steps.append(step)
        return step

    def _letter_for(self, action: StepAction | None) -> Correspondence | None:
        """The letter written for this step since the journey started (same document, same
        kind or purpose)."""
        if action is None or action.type != "letter":
            return None
        doc_id = action.params.get("document_id")
        kind = action.params.get("kind")
        for row in self.letters:
            if row.document_id != doc_id:
                continue
            if kind is None or row.kind == kind:
                return row
        return None


def _date_of(doc: Document) -> date:
    return doc.issue_date or doc.due_date or doc.created_at.date()


def _letter(
    *,
    doc: Document | None = None,
    kind: str | None = None,
    purpose: str = "",
    details: str = "",
) -> StepAction:
    params: dict[str, Any] = {}
    if kind:
        params["kind"] = kind
    if purpose:
        params["purpose"] = purpose
    if details:
        params["details"] = details
    if doc is not None and doc.id is not None:
        params["document_id"] = doc.id
    return StepAction(type="letter", label=T("write_letter"), params=params)


def _folder(kind: str) -> StepAction:
    return StepAction(type="folder", label=T("prepare_folder"), params={"kind": kind})


def _is_public(issuer: str) -> bool:
    norm = normalize(issuer)
    return any(body in norm for body in PUBLIC_BODIES)


def _organisations(docs: list[Document]) -> list[Document]:
    """One document per organisation the user has a running relationship with (most recent
    first), skipping one-off documents."""
    latest: dict[str, Document] = {}
    for doc in sorted(docs, key=_date_of, reverse=True):
        if not doc.issuer or doc.category not in RELATIONSHIPS:
            continue
        latest.setdefault(normalize(doc.issuer), doc)
    return list(latest.values())


def _is_home_insurance(doc: Document) -> bool:
    return doc.category == Category.INSURANCE and doc.area == "housing"


def _is_health_cover(doc: Document) -> bool:
    insurer = doc.category == Category.INSURANCE and doc.area == "health"
    return insurer or (doc.category == Category.HEALTH and not _is_public(doc.issuer or ""))


def _moving(ctx: _Context) -> None:
    day = ctx.day
    new_address = ctx.details.get("new_address", "").strip()
    housing = ctx.of_type(DocType.LEASE, DocType.RENT_RECEIPT)
    tenant = housing[0] if housing else None
    if tenant is not None:
        ctx.add(
            "notice",
            T("notice_title"),
            T("notice_detail"),
            day - timedelta(days=90),
            documents=[tenant],
            action=_letter(doc=tenant, purpose=T("notice_purpose", date=day)),
        )
    ctx.add("mail", T("mail_title"), T("mail_detail"), day - timedelta(days=7))
    details = letters.address_details(new_address, day) if new_address else ""
    # Whatever the document (tax notice, benefits), these are told by one online form.
    public = list(dict.fromkeys(d.issuer for d in ctx.docs if d.issuer and _is_public(d.issuer)))
    for doc in _organisations(ctx.docs):
        issuer = doc.issuer or ""
        if _is_public(issuer) or (tenant is not None and doc.issuer == tenant.issuer):
            continue
        letter = _letter(doc=doc, kind="address_change", details=details)
        key = f"org:{normalize(issuer)}"
        if doc.category in (Category.ENERGY, Category.TELECOM):
            title, detail, due = T("transfer_title", issuer=issuer), T("transfer_detail"), -15
        elif _is_home_insurance(doc):
            title = T("home_insurance_title", issuer=issuer)
            detail, due = T("home_insurance_detail"), -7
        else:
            title, detail, due = T("tell_title", issuer=issuer), T("tell_detail"), 30
        ctx.add(key, title, detail, day + timedelta(days=due), documents=[doc], action=letter)
    detail = T("public_detail")
    if public:
        names = T("list_separator").join(public)
        detail = f"{detail} {T('public_found', names=names)}"
    ctx.add("public", T("public_title"), detail, day + timedelta(days=30))
    if tenant is not None:
        ctx.add("inventory", T("inventory_title"), T("inventory_detail"), day)
        ctx.add(
            "deposit",
            T("deposit_title"),
            T("deposit_detail"),
            day + timedelta(days=60),
            documents=[tenant],
            action=_letter(doc=tenant, kind="formal_notice", details=T("deposit_purpose")),
        )
    # Any car paper (inspection, fine…) means a registration certificate to update.
    if any(d.category == Category.VEHICLE for d in ctx.docs):
        ctx.add(
            "vehicle",
            T("vehicle_title"),
            T("vehicle_detail"),
            day + timedelta(days=30),
            documents=ctx.of_type(DocType.VEHICLE_REGISTRATION)[:1],
        )
    if any(d.category == Category.FAMILY for d in ctx.docs):
        ctx.add(
            "school",
            T("school_title"),
            T("school_detail"),
            day - timedelta(days=30),
            action=_folder("school"),
        )
    ctx.add("electoral", T("electoral_title"), T("electoral_detail"), day + timedelta(days=60))


def _employer(docs: list[Document]) -> Document | None:
    slips = sorted(
        (
            d
            for d in docs
            if d.doc_type in (DocType.PAYSLIP, DocType.EMPLOYMENT_CONTRACT) and d.issuer
        ),
        key=_date_of,
        reverse=True,
    )
    return slips[0] if slips else None


def _arrived_since(ctx: _Context, *types: DocType) -> list[Document]:
    """Documents of these types added since the journey started."""
    start = ctx.journey.created_at.replace(tzinfo=None)
    return [d for d in ctx.of_type(*types) if d.created_at.replace(tzinfo=None) >= start]


def _birth(ctx: _Context) -> None:
    day = ctx.day
    if day > ctx.today:
        ctx.add("childcare", T("childcare_title"), T("childcare_detail"), day - timedelta(days=120))
    employer = _employer(ctx.docs)
    ctx.add(
        "leave",
        T("leave_title"),
        T("leave_detail"),
        day - timedelta(days=30),
        documents=[employer] if employer else None,
        action=_letter(doc=employer, purpose=T("leave_purpose", date=day)),
    )
    papers = ctx.of_type(DocType.IDENTITY_CARD, DocType.PASSPORT, DocType.FAMILY_RECORD_BOOK)
    ctx.add(
        "declare",
        T("declare_birth_title"),
        T("declare_birth_detail"),
        day + timedelta(days=5),
        documents=papers[:3],
    )
    records = [d for d in _arrived_since(ctx, DocType.CIVIL_STATUS) if _date_of(d) >= day]
    ctx.add(
        "record",
        T("birth_record_title"),
        T("birth_record_detail"),
        day + timedelta(days=15),
        documents=records[:1],
        proof=bool(records),
    )
    ctx.add("health", T("health_child_title"), T("health_child_detail"), day + timedelta(days=30))
    for doc in _organisations(ctx.docs):
        if not _is_health_cover(doc):
            continue
        issuer = doc.issuer or ""
        ctx.add(
            f"org:{normalize(issuer)}",
            T("mutual_title", issuer=issuer),
            T("mutual_detail"),
            day + timedelta(days=30),
            documents=[doc],
            action=_letter(doc=doc, purpose=T("mutual_purpose", date=day)),
        )
    caf = [d for d in ctx.docs if d.issuer and "caf" in normalize(d.issuer).split()]
    ctx.add(
        "caf",
        T("caf_birth_title"),
        T("caf_birth_detail"),
        day + timedelta(days=30),
        documents=sorted(caf, key=_date_of, reverse=True)[:1],
    )
    ctx.add("tax", T("tax_birth_title"), T("tax_birth_detail"), day + timedelta(days=60))


def _death(ctx: _Context) -> None:
    day = ctx.day
    person = ctx.details.get("person", "").strip()
    theirs = [d for d in ctx.docs if person and household.same_person(d.person, person)]
    ctx.add("declare", T("declare_death_title"), T("declare_death_detail"), day + timedelta(days=1))
    copies = _arrived_since(ctx, DocType.CIVIL_STATUS)
    ctx.add(
        "copies",
        T("death_copies_title"),
        T("death_copies_detail"),
        day + timedelta(days=3),
        documents=copies[:1],
        proof=bool(copies),
    )
    ctx.add("pension", T("pension_title"), T("pension_detail"), day + timedelta(days=7))
    contracts = banks = 0
    for doc in _organisations(theirs):
        issuer = doc.issuer or ""
        if _is_public(issuer) or doc.category == Category.WORK:
            continue
        key = f"org:{normalize(issuer)}"
        if doc.category == Category.BANK:
            purpose = T("bank_purpose", person=person, date=day)
            title, detail, due = T("bank_title", issuer=issuer), T("bank_detail"), 7
            banks += 1
        else:
            purpose = T("contract_purpose", person=person, date=day)
            title, detail, due = T("contract_title", issuer=issuer), T("contract_detail"), 30
            contracts += 1
        ctx.add(
            key,
            title,
            detail,
            day + timedelta(days=due),
            documents=[doc],
            action=_letter(doc=doc, purpose=purpose),
        )
    if not banks:
        ctx.add("bank", T("banks_title"), T("bank_detail"), day + timedelta(days=7))
    if not contracts:
        ctx.add("contracts", T("contracts_title"), T("contracts_detail"), day + timedelta(days=30))
    if any(d.doc_type in (DocType.LEASE, DocType.RENT_RECEIPT) for d in theirs):
        ctx.add("lease", T("lease_death_title"), T("lease_death_detail"), day + timedelta(days=30))
    ctx.add("health", T("health_death_title"), T("health_death_detail"), day + timedelta(days=30))
    if any(d.category == Category.SOCIAL for d in theirs):
        ctx.add("caf", T("caf_death_title"), T("caf_death_detail"), day + timedelta(days=30))
    ctx.add(
        "life_insurance",
        T("life_insurance_title"),
        T("life_insurance_detail"),
        day + timedelta(days=60),
    )
    ctx.add("notary", T("notary_title"), T("notary_detail"), day + timedelta(days=30))
    ctx.add("estate", T("estate_title"), T("estate_detail"), day + timedelta(days=182))
    ctx.add(
        "last_return",
        T("last_return_title"),
        T("last_return_detail"),
        date(day.year + 1, 5, 31),
    )


def _in_year(docs: list[Document], year: int) -> list[Document]:
    return [d for d in docs if _date_of(d).year == year]


def _for_income_year(docs: list[Document], year: int) -> list[Document]:
    """Receipts of the income year, including the yearly ones sent from January to March of
    the next year."""
    return [
        d
        for d in docs
        if _date_of(d).year == year or (_date_of(d).year == year + 1 and _date_of(d).month <= 3)
    ]


def _tax_return(ctx: _Context, session: Session) -> None:
    deadline = ctx.day
    year = deadline.year - 1
    slips = _in_year(ctx.of_type(DocType.PAYSLIP), year)
    ctx.add(
        "salaries",
        T("salaries_title"),
        T("salaries_detail", year=year),
        deadline - timedelta(days=14),
        documents=slips[:1],
    )
    statements = _in_year(ctx.of_type(DocType.ANNUAL_TAX_STATEMENT), deadline.year)
    if statements or ctx.of_type(DocType.SAVINGS_STATEMENT):
        names = T("list_separator").join(dict.fromkeys(d.issuer or d.title for d in statements))
        detail = T("investments_detail", names=names) if names else T("investments_missing")
        ctx.add(
            "investments",
            T("investments_title"),
            detail,
            deadline - timedelta(days=14),
            documents=statements,
        )
    gifts = _for_income_year(ctx.of_type(DocType.DONATION_RECEIPT), year)
    total = round(sum(d.amount or 0 for d in gifts), 2)
    if total:
        title = T("donations_title", amount=total)
        detail = T("donations_detail", reduction=round(total * 0.66, 2))
    else:
        title, detail = T("donations_none_title"), T("donations_none_detail", year=year)
    ctx.add("donations", title, detail, deadline, documents=gifts, amount=total or None)
    childcare = _for_income_year(ctx.of_type(DocType.CHILDCARE_CERTIFICATE), year)
    if childcare or any(d.category == Category.FAMILY for d in ctx.docs):
        spent = round(sum(d.amount or 0 for d in childcare), 2)
        if spent:
            title = T("childcare_tax_title", amount=spent)
            detail = T("childcare_tax_detail", year=year)
        else:
            title, detail = T("childcare_tax_none_title"), T("childcare_tax_none_detail", year=year)
        ctx.add("childcare", title, detail, deadline, documents=childcare, amount=spent or None)
    ctx.add("other", T("other_title"), T("other_detail"), deadline)
    changes = _changes(session, year, ctx.journey.id)
    if changes:
        ctx.add(
            "changes",
            T("changes_title", year=year),
            _sentence(T("sentence_separator").join(changes)),
            deadline,
        )
    ctx.add("file", T("file_title"), T("file_detail"), deadline)
    notices = [d for d in ctx.of_type(DocType.TAX_NOTICE) if _date_of(d).year == deadline.year]
    ctx.add(
        "notice",
        T("tax_notice_title"),
        T("tax_notice_detail"),
        date(deadline.year, 9, 1),
        documents=notices[:1],
        proof=bool(notices),
    )


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


def _changes(session: Session, year: int, exclude: int | None) -> list[str]:
    """Life events of the income year, from the other journeys."""
    found = []
    for row in session.exec(select(Journey).where(Journey.kind != "tax_return")):
        if row.id == exclude or row.event_date.year != year:
            continue
        found.append(T(f"change_{row.kind}", date=row.event_date))
    return found


BUILDERS: dict[str, Callable[[_Context, Session], None]] = {
    "moving": lambda ctx, _session: _moving(ctx),
    "birth": lambda ctx, _session: _birth(ctx),
    "death": lambda ctx, _session: _death(ctx),
    "tax_return": _tax_return,
}


# --- Reading and changing ----------------------------------------------------------------


def _details(row: Journey) -> dict[str, str]:
    raw = json.loads(row.details or "{}")
    return {str(k): str(v) for k, v in raw.items() if v}


def title(row: Journey) -> str:
    """Kind title, with the person or child it concerns."""
    details = _details(row)
    name = details.get("person") or details.get("child")
    base = T(f"{row.kind}_title") if row.kind in KINDS else row.kind
    return T("titled", title=base, name=name) if name else base


def steps(session: Session, row: Journey, today: date | None = None) -> list[Step]:
    if row.kind not in BUILDERS:
        return []
    letters_since = list(
        session.exec(
            select(Correspondence)
            .where(col(Correspondence.created_at) >= row.created_at)
            .order_by(col(Correspondence.created_at).desc())
        )
    )
    ctx = _Context(
        journey=row,
        details=_details(row),
        docs=folders.current_documents(session),
        letters=letters_since,
        done=set(json.loads(row.done or "[]")),
        today=today or date.today(),
    )
    BUILDERS[row.kind](ctx, session)
    return sorted(ctx.steps, key=lambda s: (s.done, s.due or date.max))


def out(session: Session, row: Journey, today: date | None = None) -> JourneyOut:
    assert row.id is not None
    found = steps(session, row, today)
    return JourneyOut(
        id=row.id,
        kind=row.kind,
        title=title(row),
        description=T(f"{row.kind}_description") if row.kind in KINDS else "",
        event_label=T(f"{row.kind}_event") if row.kind in KINDS else "",
        event_date=row.event_date,
        details=_details(row),
        steps=found,
        done=sum(s.done for s in found),
        total=len(found),
        closed=row.closed,
        created_at=row.created_at,
    )


def active(session: Session) -> list[Journey]:
    return list(
        session.exec(
            select(Journey)
            .where(Journey.closed == False)  # noqa: E712
            .order_by(col(Journey.event_date))
        )
    )


def start(
    session: Session,
    kind: str,
    event_date: date | None = None,
    details: dict[str, str] | None = None,
    *,
    actor: str = "user",
) -> Journey:
    """Starts a journey (or returns the open one of the same kind and person, updated)."""
    if kind not in KINDS:
        raise UnknownKind(kind)
    event_date = event_date or default_date(kind) or date.today()
    clean = {k: v.strip() for k, v in (details or {}).items() if k in FIELDS[kind] and v.strip()}
    for row in active(session):
        if row.kind == kind and _details(row).get("person") == clean.get("person"):
            undo.row_changed(row)
            row.event_date = event_date
            row.details = json.dumps({**_details(row), **clean}, ensure_ascii=False)
            session.add(row)
            return row
    row = Journey(kind=kind, event_date=event_date, details=json.dumps(clean, ensure_ascii=False))
    session.add(row)
    session.flush()
    undo.push("row_created", model="Journey", id=row.id)
    activity.log(session, "journey", T.msg("started", title=title(row)), actor=actor)
    return row


def update(
    session: Session,
    row: Journey,
    *,
    event_date: date | None = None,
    details: dict[str, str] | None = None,
    closed: bool | None = None,
    actor: str = "user",
) -> None:
    undo.row_changed(row)
    if event_date is not None:
        row.event_date = event_date
    if details is not None:
        allowed = FIELDS.get(row.kind, [])
        merged = {**_details(row), **{k: v.strip() for k, v in details.items() if k in allowed}}
        row.details = json.dumps({k: v for k, v in merged.items() if v}, ensure_ascii=False)
    if closed is not None and closed != row.closed:
        row.closed = closed
        key = "closed" if closed else "reopened"
        activity.log(session, "journey", T.msg(key, title=title(row)), actor=actor)
    session.add(row)


def set_step(session: Session, row: Journey, key: str, done: bool, *, actor: str = "user") -> Step:
    """Ticks (or unticks) a step."""
    found = next((s for s in steps(session, row) if s.key == key), None)
    if found is None:
        raise UnknownStep(key)
    undo.row_changed(row)
    current = [k for k in json.loads(row.done or "[]") if k != key]
    if done:
        current.append(key)
    row.done = json.dumps(current)
    session.add(row)
    msg = "step_done" if done else "step_undone"
    activity.log(session, "journey", T.msg(msg, title=title(row), step=found.title), actor=actor)
    return found.model_copy(update={"done": done or found.auto})


def due_steps(session: Session, today: date, within: int) -> list[tuple[Journey, Step]]:
    """Steps still to do that are due within `within` days (or late), in every open journey."""
    found = []
    for row in active(session):
        for step in steps(session, row, today):
            if not step.done and step.due is not None and step.due <= today + timedelta(within):
                found.append((row, step))
    return found
