# Desktop Prompt Manager for Translators

A local, cross-platform tray app that inserts up to **10 custom prompts** into
any focused application using global keyboard shortcuts. It is the desktop counterpart
of the original browser extension.

## Shortcuts

The default shortcut combinations are Ctrl+Shift+F1-F10 but these can be customized.
Function keys are default because they rarely clash with the target app's
own shortcuts. In Settings each prompt has two
dropdowns – a modifier preset (Ctrl+Shift, Ctrl+Alt, Alt, …) and a key
(0–9, F1–F12, A–Z) – so you can reassign any shortcut.

On macOS the trigger is still `Ctrl+Shift+…`; the paste is sent as `Cmd+V`.

## How it works

On a hotkey the app builds the text to insert, selects the existing input
(Ctrl+A / Cmd+A) and simulates a paste into the focused window. Because it
selects first, a new prompt **replaces** whatever is in the field – so picking
the wrong shortcut just overwrites it. No per-site DOM selectors are needed,
so it works in any text field – desktop LLM apps included.

### Instruct in one action (append copied text)

Because a desktop app has full clipboard access (unlike the browser extension),
you can instruct in a single keystroke:

1. Copy a snippet of text somewhere (Ctrl+C).
2. Focus the AI input and press, say, `Ctrl+Shift+F1`.
3. The app inserts `Rephrase: <your copied text>` in one go.

It reads your copied text, prepends the trigger prompt, pastes the combination, and then
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

## Companion system prompt

The short trigger prompts are only the *cue* – keep the detailed instructions in
your LLM's **system prompt**.
That keeps each message short and cache-friendly instead of
resending a full prompt every time. See
[`example-system-prompt.md`](example-system-prompt.md) for a worked example (a
translator's English > Dutch setup) to adapt to your own workflow.

## Send to a specific app (target mode)

By default a prompt is pasted into **whatever window is focused** – the app
works OS-wide. Optionally you can route prompts to **one fixed app** instead:

1. In Settings, tick **"Send prompts to a specific app instead of the focused window"**
   and choose the app in one of two ways:
   - **Pick installed app…** – a searchable list of installed apps, including
     **Microsoft Store apps** such as Claude Desktop (matched and launched by
     its app id, so store-app updates don't break it).
   - **Browse .exe…** – point directly at a program's `.exe` (for standalone,
     non-store installs).
2. Now, while translating: select a snippet in your CAT tool and press a
   shortcut (e.g. `Ctrl+Shift+F1`).
3. The app copies your selection, brings the target app to the front (launching
   it first if it isn't running), and pastes `Rephrase: <your selection>` into
   it – all in one keystroke. Your original clipboard is restored afterwards.

The selection is only picked up at the moment you press the shortcut, so nothing
is copied behind your back. This mode is **Windows only**; with it off the app
behaves OS-wide as before.

## Help window

Right-click the tray icon and choose **Help** (or click **Help** in Settings) to
open a window that shows this guide inside the app – a quick reference without
leaving your desktop.

## About & update check

The tray menu's **About** entry shows the app name, version, a short
description, the author and the license. Its footer has a **Check for updates** button.

## Platform notes

- **macOS** requires granting the app *Accessibility* permission
  (System Settings → Privacy & Security → Accessibility) so it may simulate
  keystrokes.
- **Linux** global hotkeys work under X11; Wayland restricts key simulation and
  may not be supported.

## Building from source

Developers: see [DEVELOPMENT.md](DEVELOPMENT.md) for running from source, building the executable and publishing releases.
