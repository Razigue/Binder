# Binder

Coffre-fort administratif intelligent, **100 % local**.

Vous déposez vos papiers (PDF, photos). Binder les classe, extrait les informations clés
(montant, dates, référence, émetteur), suit les échéances et répond à vos questions.
Rien ne quitte votre machine : la base est chiffrée (SQLCipher), les fichiers aussi (Fernet),
et l'IA tourne en local via Ollama.

## Fonctionnalités

**Automatiser**
- **Dépôt** : glisser-déposer de PDF, JPG ou PNG.
- **Import automatique** : dossier surveillé (sous-dossiers compris) et pièces jointes d'une boîte
  mail IMAP. Lecture seule : aucun fichier déplacé, aucun message marqué comme lu.
- **Classement** : Impôts, Énergie, Assurance, Banque, Logement, Santé, Social, Travail, Télécom,
  Identité, Véhicule ; type de document détecté (facture, attestation, carte d'identité…).
- **Renommage** : nom normalisé « AAAA-MM-JJ Titre Émetteur.pdf » au téléchargement et à l'export.
- **Doublons** : copie exacte ignorée ; doublon probable (autre scan) mis en vérification.
- **Versions** : une attestation ou une pièce d'identité plus récente remplace l'ancienne
  (marquée, jamais supprimée). Les bulletins de paie sont tous conservés.
- **Extraction** : montant, dates d'émission, d'échéance et de fin de validité, référence,
  émetteur, avec un score de confiance.
- **Échéances et expirations** : paiements, fins de validité avec délai de renouvellement
  (90 jours pour une carte d'identité, 120 pour un passeport…), rappels manuels.
- **Conservation** : durées conseillées (service-public.fr), page « Tri » qui propose les
  documents à trier ; rien n'est supprimé sans vous.

**Aider**
- **En bref** : chaque courrier expliqué simplement, avec ce qu'il faut faire et avant quand.
- **Agent** : répond en citant le document source ; hors IA, répond aux questions
  « combien », « quand », « quand expire », « explique-moi ».
- **Dossiers** : location, prêt immobilier, aide au logement CAF ; pièces trouvées, manquantes
  ou trop anciennes, export ZIP numéroté.
- **Courriers types** : résiliation, réclamation, demande de document, préremplis.
- **Abonnements** : factures récurrentes regroupées, rythme, estimation annuelle, alerte en cas
  de hausse de plus de 10 %.
- **Recherche** plein texte (FTS5) et **export** ZIP rangé par catégorie et par année.

**Rester fiable**
- Un document incomplet, douteux ou en double part dans la file « À vérifier ».
- Supprimer met à la corbeille ; l'effacement définitif demande une confirmation explicite.
- **Historique** lisible de tout ce que Binder, l'agent et vous avez fait, par document.

## Architecture

```
backend/   Python 3.12, FastAPI, SQLModel sur SQLCipher, PyMuPDF, Ollama
  src/binder/
    services/text.py     lecture PDF (PyMuPDF), OCR des scans (docTR ou Tesseract si installés)
    services/rules.py    classement et extraction par règles
    services/llm.py      client Ollama : extraction en JSON structuré, appels d'outils
    services/ingest.py   pipeline : stockage chiffré → lecture → extraction → échéances → index
    agent/               outils + boucle d'agent maison
    api/routes.py        API REST
frontend/  React, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query
```

L'extraction combine deux moteurs : le modèle local (Qwen) quand il est disponible, et des règles
déterministes qui comblent ses trous et servent de repli. Sans Ollama, l'application reste
entièrement utilisable ; l'agent passe alors par un routeur d'intentions.

## Démarrage

Prérequis : [uv](https://docs.astral.sh/uv/), Node 20 ou plus, et [Ollama](https://ollama.com) (optionnel).

```bash
# Modèle local (recommandé)
ollama pull qwen3.5:9b

# Interface (compilée dans backend/src/binder/static)
cd frontend && npm install && npm run build

# Serveur
cd ../backend && uv sync
uv run binder --seed      # optionnel : documents de démonstration
uv run binder             # http://127.0.0.1:8765
uv run --extra desktop binder --desktop   # fenêtre native (pywebview)
```

### Application de bureau (Linux, Windows, macOS)

Binder tourne sur les trois systèmes. La fenêtre utilise le moteur web du système sous Windows
(Edge WebView2, présent par défaut sur Windows 10 et 11) et macOS (WebKit), Qt WebEngine sous Linux.

```bash
python packaging/build.py     # interface + exécutable PyInstaller pour le système courant
```

| Système | Résultat |
|---|---|
| Linux | `packaging/dist/Binder/Binder` ; `./packaging/install-linux.sh` l'ajoute au menu (`--uninstall` pour retirer) |
| Windows | `packaging\dist\Binder\Binder.exe` |
| macOS | `packaging/dist/Binder.app` |

PyInstaller ne compile pas pour un autre système : le workflow GitHub « Application de bureau »
(lancement manuel ou tag `v*`) construit les trois versions et les publie en artefacts.
L'application n'est pas signée : au premier lancement, macOS demande clic droit → Ouvrir et
Windows SmartScreen « Informations complémentaires » → Exécuter quand même.

L'application embarque son serveur sur un port libre de 127.0.0.1 : fermer la fenêtre arrête tout.
Sous Linux, environ 580 Mo, dont 200 Mo pour le moteur web Chromium de Qt. Ollama reste à installer à part.

En développement : `uv run binder` d'un côté, `npm run dev` de l'autre (http://localhost:5173,
les appels `/api` sont relayés vers le backend).

### Configuration

Par variables d'environnement, ou dans un fichier `backend/.env` :

| Variable | Défaut | Rôle |
|---|---|---|
| `BINDER_DATA_DIR` | voir ci-dessous | base, fichiers chiffrés, clé |
| `BINDER_DB_KEY` | générée dans `DATA_DIR/key` | secret maître du chiffrement |
| `BINDER_LLM_MODEL` | `qwen3.5:9b` | modèle Ollama |
| `BINDER_LLM_ENABLED` | `true` | `false` pour n'utiliser que les règles |
| `BINDER_OLLAMA_URL` | `http://localhost:11434` | |
| `BINDER_PORT` | `8765` | |
| `BINDER_AUTO_IMPORT` | `true` | `false` pour couper l'import automatique en tâche de fond |

Dossier de données par défaut : `~/.local/share/binder` (Linux, ou `$XDG_DATA_HOME/binder`),
`~/Library/Application Support/Binder` (macOS), `%LOCALAPPDATA%\Binder` (Windows).

> ⚠️ Perdre la clé, c'est perdre l'accès aux données. Sauvegardez `DATA_DIR/key`.

### OCR

Les PDF avec du texte sont lus directement. Pour les photos et les scans, installez un moteur OCR :
`uv pip install "python-doctr[torch]"` (recommandé) ou `pytesseract` avec `tesseract-ocr-fra`.
Sans OCR, une photo est importée mais part en vérification.

## Qualité

```bash
cd backend
uv run pytest               # API, chiffrement au repos, extraction, agent
uv run ruff check . && uv run mypy src
uv run python scripts/evaluate.py          # précision des règles
uv run python scripts/evaluate.py --llm    # règles + modèle local
```

L'évaluation porte pour l'instant sur 12 documents fictifs générés par `binder/samples.py`.
Les règles ont été mises au point sur ces mêmes documents, donc leur score n'est pas une mesure
de généralisation. Le jeu de 100 documents annotés reste à constituer.

## Feuille de route

- Jeu d'évaluation de 100 documents, comparaison modèles locaux et API
- Recherche sémantique (sqlite-vec, nomic-embed-text)
- Notifications système pour les échéances et les hausses
- Installeurs signés Windows (MSI) et macOS (DMG notarisé)
- Clé protégée par le trousseau du système ou une phrase de passe
