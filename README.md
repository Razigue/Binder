# Binder

Coffre-fort administratif intelligent, **100 % local**.

Vous déposez vos papiers (PDF, photos). Binder les classe, extrait les informations clés
(montant, dates, référence, émetteur), suit les échéances et répond à vos questions.
Rien ne quitte votre machine : la base est chiffrée (SQLCipher), les fichiers aussi (Fernet),
et l'IA tourne en local via Ollama.

## Fonctionnalités (V1)

- **Dépôt** : glisser-déposer de PDF, JPG ou PNG, avec détection des doublons.
- **Classement** : Impôts, Énergie, Assurance, Banque, Logement, Santé, Social, Travail, Télécom.
- **Extraction** : montant, date d'émission, échéance, référence, émetteur, avec un score de confiance.
  Un document incomplet ou douteux part dans la file « À vérifier », et vous pouvez corriger puis valider.
- **Échéances** : déduites des documents, frise du mois, rappels manuels, marquage « réglée ».
- **Recherche** plein texte (FTS5), insensible aux accents et aux mots partiels.
- **Agent** : « Quels documents arrivent bientôt ? », « Trouve mes factures EDF »,
  « Rappelle-moi de payer la cantine le 12/11/2026 », « Exporte mon dossier impôts ».
- **Export** d'un dossier en ZIP (documents déchiffrés et `index.json`).

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

### Application de bureau (Linux)

```bash
./packaging/build-app.sh      # interface + exécutable PyInstaller (Qt WebEngine)
./packaging/install-linux.sh  # installe dans ~/.local/opt/binder + entrée « Binder » du menu
./packaging/install-linux.sh --uninstall
```

L'application embarque son serveur sur un port libre de 127.0.0.1 : fermer la fenêtre arrête tout.
Environ 580 Mo, dont 200 Mo pour le moteur web Chromium de Qt. Ollama reste à installer à part.

En développement : `uv run binder` d'un côté, `npm run dev` de l'autre (http://localhost:5173,
les appels `/api` sont relayés vers le backend).

### Configuration

Par variables d'environnement, ou dans un fichier `backend/.env` :

| Variable | Défaut | Rôle |
|---|---|---|
| `BINDER_DATA_DIR` | `~/.local/share/binder` | base, fichiers chiffrés, clé |
| `BINDER_DB_KEY` | générée dans `DATA_DIR/key` | secret maître du chiffrement |
| `BINDER_LLM_MODEL` | `qwen3.5:9b` | modèle Ollama |
| `BINDER_LLM_ENABLED` | `true` | `false` pour n'utiliser que les règles |
| `BINDER_OLLAMA_URL` | `http://localhost:11434` | |
| `BINDER_PORT` | `8765` | |

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
- Rappels planifiés (APScheduler) et notifications
- Paquets Windows et macOS
- Clé protégée par le trousseau du système ou une phrase de passe
