"""Annotated fictitious documents: demo set and basis of the evaluation.

Each sample is a PDF generated on the fly with its expected values. Their content mirrors real
French administrative documents, so it stays in French. Dates are relative to `today` so that
the demo dashboard shows upcoming deadlines.

They tell the story of one typical French household, so that every part of the agent has
something to show: the Martins, tenants of a flat in Lyon. Camille is an employee, Thomas is
self-employed, they have two children, Léa (8) and Hugo (5). Their paperwork holds an income
tax balance due within days, an electricity bill on the rise, a phone bill debited twice, a CAF
overpayment claim, a rent charges catch-up, an identity card to renew and no bank details (RIB)
yet.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pymupdf

from binder.models import Category, DocType


@dataclass
class Sample:
    filename: str
    html: str
    expected: dict[str, Any]

    def pdf(self) -> bytes:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_htmlbox(pymupdf.Rect(48, 48, 547, 794), self.html, css=CSS)
        # Fixed metadata and no random identifier: same content, same bytes.
        doc.set_metadata({})
        data = doc.tobytes(no_new_id=True)
        doc.close()
        return bytes(data)


CSS = """
* { font-family: sans-serif; font-size: 10pt; color: #1f2937; }
h1 { font-size: 16pt; margin: 0 0 6pt 0; }
h2 { font-size: 11pt; color: #475569; margin: 0 0 14pt 0; }
table { width: 100%; border-collapse: collapse; margin: 10pt 0; }
td { padding: 4pt; border-bottom: 1px solid #e5e7eb; }
.big { font-size: 13pt; font-weight: bold; }
.muted { color: #6b7280; font-size: 8pt; }
"""


def _fr(d: date) -> str:
    """Date as written in French documents (15/10/2026)."""
    return d.strftime("%d/%m/%Y")


def _money(v: float) -> str:
    """Amount as written in French documents (1 240,00 €)."""
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"


MONTHS_FR = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def _long(d: date) -> str:
    """Date written out in French (15 octobre 2026)."""
    return f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"


HOME = "12 rue des Tilleuls, 69003 Lyon"


def build_samples(today: date | None = None) -> list[Sample]:
    t = today or date.today()
    d = lambda n: t + timedelta(days=n)  # noqa: E731
    y = t.year
    samples: list[Sample] = []

    def add(filename: str, html: str, **expected: Any) -> None:
        samples.append(Sample(filename, html, expected))

    add(
        "avis-imposition.pdf",
        f"""<p>RÉPUBLIQUE FRANÇAISE</p><h1>DIRECTION GÉNÉRALE DES FINANCES PUBLIQUES</h1>
        <h2>AVIS D'IMPÔT {y} SUR LES REVENUS DE L'ANNÉE {y - 1}</h2>
        <p>Déclarant 1 : Camille Martin</p><p>Déclarant 2 : Thomas Martin</p><p>{HOME}</p>
        <p>Numéro fiscal : 30 12 456 789 012</p>
        <p>Date d'établissement : {_fr(d(-35))}</p>
        <table><tr><td>Revenu fiscal de référence</td><td>52 310 €</td></tr>
        <tr><td>Nombre de parts</td><td>3</td></tr>
        <tr><td>Impôt sur le revenu net</td><td>3 186 €</td></tr>
        <tr><td>Retenues à la source déjà versées</td><td>1 946 €</td></tr>
        <tr><td>Montant restant à payer</td><td class="big">{_money(1240)}</td></tr>
        <tr><td>Date limite de paiement</td><td>{_long(d(5))}</td></tr></table>
        <p class="muted">Payez en ligne sur impots.gouv.fr ou avec l'application mobile.</p>""",
        category=Category.TAXES,
        doc_type=DocType.TAX_NOTICE,
        amount=1240.0,
        due_date=d(5),
        issue_date=d(-35),
        reference="30 12 456 789 012",
    )
    add(
        "maif-echeance.pdf",
        f"""<h1>MAIF</h1><h2>Avis d'échéance — Assurance habitation</h2>
        <p>N° de contrat : 4521877 H</p><p>Édité le {_fr(d(-25))}</p>
        <p>Souscripteur : Camille Martin</p>
        <p>Logement assuré : {HOME}, appartement de 4 pièces occupé en tant que locataire.</p>
        <p>Votre contrat d'assurance habitation Raqvam sera renouvelé.</p>
        <table><tr><td>Cotisation annuelle TTC</td><td class="big">{_money(278)}</td></tr>
        <tr><td>Échéance</td><td>{_fr(d(18))}</td></tr></table>""",
        category=Category.INSURANCE,
        doc_type=DocType.PAYMENT_NOTICE,
        amount=278.0,
        due_date=d(18),
        issue_date=d(-25),
        reference="4521877 H",
    )
    for name, issued in (("attestation-maif-ancienne.pdf", -375), ("attestation-maif.pdf", -8)):
        add(
            name,
            f"""<h1>MAIF</h1><h2>Attestation d'assurance habitation</h2>
            <p>N° de contrat : 4521877 H</p><p>Fait le {_fr(d(issued))}</p>
            <p>La MAIF atteste que Mme Camille Martin est assurée en responsabilité civile pour
            le logement situé {HOME}, qu'elle occupe en tant que locataire.</p>
            <p>Attestation valable jusqu'au {_fr(d(issued + 365))}.</p>""",
            category=Category.INSURANCE,
            doc_type=DocType.INSURANCE_CERTIFICATE,
            amount=None,
            due_date=None,
            issue_date=d(issued),
            expiry_date=d(issued + 365),
            reference="4521877 H",
        )
    add(
        "facture-edf.pdf",
        f"""<h1>EDF</h1><h2>Votre facture d'électricité</h2>
        <p>Facture du {_fr(d(-12))} — N° client : 6012 3456 78</p>
        <p>Titulaire : Camille Martin — {HOME}</p>
        <table><tr><td>Consommation</td><td>312 kWh</td></tr>
        <tr><td>Abonnement</td><td>{_money(14.12)}</td></tr>
        <tr><td>Total TTC à payer</td><td class="big">{_money(94.37)}</td></tr></table>
        <p>Montant prélevé le {_fr(d(12))} sur votre compte.</p>""",
        category=Category.ENERGY,
        doc_type=DocType.INVOICE,
        amount=94.37,
        due_date=d(12),
        issue_date=d(-12),
        reference="6012 3456 78",
    )
    add(
        "facture-edf-juillet.pdf",
        f"""<h1>EDF</h1><h2>Votre facture d'électricité</h2>
        <p>Facture du {_fr(d(-72))} — N° client : 6012 3456 78</p>
        <p>Titulaire : Camille Martin — {HOME}</p>
        <table><tr><td>Consommation</td><td>268 kWh</td></tr>
        <tr><td>Total TTC à payer</td><td class="big">{_money(81.05)}</td></tr></table>""",
        category=Category.ENERGY,
        doc_type=DocType.INVOICE,
        amount=81.05,
        due_date=None,
        issue_date=d(-72),
        reference="6012 3456 78",
    )
    add(
        "attestation-caf.pdf",
        f"""<h1>Caisse d'allocations familiales du Rhône</h1><h2>Attestation de paiement</h2>
        <p>Allocataire : Camille Martin</p><p>Numéro allocataire : 7788123</p>
        <p>Fait le {_fr(d(-9))}</p>
        <p>Enfants à charge : Léa (8 ans) et Hugo (5 ans).</p>
        <p>La CAF certifie avoir versé les allocations familiales pour un montant mensuel de
        {_money(151.08)}.</p>""",
        category=Category.SOCIAL,
        doc_type=DocType.CERTIFICATE,
        amount=151.08,
        due_date=None,
        issue_date=d(-9),
        reference="7788123",
    )
    add(
        "trop-percu-caf.pdf",
        f"""<h1>CAF du Rhône — Caisse d'allocations familiales</h1>
        <h2>Notification de trop-perçu</h2>
        <p>Allocataire : Camille Martin</p><p>Numéro allocataire : 7788123</p>
        <p>Date : {_fr(d(-4))}</p>
        <p>Madame, après examen de vos ressources de {y - 1}, votre droit à l'allocation de
        rentrée scolaire versée en août {y} a été recalculé : cette somme vous a été versée à
        tort.</p>
        <table><tr><td>Montant du trop-perçu</td><td class="big">{_money(423.48)}</td></tr>
        <tr><td>À rembourser avant le</td><td>{_fr(d(28))}</td></tr></table>
        <p>Vous pouvez contester cette décision dans un délai de deux mois auprès de la
        commission de recours amiable, ou demander un échelonnement.</p>""",
        category=Category.SOCIAL,
        doc_type=DocType.BENEFIT_DECISION,
        amount=423.48,
        due_date=d(28),
        issue_date=d(-4),
        reference="7788123",
    )
    add(
        "releve-bancaire.pdf",
        f"""<h1>Crédit Agricole Centre-Est</h1><h2>Relevé de compte</h2>
        <p>Titulaire : Camille Martin</p>
        <p>Date du relevé : {_fr(d(-14))}</p><p>IBAN FR89 1780 6000 1234 5678 9012 345</p>
        <table><tr><td>Solde créditeur au {_fr(d(-14))}</td><td>{_money(2310.18)}</td></tr>
        <tr><td>VIR SALAIRE STUDIO ATLAS</td><td>+ {_money(2134.56)}</td></tr>
        <tr><td>PRLV SEPA REGIE BROTTEAUX</td><td>- {_money(1210)}</td></tr>
        <tr><td>PRLV SEPA EDF</td><td>- {_money(81.05)}</td></tr>
        <tr><td>PRLV SEPA ORANGE</td><td>- {_money(39.99)}</td></tr>
        <tr><td>PRLV SEPA ORANGE</td><td>- {_money(39.99)}</td></tr>
        <tr><td>CB CARREFOUR LYON</td><td>- {_money(86.40)}</td></tr></table>""",
        category=Category.BANK,
        doc_type=DocType.BANK_STATEMENT,
        amount=2310.18,
        due_date=None,
        issue_date=d(-14),
        reference=None,
    )
    add(
        "quittance-loyer.pdf",
        f"""<h1>Quittance de loyer</h1>
        <p>Bailleur : SCI Les Tilleuls, représentée par la Régie Brotteaux Immobilier</p>
        <p>Locataire : Camille Martin</p><p>Logement : {HOME}, 3e étage</p>
        <p>Fait le {_fr(d(-3))}</p>
        <table><tr><td>Loyer</td><td>{_money(1090)}</td></tr>
        <tr><td>Provision pour charges</td><td>{_money(120)}</td></tr>
        <tr><td>Total</td><td class="big">{_money(1210)}</td></tr></table>
        <p>Prochain loyer à payer avant le {_fr(d(25))}.</p>""",
        category=Category.HOUSING,
        doc_type=DocType.RENT_RECEIPT,
        amount=1210.0,
        due_date=d(25),
        issue_date=d(-3),
        reference=None,
    )
    add(
        "regularisation-charges.pdf",
        f"""<h1>Régie Brotteaux Immobilier</h1>
        <h2>Régularisation des charges locatives {y - 1}</h2>
        <p>Locataire : Camille Martin — {HOME}</p><p>Édité le {_fr(d(-1))}</p>
        <table><tr><td>Charges réelles {y - 1} (eau, chauffage, entretien)</td>
        <td>{_money(1625.40)}</td></tr>
        <tr><td>Provisions versées</td><td>{_money(1440)}</td></tr>
        <tr><td>Solde restant à payer</td><td class="big">{_money(185.40)}</td></tr>
        <tr><td>À régler avant le</td><td>{_fr(d(30))}</td></tr></table>
        <p>Les justificatifs sont consultables à la régie pendant six mois.</p>""",
        category=Category.HOUSING,
        doc_type=DocType.CHARGES_STATEMENT,
        amount=185.40,
        due_date=d(30),
        issue_date=d(-1),
        reference=None,
    )
    add(
        "facture-orange.pdf",
        f"""<h1>Orange</h1><h2>Facture mobile et internet</h2>
        <p>Facture n° 2026-884512 du {_fr(d(-6))}</p><p>Titulaire : Camille Martin</p>
        <table><tr><td>Forfait mobile</td><td>{_money(19.99)}</td></tr>
        <tr><td>Abonnement internet Livebox</td><td>{_money(20)}</td></tr>
        <tr><td>Montant total à payer</td><td class="big">{_money(39.99)}</td></tr></table>
        <p>Prélevé le {_fr(d(20))}</p>""",
        category=Category.TELECOM,
        doc_type=DocType.INVOICE,
        amount=39.99,
        due_date=d(20),
        issue_date=d(-6),
        reference="2026-884512",
    )
    add(
        "bulletin-paie.pdf",
        f"""<h1>Bulletin de paie</h1><p>Employeur : Studio Atlas SAS, Lyon</p>
        <p>Salariée : Camille Martin — Emploi : graphiste</p>
        <p>Période : {MONTHS_FR[d(-30).month - 1]} {d(-30).year} — Édité le {_fr(d(-28))}</p>
        <table><tr><td>Salaire brut</td><td>{_money(2750)}</td></tr>
        <tr><td>Net imposable</td><td>{_money(2201.4)}</td></tr>
        <tr><td>Net à payer</td><td class="big">{_money(2134.56)}</td></tr></table>""",
        category=Category.WORK,
        doc_type=DocType.PAYSLIP,
        amount=2134.56,
        due_date=None,
        issue_date=d(-28),
        reference=None,
    )
    add(
        "decompte-ameli.pdf",
        f"""<h1>Assurance Maladie — ameli.fr</h1><h2>Décompte de remboursement de soins</h2>
        <p>CPAM du Rhône — Édité le {_fr(d(-11))}</p><p>Bénéficiaire : Hugo Martin</p>
        <table><tr><td>Consultation de pédiatrie</td><td>{_money(30)}</td></tr>
        <tr><td>Montant remboursé</td><td class="big">{_money(21)}</td></tr></table>
        <p>La part complémentaire a été transmise à votre mutuelle.</p>""",
        category=Category.HEALTH,
        doc_type=DocType.REIMBURSEMENT_STATEMENT,
        amount=21.0,
        due_date=None,
        issue_date=d(-11),
        reference=None,
    )
    add(
        "carte-identite.pdf",
        f"""<h1>RÉPUBLIQUE FRANÇAISE</h1><h2>Carte nationale d'identité</h2>
        <p>Nom : MARTIN — Prénom : Camille</p><p>Lieu de naissance : Lyon (69)</p>
        <p>Date de délivrance : {_fr(d(-3585))}</p><p>Date d'expiration : {_fr(d(65))}</p>""",
        category=Category.IDENTITY,
        doc_type=DocType.IDENTITY_CARD,
        amount=None,
        due_date=None,
        issue_date=d(-3585),
        expiry_date=d(65),
        reference=None,
    )
    add(
        "controle-technique.pdf",
        f"""<h1>Autosur — Centre de contrôle technique de Lyon Gerland</h1>
        <h2>Procès-verbal de contrôle technique</h2>
        <p>Titulaire : Thomas Martin</p>
        <p>Peugeot 308 — Immatriculation : AB-123-CD — Kilométrage : 84 210 km</p>
        <p>Date du contrôle : {_fr(d(-160))}</p><p>Résultat : favorable</p>
        <table><tr><td>Montant TTC</td><td class="big">{_money(78)}</td></tr></table>
        <p>Prochain contrôle à effectuer avant le {_fr(d(570))}</p>""",
        category=Category.VEHICLE,
        doc_type=DocType.ROADWORTHINESS_TEST,
        amount=78.0,
        due_date=None,
        issue_date=d(-160),
        expiry_date=d(570),
        reference=None,
    )
    add(
        "note-garage.pdf",
        f"""<h1>Garage du Centre</h1><p>Devis réparation du {_fr(d(-2))}</p>
        <p>Peugeot 308 : remplacement des plaquettes de frein avant, main-d'œuvre comprise :
        145 €</p>""",
        category=Category.OTHER,
        doc_type=DocType.QUOTE,
        amount=145.0,
        due_date=None,
        issue_date=d(-2),
        reference=None,
    )
    add(
        "recu-don.pdf",
        f"""<h1>Ligue contre le cancer — Comité du Rhône</h1>
        <h2>Reçu au titre des dons à certains organismes d'intérêt général</h2>
        <p>Cerfa n° 11580*04 — Reçu n° R-{y}-04417</p><p>Donateur : Camille Martin, {HOME}</p>
        <p>Le bénéficiaire reconnaît avoir reçu au titre des dons et versements ouvrant droit à
        réduction d'impôt la somme de :</p>
        <table><tr><td>Montant du don</td><td class="big">{_money(120)}</td></tr>
        <tr><td>Date du versement</td><td>{_fr(d(-48))}</td></tr></table>
        <p>Fait le {_fr(d(-45))}. Articles 200 et 238 bis du code général des impôts.</p>""",
        category=Category.TAXES,
        doc_type=DocType.DONATION_RECEIPT,
        amount=120.0,
        due_date=None,
        issue_date=d(-45),
        reference=f"R-{y}-04417",
    )
    add(
        "attestation-garde.pdf",
        f"""<h1>Ville de Lyon — Accueil périscolaire</h1>
        <h2>Attestation de frais de garde</h2>
        <p>Enfant : Hugo Martin, né le 14/03/{y - 5}</p><p>Responsable : Camille Martin</p>
        <p>Établi le {_fr(d(-5))}</p>
        <table><tr><td>Garderie du matin et du soir, janvier à septembre {y}</td>
        <td class="big">{_money(486)}</td></tr></table>
        <p>Attestation à conserver pour la déclaration de vos revenus.</p>""",
        category=Category.FAMILY,
        doc_type=DocType.CHILDCARE_CERTIFICATE,
        amount=486.0,
        due_date=None,
        issue_date=d(-5),
        reference=None,
    )
    add(
        "avis-contravention.pdf",
        f"""<h1>Agence nationale de traitement automatisé des infractions (ANTAI)</h1>
        <h2>Avis de contravention</h2><p>Titulaire du certificat d'immatriculation : Thomas
        Martin</p><p>Véhicule : Peugeot 308 — AB-123-CD</p>
        <p>Date d'envoi : {_fr(d(-10))}</p><p>Numéro de l'avis : 7012 4458 9931</p>
        <p>Excès de vitesse inférieur à 20 km/h, limitation 80 km/h, vitesse retenue 89 km/h.</p>
        <table><tr><td>Montant de l'amende forfaitaire</td><td class="big">{_money(135)}</td></tr>
        <tr><td>À payer avant le</td><td>{_fr(d(35))}</td></tr></table>
        <p>Montant minoré de 90 € en cas de paiement dans les 15 jours. Vous pouvez contester
        cet avis dans un délai de 45 jours sur antai.gouv.fr.</p>""",
        category=Category.VEHICLE,
        doc_type=DocType.FINE,
        amount=135.0,
        due_date=d(35),
        issue_date=d(-10),
        reference="7012 4458 9931",
    )
    add(
        "certificat-scolarite.pdf",
        f"""<h1>École élémentaire Jean Macé — Lyon 3e</h1>
        <h2>Certificat de scolarité</h2>
        <p>La directrice certifie que l'élève Léa Martin, née le 02/06/{y - 8}, est inscrite en
        classe de CE2 pour l'année scolaire {y}-{y + 1}.</p>
        <p>Fait le {_fr(d(-25))}, à Lyon</p>""",
        category=Category.FAMILY,
        doc_type=DocType.SCHOOL_CERTIFICATE,
        amount=None,
        due_date=None,
        issue_date=d(-25),
        reference=None,
    )
    return samples
