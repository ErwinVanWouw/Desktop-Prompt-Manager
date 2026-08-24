# Development & releases

Maintainer notes for running from source, building a shareable executable and
publishing updates. End-user documentation lives in [README.md](README.md)
(which also powers the in-app Help).

## Run from source

```bash
pip install -r requirements.txt
python desktop_prompt_manager.py
```

A tray icon appears. Right-click it for **Settings** (edit the 10 prompts) and
**Quit**. Prompts are stored in:

- Windows: `%APPDATA%\DesktopPromptManager\prompts.json`
- macOS:   `~/Library/Application Support/DesktopPromptManager/prompts.json`
- Linux:   `~/.config/DesktopPromptManager/prompts.json`

## Build a shareable .exe (Windows)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "DesktopPromptManager" --add-data "logo.png;." --add-data "README.md;." desktop_prompt_manager.py
```

(on macOS/Linux use `:` instead of `;` in `--add-data`, e.g. `"logo.png:."`.)

`logo.png` is used for the tray/window icon and `README.md` powers the in-app
**Help** window, so both are bundled into the executable.

The result is `dist/DesktopPromptManager.exe`. Colleagues can run it directly.

> **Note:** an unsigned `.exe` may trigger a Windows SmartScreen warning
> ("unknown publisher"). Click *More info -> Run anyway*. Removing this warning
> requires a paid code-signing certificate.

## Update check

The **Check for updates** button downloads a plain-text file that contains only
the latest version number and compares it to the running version. If the remote
version is newer, it offers to open the GitHub download page. Configure it near
the top of `desktop_prompt_manager.py`:

- `APP_VERSION` – the version this build reports (bump it on each release).
- `VERSION_CHECK_URL` – a URL to a text file containing just the latest version,
  e.g. a raw `version.txt` in your GitHub repo (`1.2.0` on one line).
- `GITHUB_URL` – where users are sent to download a newer version.

To publish a new release: update the code, bump `APP_VERSION`, rebuild the
`.exe`, and set the remote `version.txt` to the same number.
