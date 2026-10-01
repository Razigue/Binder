# Desktop builds and releases

## Desktop application (Linux, Windows, macOS)

The window uses the system web engine on Windows (Edge WebView2, installed by default on Windows 10
and 11) and macOS (WebKit), Qt WebEngine on Linux.

```bash
python packaging/build.py     # interface + PyInstaller executable for the current system
```

| System | Output |
|---|---|
| Linux | `packaging/dist/Binder/Binder`; `./packaging/install-linux.sh` adds it to the menu (`--uninstall` to remove it) |
| Windows | `packaging\dist\Binder\Binder.exe` |
| macOS | `packaging/dist/Binder.app` |

PyInstaller does not cross-compile: CI builds the three versions. The application is not signed.
It embeds its server on a free port of 127.0.0.1: closing the window stops everything. On Linux,
about 580 MB, of which 200 MB is Qt's Chromium web engine. Ollama has to be installed separately.

## CI and releases

CI (`.github/workflows/ci.yml`) runs on every push and every pull request: lint, type checking,
tests on Linux, Windows and macOS, evaluation, interface build.

To publish, push a tag: `git tag v1.2.0 && git push origin v1.2.0`. The "Release" workflow reruns
the whole CI, builds the three applications with the tag's version, then creates the GitHub
release (archives, `SHA256SUMS.txt`, generated notes). A tag with a suffix (`v1.3.0-beta.1`) gives
a pre-release. Run manually, the workflow builds the archives without publishing anything.

## Automatic update

At launch, the desktop application shows a splash screen and checks the latest release. If it is
newer, Binder downloads the archive for its system, verifies its SHA-256, extracts it next to the
installation, replaces itself and restarts. Offline or on failure, Binder starts normally. The
installation folder must be writable by the user. Log: `DATA_DIR/binder.log`.
