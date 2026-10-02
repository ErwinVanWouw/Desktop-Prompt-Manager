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
pyinstaller --onefile --noupx --noconsole --name "DesktopPromptManager" --version-file=version_info.txt --icon="logo.ico" --add-data "logo.png;." --add-data "README.md;." --hidden-import pystray._win32 --collect-submodules PIL --collect-submodules pynput desktop_prompt_manager.py
```

What the flags do:

- `--onefile --noconsole` – one self-contained windowed `.exe`, no console.
- `--noupx` – skip UPX compression (fewer antivirus false positives).
- `--icon="logo.ico"` – the executable's file icon (regenerate from `logo.png`
  with `Image.open('logo.png').save('logo.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])`).
- `--version-file=version_info.txt` – version/author metadata shown in the
  file's Properties. Keep its version numbers in sync with `APP_VERSION`.
- `--add-data "logo.png;." --add-data "README.md;."` – `logo.png` is the
  tray/window icon and `README.md` powers the in-app Help, so both are bundled.
- `--hidden-import pystray._win32 --collect-submodules PIL --collect-submodules pynput`
  – make sure the tray, imaging and global-hotkey backends are included
  (PyInstaller can otherwise miss them, causing a silent startup crash).

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
