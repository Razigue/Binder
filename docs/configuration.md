# Configuration

Through environment variables, or in a `backend/.env` file:

| Variable | Default | Purpose |
|---|---|---|
| `BINDER_DATA_DIR` | see below | database, encrypted files, key |
| `BINDER_DB_KEY` | generated in `DATA_DIR/key` | encryption master secret |
| `BINDER_LLM_MODEL` | `qwen3.5:9b` | default Ollama model (the choice made in Settings wins) |
| `BINDER_LLM_ENABLED` | `true` | `false` to use the rules only |
| `BINDER_LLM_CONTEXT` | `16384` | context window asked of Ollama (its own default, 4096, cuts agent conversations) |
| `BINDER_LLM_KEEP_ALIVE` | `30m` | how long Ollama keeps the model loaded after a request |
| `BINDER_LLM_VISION` | `true` | show scans, photos and pages to the model when it reads images |
| `BINDER_LLM_THINK` | `false` | let the agent reason before each step (slower) |
| `BINDER_EMBED_MODEL` | `qwen3-embedding:0.6b` | embedding model for semantic search (used when installed) |
| `BINDER_OLLAMA_URL` | `http://localhost:11434` | |
| `BINDER_PORT` | `8765` | |
| `BINDER_AUTO_IMPORT` | `true` | `false` to turn off background automatic import |
| `BINDER_AUTO_SETUP` | `true` | install/start Ollama and download the model suited to the machine at launch |
| `BINDER_OLLAMA_RELEASE_URL` | GitHub API, Ollama's latest release | where Ollama is downloaded from (checksum verified) |
| `BINDER_NOTIFICATIONS` | `true` | system notifications (urgent deadlines, anomalies, mail imports, weekly briefing) |
| `BINDER_AUTO_BACKUP` | `true` | daily encrypted backup when something changed |
| `BINDER_BACKUP_DIR` | `Documents/Binder backups` | backup folder (`DATA_DIR/backups` without a Documents folder) |
| `BINDER_AUTO_UPDATE` | `true` | `false` not to update the application at launch |
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

`services/setup.py` runs at launch: if Ollama does not answer on a local `BINDER_OLLAMA_URL`, it
uses an installed Ollama (PATH, usual locations) or downloads Ollama's own release archive for the
system into `DATA_DIR/ollama` (no administrator rights; `.tar.zst` on Linux, `.tgz` on macOS,
`.zip` on Windows; SHA-256 from the release), starts `ollama serve` for the session (log:
`DATA_DIR/ollama.log`) and stops it at exit. It then downloads the chat model that fits the
machine (memory, NVIDIA card through `nvidia-smi`, free disk) and the embedding model.
`GET /api/setup` reports the progress shown on Today. These downloads and the update check are
the only outbound traffic; nothing about the documents leaves the machine.

## Backups

`services/backup.py`: an archive (`.binderbackup`, a ZIP) holds the database exported with
`sqlcipher_export` (same key), the Fernet-encrypted files and the master secret wrapped with the
recovery code (scrypt, then Fernet). The code (24 characters) is shown in the Today feed until the
user confirms it, then erased. `POST /api/backup/restore` (file + code) only accepts an empty
library and refuses when `BINDER_DB_KEY` is set.

## Notifications

`services/notify.py` uses the system's own tools: `notify-send` (Linux, libnotify), `osascript`
(macOS) and a PowerShell toast (Windows). Each alert is sent once (keys stored in the database).
