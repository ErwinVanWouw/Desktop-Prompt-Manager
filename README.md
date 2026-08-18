# Desktop Prompt Manager for Translators

A local, cross-platform tray app that inserts up to **10 custom prompts** into
any focused application — Claude Desktop, ChatGPT Desktop, or anything else —
using global keyboard shortcuts. It is the desktop counterpart of the original
browser extension: same prompts, same defaults, same shortcut scheme, but it
works outside the browser.

## Shortcuts

Default scheme (each shortcut is **customizable** in Settings):

| Shortcut        | Prompt     |
| --------------- | ---------- |
| `Ctrl+Shift+1`  | Prompt 1   |
| …               | …          |
| `Ctrl+Shift+9`  | Prompt 9   |
| `Ctrl+Shift+0`  | Prompt 10  |

In Settings each prompt has two dropdowns — a modifier preset (Ctrl+Shift,
Ctrl+Alt, Alt, …) and a key (0–9, A–Z, F1–F12) — so you can reassign any
shortcut. Changes take effect immediately on Save; duplicates are flagged.

On macOS the trigger is still `Ctrl+Shift+…`; the paste is sent as `Cmd+V`.

## How it works

On a hotkey the app builds the text to insert, selects the existing input
(Ctrl+A / Cmd+A) and simulates a paste into the focused window. Because it
selects first, a new prompt **replaces** whatever is in the field — so picking
the wrong shortcut just overwrites it, no manual deleting needed. No per-site
DOM selectors are needed, so it works in any text field — desktop LLM apps
included.

### Instruct in one action (append copied text)

Because a desktop app has full clipboard access (unlike the browser extension),
you can instruct in a single keystroke:

1. Copy a snippet of text somewhere (Ctrl+C).
2. Focus the AI input and press, say, `Ctrl+Shift+3`.
3. The app inserts `Translate: <your copied text>` in one go.

It reads your copied text, prepends the prompt, pastes the combination, and then
restores your original clipboard so repeated triggers stay clean. Turn this off
with the **"Append copied text after the prompt"** checkbox in Settings if you
ever want the prompt on its own.

### Password safety net

Because the one-action feature pastes whatever you last copied, the app can warn
you if that copied text looks like a **password, API key or token** (mixed
letters/digits/symbols, camelCase, no spaces). You get a confirm dialog before
it is pasted; sentences, URLs and e-mail addresses are never flagged. Toggle it
with the **"Warn before pasting text that looks like a password"** checkbox in
Settings.

## Help window

Right-click the tray icon and choose **Help** (or click **Help** in Settings) to
open a window that shows this guide inside the app — a quick reference without
leaving your desktop.

## About & update check

The tray menu's **About** entry shows the app name, version, a short
description, the author (Black Kite) and the license (GNU General Public License
v3). Its footer has a **Check for updates** button.

The update check works like this: it downloads a plain-text file that contains
only the latest version number and compares it to the running version. If the
remote version is newer, it offers to open the GitHub download page. Configure
it near the top of `desktop_prompt_manager.py`:

- `APP_VERSION` — the version this build reports (bump it on each release).
- `VERSION_CHECK_URL` — a URL to a text file containing just the latest version,
  e.g. a raw `VERSION` file in your GitHub repo (`1.2.0` on one line).
- `GITHUB_URL` — where users are sent to download a newer version.

To publish a new release: update the code, bump `APP_VERSION`, and set the
remote `VERSION` file to the same number.

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
> ("unknown publisher"). Click *More info → Run anyway*. Removing this warning
> requires a paid code-signing certificate.

## Platform notes

- **macOS** requires granting the app *Accessibility* permission
  (System Settings → Privacy & Security → Accessibility) so it may simulate
  keystrokes.
- After the password-confirmation dialog, the app hands keyboard focus back to
  the target app before pasting. This focus-restore is implemented for Windows;
  on macOS focus usually returns to the previous app on its own, but if a paste
  ever fails to land after confirming, click the input field once and retry.
- **Linux** global hotkeys work under X11; Wayland restricts key simulation and
  may not be supported.
