# Configuration

Through environment variables, or in a `backend/.env` file:

| Variable | Default | Purpose |
|---|---|---|
| `BINDER_DATA_DIR` | see below | database, encrypted files, key |
| `BINDER_DB_KEY` | generated in `DATA_DIR/key` | encryption master secret |
| `BINDER_LLM_MODEL` | `qwen3.5:9b` | default Ollama model (the choice made in Settings wins) |
| `BINDER_LLM_ENABLED` | `true` | `false`: no model at all, the rules read every document (tests, demo on a modest machine; they are tuned on the demo documents only). With `true`, real documents imported before the model is ready wait for it |
| `BINDER_LLM_CONTEXT` | `16384` | context window asked of Ollama (its own default, 4096, cuts agent conversations) |
| `BINDER_LLM_KEEP_ALIVE` | `30m` | how long Ollama keeps the model loaded after a request |
| `BINDER_LLM_VISION` | `true` | show scans, photos and pages to the model when it reads images |
| `BINDER_LLM_THINK` | `false` | let the agent reason before each step (slower) |
| `BINDER_WEB_SEARCH` | `true` | let the agent search the web for general facts (queries with personal data are refused) |
| `BINDER_WEB_SEARCH_URL` | `https://html.duckduckgo.com/html/` | search page queried |
| `BINDER_EMBED_MODEL` | `qwen3-embedding:0.6b` | embedding model for semantic search (used when installed) |
| `BINDER_OLLAMA_URL` | Binder's own Ollama, on a free port | set it to use an Ollama you run yourself |
| `BINDER_PORT` | `8765` | |
| `BINDER_AUTO_IMPORT` | `true` | `false` to turn off background automatic import |
| `BINDER_AUTO_SETUP` | `true` | install/start Ollama and download the model suited to the machine at launch |
| `BINDER_OLLAMA_DOWNLOAD_URL` | Ollama's GitHub release downloads | base URL of the pinned Ollama archives (checksums in `services/setup.py`) |
| `BINDER_NOTIFICATIONS` | `true` | system notifications (urgent deadlines, anomalies, mail imports, weekly briefing) |
| `BINDER_AUTO_BACKUP` | `true` | daily encrypted backup when something changed |
| `BINDER_BACKUP_DIR` | `Documents/Binder backups` | backup folder (`DATA_DIR/backups` without a Documents folder) |
| `BINDER_AUTO_UPDATE` | `true` | `false` not to update the application at launch |
| `BINDER_UPDATE_REPO` | `https://github.com/Razigue/Binder` | releases read by the installed application (Velopack) |
| `BINDER_UPDATE_URL` | GitHub API, latest release | update source |
| `BINDER_LOCALE` | detected from the system | system locale override, e.g. `fr_FR` or `en_GB` |

Default data folder: `~/.local/share/binder` (Linux, or `$XDG_DATA_HOME/binder`),
`~/Library/Application Support/Binder` (macOS), `%LOCALAPPDATA%\Binder` (Windows).

> ⚠️ Losing the key means losing access to your data. Back up `DATA_DIR/key`.

## OCR

PDFs with text are read directly. Photos and scans go through RapidOCR (PP-OCRv6 on ONNX
Runtime), a regular dependency: its models ship inside the wheel and the desktop build, nothing
is downloaded at runtime. docTR or Tesseract are used instead only if RapidOCR cannot be
imported. With a vision model (Qwen 3.5), the pages of a scan are also shown to the model, which
reads what OCR misses; a page OCR cannot read at all is transcribed by the model.

## Local AI setup

`services/setup.py` runs at launch. Unless `BINDER_OLLAMA_URL` is set, Binder runs its own Ollama,
which the user never has to know about:

- **Its own server**: `ollama serve` on a free loopback port drawn at each launch (never 11434,
  so an Ollama the user runs is neither used nor disturbed), hidden, log in
  `DATA_DIR/ollama.log`, stopped at exit.
- **Nothing left running**: on Windows, Ollama and its runners are in a job object that Windows
  ends with Binder's process, crash included; on Linux and macOS, the next launch stops the
  server a crashed session left (`DATA_DIR/ollama.pid`, checked to be an `ollama serve`).
- **Its own models**: `OLLAMA_MODELS=DATA_DIR/models`. On first use, the models the user's
  Ollama already has (`~/.ollama/models` or `OLLAMA_MODELS`) are hard-linked there: no download,
  no extra disk space. When links are impossible (another disk), those models are used where they
  are. A model location set in the Ollama desktop app's settings is not detected.
- **A pinned version**: `OLLAMA_VERSION` and the SHA-256 of each archive are written in the code
  (`.tar.zst` on Linux, `.tgz` on macOS, `.zip` on Windows, about 1.5 GB with the GPU
  libraries). Installed in `DATA_DIR/ollama` without administrator rights. On the first launch,
  an Ollama already on the machine (PATH, usual locations) is started at once if there is one,
  and the pinned version is downloaded in the background into `DATA_DIR/ollama.next`, which takes
  over at the next launch. Upgrading Ollama: change `OLLAMA_VERSION` and the checksums (from the
  release's `sha256sum.txt`).

With `BINDER_OLLAMA_URL` set, that server is used as it is (started if local and not answering,
with the user's own models). Binder then downloads the chat model that fits the machine (memory,
NVIDIA card through `nvidia-smi`, free disk) and the embedding model. `GET /api/setup` reports
the progress shown on Today. These downloads and the update check are the only outbound traffic;
nothing about the documents leaves the machine.

## Backups

`services/backup.py`: an archive (`.binderbackup`, a ZIP) holds the database exported with
`sqlcipher_export` (same key), the Fernet-encrypted files and the master secret wrapped with the
recovery code (scrypt, then Fernet). The code (24 characters) is shown in Settings until the user
confirms it (`POST /api/backup/confirm`), then erased; `POST /api/backup/code` makes a new one.
`DELETE /api/demo` permanently removes the demo documents (batch `demo-…`) and their reminders
and letters. `POST /api/backup/restore` (file + code) only accepts an empty
library and refuses when `BINDER_DB_KEY` is set.

## Notifications

`services/notify.py` uses the system's own tools: `notify-send` (Linux, libnotify), `osascript`
(macOS) and a PowerShell toast (Windows). Each alert is sent once (keys stored in the database).
