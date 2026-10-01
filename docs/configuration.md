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
