# Desktop builds and releases

## Desktop application (Linux, Windows, macOS)

The window uses the system web engine on Windows (Edge WebView2, installed by default on Windows 10
and 11) and macOS (WebKit), Qt WebEngine on Linux.

```bash
python packaging/build.py     # interface + PyInstaller executable for the current system
python packaging/build.py --version 1.2.0 --installer   # + Velopack installer (needs vpk)
```

| System | Output | Installer (`packaging/releases/`) |
|---|---|---|
| Linux | `packaging/dist/Binder/Binder`; `./packaging/install-linux.sh` adds it to the menu (`--uninstall` to remove it) | `.AppImage` |
| Windows | `packaging\dist\Binder\Binder.exe` | `BinderApp-windows-Setup.exe` |
| macOS | `packaging/dist/Binder.app` | `.pkg` |

PyInstaller does not cross-compile: CI builds the three versions. It embeds its server on a free
port of 127.0.0.1: closing the window stops everything. On Linux, about 580 MB, of which 200 MB is
Qt's Chromium web engine. Ollama is not bundled (about 1.5 GB with its GPU libraries): Binder
downloads a pinned version at first launch and runs it itself (see
[configuration](configuration.md#local-ai-setup)).

## Installer

`--installer` runs [Velopack](https://velopack.io) (`dotnet tool install -g vpk`, same version as
the `velopack` Python package) on the PyInstaller output:

- **Windows**: `Setup.exe` installs for the current user in `%LocalAppData%\BinderApp`, with no
  wizard, no UAC prompt, Start menu and desktop shortcuts, then starts Binder. Uninstall from
  Settings > Apps removes that folder only.
- **macOS**: a `.pkg`. **Linux**: an AppImage.
- `--noPortable` is passed only on Windows and macOS: Linux's `vpk pack` does not accept
  it, since the AppImage is its portable package. The workflow also creates the portable
  archives used by older installations.
- The package id is `BinderApp`, not `Binder`: on Windows the install folder is
  `%LocalAppData%\<id>`, and `%LocalAppData%\Binder` is the data folder, which uninstalling would
  delete.
- Each system has its own channel (`windows`, `macos`, `linux`), part of every file name, so the
  three sets of files fit in one GitHub release.
- `packaging/binder_app.py` calls `velopack.App().run()` first: it handles the installer's hooks
  (`--veloapp-install`, …) and exits, and does nothing for a normal or portable launch.

Signing: `vpk` signs when its `VPK_*` variables are set (see the comment at the top of
`release.yml`): Azure Trusted Signing on Windows, Developer ID and notarization on macOS
(`packaging/entitlements.plist` for the hardened runtime). Unsigned builds work, but SmartScreen
and Gatekeeper warn at first launch.

## CI and releases

CI (`.github/workflows/ci.yml`) runs on every push and every pull request: lint, type checking,
tests on Linux, Windows and macOS, evaluation, interface build.

To publish, push a tag: `git tag v1.2.0 && git push origin v1.2.0`. The "Release" workflow reruns
the whole CI, then on each system downloads the previous installer release (for delta packages),
builds the application and its installer with the tag's version, and creates the GitHub release:
installers, update packages and feeds (`releases.<channel>.json`), portable archives,
`SHA256SUMS.txt`, generated notes. A tag with a suffix (`v1.3.0-beta.1`) gives a pre-release.
Run manually, the workflow builds everything (version `0.0.0-dev.<run>`) without publishing.

## Automatic update

At launch, the desktop application shows a splash screen and checks the latest release. Offline
or on failure, Binder starts normally. Log: `DATA_DIR/binder.log`.

- **Installed** (`updater.installed()` finds Velopack's installation): Velopack reads the feed of
  its channel, downloads the delta packages (or the full one), verifies them, and applies them
  once Binder has exited, then restarts it.
- **Portable archive** (and versions published before the installer): Binder downloads the
  archive for its system, verifies its SHA-256, extracts it next to the installation, replaces
  itself and restarts. The installation folder must be writable by the user. The archives keep
  their names (`updater.ASSETS`) so these copies keep updating.
