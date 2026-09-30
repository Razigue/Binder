"""Documents fictifs annotés : jeu de démonstration et base de l'évaluation.

Chaque échantillon est un PDF généré à la volée avec ses valeurs attendues. Les dates sont
relatives à `today` pour que le tableau de bord de démo montre des échéances à venir.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pymupdf

from binder.models import Category


@dataclass
class Sample:
    filename: str
    html: str
    expected: dict[str, Any]

    def pdf(self) -> bytes:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_htmlbox(pymupdf.Rect(48, 48, 547, 794), self.html, css=CSS)
        # Métadonnées fixes et pas d'identifiant aléatoire : même contenu, mêmes octets.
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
    return d.strftime("%d/%m/%Y")


def _money(v: float) -> str:
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
    return f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"


def build_samples(today: date | None = None) -> list[Sample]:
    t = today or date.today()
    d = lambda n: t + timedelta(days=n)  # noqa: E731
    y = t.year
    samples: list[Sample] = []

    def add(filename: str, html: str, **expected: Any) -> None:
        samples.append(Sample(filename, html, expected))

    add(
        "taxe-fonciere.pdf",
        f"""<p>RÉPUBLIQUE FRANÇAISE</p><h1>DIRECTION GÉNÉRALE DES FINANCES PUBLIQUES</h1>
        <h2>AVIS D'IMPÔT {y} — TAXES FONCIÈRES</h2>
        <p>Date d'établissement : {_fr(d(-20))}</p>
        <p>Référence de l'avis : 26 94 318 204 117</p>
        <table><tr><td>Montant de votre taxe foncière</td><td class="big">{_money(1240)}</td></tr>
        <tr><td>Date limite de paiement</td><td>{_long(d(5))}</td></tr></table>
        <p class="muted">Payez en ligne sur impots.gouv.fr</p>""",
        category=Category.IMPOTS,
        amount=1240.0,
        due_date=d(5),
        issue_date=d(-20),
        reference="26 94 318 204 117",
    )
    add(
        "avis-imposition.pdf",
        f"""<h1>Finances publiques</h1><h2>Avis d'impôt {y} sur les revenus de {y - 1}</h2>
        <p>Numéro fiscal : 30 12 456 789 012</p><p>Date d'émission : {_fr(d(-18))}</p>
        <table><tr><td>Revenu fiscal de référence</td><td>32 480 €</td></tr>
        <tr><td>Montant restant à payer</td><td class="big">{_money(1842)}</td></tr>
        <tr><td>Date limite de paiement</td><td>{_fr(d(15))}</td></tr></table>""",
        category=Category.IMPOTS,
        amount=1842.0,
        due_date=d(15),
        issue_date=d(-18),
        reference="30 12 456 789 012",
    )
    add(
        "maif-echeance.pdf",
        f"""<h1>MAIF</h1><h2>Avis d'échéance — Assurance habitation</h2>
        <p>N° de contrat : 4521877 H</p><p>Édité le {_fr(d(-25))}</p>
        <p>Votre contrat d'assurance habitation Raqvam sera renouvelé.</p>
        <table><tr><td>Cotisation annuelle TTC</td><td class="big">{_money(278)}</td></tr>
        <tr><td>Échéance</td><td>{_fr(d(18))}</td></tr></table>""",
        category=Category.ASSURANCE,
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
            <p>La MAIF atteste que M. Martin est assuré en responsabilité civile pour le logement
            situé 12 rue des Tilleuls, 69003 Lyon.</p>
            <p>Attestation valable jusqu'au {_fr(d(issued + 365))}.</p>""",
            category=Category.ASSURANCE,
            amount=None,
            due_date=None,
            issue_date=d(issued),
            reference="4521877 H",
        )
    add(
        "facture-edf.pdf",
        f"""<h1>EDF</h1><h2>Votre facture d'électricité</h2>
        <p>Facture du {_fr(d(-12))} — N° client : 6012 3456 78</p>
        <table><tr><td>Consommation</td><td>312 kWh</td></tr>
        <tr><td>Abonnement</td><td>{_money(14.12)}</td></tr>
        <tr><td>Total TTC à payer</td><td class="big">{_money(94.37)}</td></tr></table>
        <p>Montant prélevé le {_fr(d(12))} sur votre compte.</p>""",
        category=Category.ENERGIE,
        amount=94.37,
        due_date=d(12),
        issue_date=d(-12),
        reference="6012 3456 78",
    )
    add(
        "facture-edf-juillet.pdf",
        f"""<h1>EDF</h1><h2>Votre facture d'électricité</h2>
        <p>Facture du {_fr(d(-72))} — N° client : 6012 3456 78</p>
        <table><tr><td>Consommation</td><td>268 kWh</td></tr>
        <tr><td>Total TTC à payer</td><td class="big">{_money(81.05)}</td></tr></table>""",
        category=Category.ENERGIE,
        amount=81.05,
        due_date=None,
        issue_date=d(-72),
        reference="6012 3456 78",
    )
    add(
        "attestation-caf.pdf",
        f"""<h1>Caisse d'allocations familiales</h1><h2>Attestation de paiement</h2>
        <p>Numéro allocataire : 7788123</p><p>Fait le {_fr(d(-9))}</p>
        <p>La CAF certifie avoir versé l'aide au logement (APL) pour un montant mensuel de
        {_money(212.45)}.</p>""",
        category=Category.SOCIAL,
        amount=212.45,
        due_date=None,
        issue_date=d(-9),
        reference="7788123",
    )
    add(
        "releve-bancaire.pdf",
        f"""<h1>Crédit Agricole</h1><h2>Relevé de compte</h2>
        <p>Date du relevé : {_fr(d(-14))}</p><p>IBAN FR76 1820 6000 1234 5678 9012 345</p>
        <table><tr><td>Solde créditeur au {_fr(d(-14))}</td><td>{_money(2310.18)}</td></tr>
        <tr><td>PRLV EDF</td><td>- {_money(81.05)}</td></tr></table>""",
        category=Category.BANQUE,
        amount=2310.18,
        due_date=None,
        issue_date=d(-14),
        reference=None,
    )
    add(
        "quittance-loyer.pdf",
        f"""<h1>Quittance de loyer</h1>
        <p>Bailleur : SCI Les Tilleuls — Locataire : M. Martin</p><p>Fait le {_fr(d(-3))}</p>
        <table><tr><td>Loyer</td><td>{_money(780)}</td></tr>
        <tr><td>Charges locatives</td><td>{_money(70)}</td></tr>
        <tr><td>Total</td><td class="big">{_money(850)}</td></tr></table>
        <p>Prochain loyer à payer avant le {_fr(d(25))}.</p>""",
        category=Category.LOGEMENT,
        amount=850.0,
        due_date=d(25),
        issue_date=d(-3),
        reference=None,
    )
    add(
        "facture-orange.pdf",
        f"""<h1>Orange</h1><h2>Facture mobile et internet</h2>
        <p>Facture n° 2026-884512 du {_fr(d(-6))}</p>
        <table><tr><td>Forfait mobile</td><td>{_money(19.99)}</td></tr>
        <tr><td>Abonnement internet Livebox</td><td>{_money(20)}</td></tr>
        <tr><td>Montant total à payer</td><td class="big">{_money(39.99)}</td></tr></table>
        <p>Prélevé le {_fr(d(20))}</p>""",
        category=Category.TELECOM,
        amount=39.99,
        due_date=d(20),
        issue_date=d(-6),
        reference="2026-884512",
    )
    add(
        "bulletin-paie.pdf",
        f"""<h1>Bulletin de paie</h1><p>Employeur : Studio Atlas SAS</p>
        <p>Période : {MONTHS_FR[d(-30).month - 1]} {d(-30).year} — Édité le {_fr(d(-28))}</p>
        <table><tr><td>Salaire brut</td><td>{_money(2750)}</td></tr>
        <tr><td>Net imposable</td><td>{_money(2201.4)}</td></tr>
        <tr><td>Net à payer</td><td class="big">{_money(2134.56)}</td></tr></table>""",
        category=Category.TRAVAIL,
        amount=2134.56,
        due_date=None,
        issue_date=d(-28),
        reference=None,
    )
    add(
        "decompte-ameli.pdf",
        f"""<h1>Assurance Maladie — ameli.fr</h1><h2>Décompte de remboursement de soins</h2>
        <p>CPAM de Paris — Édité le {_fr(d(-11))}</p>
        <table><tr><td>Consultation généraliste</td><td>{_money(30)}</td></tr>
        <tr><td>Montant remboursé</td><td class="big">{_money(23.40)}</td></tr></table>""",
        category=Category.SANTE,
        amount=23.40,
        due_date=None,
        issue_date=d(-11),
        reference=None,
    )
    add(
        "note-garage.pdf",
        f"""<h1>Garage du Centre</h1><p>Devis réparation du {_fr(d(-2))}</p>
        <p>Remplacement plaquettes de frein : 145 €</p>""",
        category=Category.AUTRE,
        amount=145.0,
        due_date=None,
        issue_date=d(-2),
        reference=None,
    )
    return samples
