"""
Desktop Prompt Manager
----------------------
A local, cross-platform tray app that inserts up to 10 custom prompts into any
focused application (Claude Desktop, ChatGPT Desktop, or anything else) using
global keyboard shortcuts.

Default trigger scheme (each shortcut is customizable in Settings):
    Ctrl+Shift+F1 .. Ctrl+Shift+F10  -> prompt 1 .. 10

How it works: on a hotkey it copies the stored prompt to the clipboard and
simulates a paste (Ctrl+V, or Cmd+V on macOS) into whatever window is focused.
This mirrors the behaviour of the original browser extension without needing
any per-site DOM selectors.

Extras beyond the extension:
  * one-action instructing – optionally append the text you just copied after
    the prompt, so "copy + shortcut" inserts e.g. "Translate: <copied text>";
  * a password safety net – warns before pasting copied text that looks like a
    password, API key or token.

Dependencies:  pip install pynput pyperclip pystray pillow
"""

import os
import re
import sys
import json
import threading
import time
import webbrowser
import urllib.request
import urllib.error

import tkinter as tk
from tkinter import messagebox, ttk, filedialog

import pyperclip
from pynput import keyboard
import pystray
from PIL import Image, ImageDraw, ImageTk

# --------------------------------------------------------------------------- #
# Configuration / storage
# --------------------------------------------------------------------------- #

APP_NAME = "DesktopPromptManager"
APP_TITLE = "Desktop Prompt Manager for Translators"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Black Kite"
APP_LICENSE = "GNU General Public License v3"
APP_DESCRIPTION = (
    "A local tray app that inserts up to 10 custom prompts into any focused "
    "application – such as Claude Desktop and ChatGPT Desktop – using global "
    "keyboard shortcuts."
)

# --- Update check -----------------------------------------------------------
# SET THESE to your own URLs. VERSION_CHECK_URL must point to a plain-text file
# that contains only the latest version number (e.g. "1.2.0"). GITHUB_URL is
# where users are sent to download a newer version.
VERSION_CHECK_URL = "https://raw.githubusercontent.com/ErwinVanWouw/Desktop-Prompt-Manager/main/version.txt"
GITHUB_URL = "https://github.com/ErwinVanWouw/Desktop-Prompt-Manager"

NUM_PROMPTS = 10  # prompt1 .. prompt10

DEFAULT_PROMPTS = {
    "prompt1": "Rephrase: ",
    "prompt2": "Correct: ",
    "prompt3": "Translate: ",
    "prompt4": "Give 3 equivalents for: ",
    "prompt5": "",
    "prompt6": "",
    "prompt7": "",
    "prompt8": "",
    "prompt9": "",
    "prompt10": "",
}

# Default hotkeys in pynput format. F-keys are used because they rarely clash
# with the target app's own shortcuts (e.g. Claude Desktop).
DEFAULT_SHORTCUTS = {f"prompt{i}": f"<ctrl>+<shift>+<f{i}>" for i in range(1, 11)}

# Modifier presets offered in the Settings dropdown -> pynput tokens.
MODIFIER_PRESETS = {
    "Ctrl+Shift": ["<ctrl>", "<shift>"],
    "Ctrl+Alt": ["<ctrl>", "<alt>"],
    "Ctrl": ["<ctrl>"],
    "Alt+Shift": ["<alt>", "<shift>"],
    "Alt": ["<alt>"],
    "Ctrl+Shift+Alt": ["<ctrl>", "<shift>", "<alt>"],
}

# Keys offered in the Settings dropdown: 0-9, then F1-F12, then A-Z.
# F-keys come right after the digits so they're easy to find near the top of
# the list (they rarely clash with an app's own shortcuts).
KEY_CHOICES = (
    [str(d) for d in range(10)]
    + [f"F{n}" for n in range(1, 13)]
    + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
)


def key_display_to_token(display: str) -> str:
    """'3' -> '3', 'A' -> 'a', 'F1' -> '<f1>' (pynput hotkey token)."""
    if re.fullmatch(r"[Ff]\d{1,2}", display):
        return f"<{display.lower()}>"
    return display.lower()


def key_token_to_display(token: str) -> str:
    """Inverse of key_display_to_token."""
    m = re.fullmatch(r"<(f\d{1,2})>", token)
    if m:
        return m.group(1).upper()
    return token.upper()


def combo_to_parts(combo: str):
    """Split a pynput combo into (modifier tokens set, key token)."""
    tokens = [t.strip() for t in combo.split("+") if t.strip()]
    mods, key = [], ""
    for t in tokens:
        if t in ("<ctrl>", "<shift>", "<alt>", "<cmd>"):
            mods.append(t)
        else:
            key = t
    return mods, key


def combo_to_human(combo: str) -> str:
    """'<ctrl>+<shift>+3' -> 'Ctrl+Shift+3'."""
    mods, key = combo_to_parts(combo)
    names = {"<ctrl>": "Ctrl", "<shift>": "Shift", "<alt>": "Alt", "<cmd>": "Cmd"}
    parts = [names.get(m, m) for m in mods]
    if key:
        parts.append(key_token_to_display(key))
    return "+".join(parts)


def parts_to_combo(mod_tokens, key_token: str) -> str:
    """Build a pynput combo string from modifier tokens and a key token."""
    return "+".join(list(mod_tokens) + [key_token])


def modtokens_to_label(mod_tokens):
    """Find the preset label matching a set of modifier tokens, else None."""
    want = set(mod_tokens)
    for label, toks in MODIFIER_PRESETS.items():
        if set(toks) == want:
            return label
    return None

# Colour scheme mirrored from the original extension's css/styles.css.
COL_BG = "#f5f5f5"       # page background
COL_FG = "#656565"       # grey text
COL_YELLOW = "#ffd401"   # accent (intro box, Save button)
COL_WHITE = "#ffffff"
COL_BORDER = "#dddddd"   # input border
COL_FOCUS = "#667eea"    # input focus border
COL_SEP = "#e0e0e0"      # header separator
COL_INPUT_TEXT = "#000000"
UI_FONT = "Arial"


def config_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, APP_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "prompts.json")


def _read_raw() -> dict:
    """Return the raw JSON dict from disk (prompts + settings), or {}."""
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def load_config() -> dict:
    """Read prompts from disk, falling back to defaults for missing keys."""
    raw = _read_raw()
    prompts = dict(DEFAULT_PROMPTS)
    for key in DEFAULT_PROMPTS:
        if isinstance(raw.get(key), str):
            prompts[key] = raw[key]
    return prompts


def get_append_clipboard() -> bool:
    """Whether copied clipboard text is appended after the prompt (default on)."""
    return bool(_read_raw().get("append_clipboard", True))


def get_password_warning() -> bool:
    """Whether to warn before pasting text that looks like a password (default on)."""
    return bool(_read_raw().get("password_warning", True))


def get_shortcuts() -> dict:
    """Return {prompt_key: pynput combo}, falling back to defaults."""
    raw = _read_raw().get("shortcuts", {})
    shortcuts = dict(DEFAULT_SHORTCUTS)
    if isinstance(raw, dict):
        for key in DEFAULT_SHORTCUTS:
            if isinstance(raw.get(key), str) and raw[key].strip():
                shortcuts[key] = raw[key].strip()
    return shortcuts


def get_send_to_target() -> bool:
    """Whether prompts are sent to a fixed target app instead of the focused one."""
    return bool(_read_raw().get("send_to_target", False))


def stored_target():
    """The stored target app dict regardless of whether target mode is enabled.

    dict keys: kind ("exe"|"appx"), proc (process basename for window matching),
    label (display name), and either path (exe) or aumid (Store app).
    """
    raw = _read_raw()
    kind = raw.get("target_kind", "exe")
    proc = raw.get("target_proc", "") or ""
    label = raw.get("target_label", "") or ""
    if kind == "appx":
        aumid = raw.get("target_aumid", "") or ""
        if not aumid:
            return None
        return {"kind": "appx", "aumid": aumid, "proc": proc,
                "label": label or aumid}
    path = raw.get("target_app_path", "") or ""
    if not path:
        return None
    return {"kind": "exe", "path": path, "proc": proc or os.path.basename(path),
            "label": label or os.path.basename(path)}


def get_target():
    """The active target dict, or None if target mode is disabled/unset."""
    if not _read_raw().get("send_to_target"):
        return None
    return stored_target()


def save_config(prompts: dict, append_clipboard=None, shortcuts=None,
                password_warning=None, send_to_target=None, target=None) -> None:
    """Persist prompts and optional settings, preserving other keys in the file.

    `target` is a dict like get_target() returns (or None to leave unchanged).
    """
    raw = _read_raw()
    raw.update(prompts)
    if append_clipboard is not None:
        raw["append_clipboard"] = bool(append_clipboard)
    if password_warning is not None:
        raw["password_warning"] = bool(password_warning)
    if shortcuts is not None:
        raw["shortcuts"] = shortcuts
    if send_to_target is not None:
        raw["send_to_target"] = bool(send_to_target)
    if target is not None:
        raw["target_kind"] = target.get("kind", "exe")
        raw["target_app_path"] = target.get("path", "")
        raw["target_aumid"] = target.get("aumid", "")
        raw["target_proc"] = target.get("proc", "")
        raw["target_label"] = target.get("label", "")
    os.makedirs(config_dir(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Prompt insertion (clipboard + simulated paste)
# --------------------------------------------------------------------------- #

_kbd = keyboard.Controller()

# Set by the GUI so a background paste can ask the user for confirmation.
# Signature: confirm(masked_preview: str) -> bool. None means "no GUI, allow".
_confirm_hook = None

_URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def set_confirm_hook(func) -> None:
    global _confirm_hook
    _confirm_hook = func


def _get_foreground_window():
    """Handle of the currently focused window (Windows only, else None)."""
    if sys.platform == "win32":
        try:
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            return None
    return None


def _focus_window(hwnd) -> None:
    """Best-effort: return keyboard focus to a window after a dialog stole it.

    Needed because the password-confirmation dialog takes focus away from the
    target app; without this the subsequent paste would go nowhere. Windows
    only – a no-op on other platforms.
    """
    if sys.platform != "win32" or not hwnd:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cur = kernel32.GetCurrentThreadId()
        target = user32.GetWindowThreadProcessId(hwnd, None)
        # Attaching input queues lets us hand foreground back reliably.
        user32.AttachThreadInput(cur, target, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(cur, target, False)
    except Exception:
        pass


# Set by the GUI so a background paste can show an informational message.
_notify_hook = None


def set_notify_hook(func) -> None:
    global _notify_hook
    _notify_hook = func


def _notify(message: str) -> None:
    if _notify_hook is not None:
        _notify_hook(message)


def _find_window_for_exe(exe_path: str):
    """Return a visible, titled top-level window owned by the given exe, or None
    (Windows only)."""
    if sys.platform != "win32" or not exe_path:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        target_name = os.path.basename(exe_path).lower()
        found = []
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        def proc_name(pid):
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(4096)
                size = wintypes.DWORD(len(buf))
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    return os.path.basename(buf.value).lower()
            finally:
                kernel32.CloseHandle(h)
            return ""

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True  # skip tool/hidden windows without a title
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if proc_name(pid.value) == target_name:
                found.append(hwnd)
                return False  # stop enumerating
            return True

        user32.EnumWindows(callback, 0)
        return found[0] if found else None
    except Exception:
        return None


def _run_powershell(script: str, timeout: float = 25.0) -> str:
    """Run a PowerShell snippet without a visible console; return stdout."""
    if sys.platform != "win32":
        return ""
    try:
        import subprocess
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            startupinfo=si, creationflags=0x08000000)  # CREATE_NO_WINDOW
        return out.stdout or ""
    except Exception:
        return ""


def list_start_apps():
    """Return [(name, appid)] of launchable apps (Store + desktop), sorted."""
    out = _run_powershell(
        "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    apps = [(d["Name"], d["AppID"]) for d in data
            if d.get("Name") and d.get("AppID")]
    apps.sort(key=lambda x: x[0].lower())
    return apps


def resolve_appx_exe(aumid: str) -> str:
    """Return the process basename (e.g. 'Claude.exe') for a Store app AUMID."""
    if "!" not in aumid:
        return ""
    pfn, _, appid = aumid.partition("!")
    script = (
        "$p=Get-AppxPackage | Where-Object {$_.PackageFamilyName -eq '%s'} "
        "| Select-Object -First 1;"
        "$a=(Get-AppxPackageManifest $p).Package.Applications.Application "
        "| Where-Object {$_.Id -eq '%s'} | Select-Object -First 1;"
        "[System.IO.Path]::GetFileName($a.Executable)" % (pfn, appid)
    )
    return _run_powershell(script).strip()


def _launch_appx(aumid: str) -> None:
    """Launch a Store (packaged) app by its AppUserModelID via the shell."""
    try:
        import subprocess
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aumid}"])
    except Exception:
        pass


def _activate_target(target: dict, timeout: float = 15.0) -> bool:
    """Bring the target app's window to the foreground, launching it if needed.
    Returns True when a window was focused (Windows only)."""
    if sys.platform != "win32" or not target:
        return False
    proc = target.get("proc", "")
    hwnd = _find_window_for_exe(proc) if proc else None
    if hwnd is None:
        # Not running (or no proc name to match): launch it.
        if target.get("kind") == "appx":
            _launch_appx(target.get("aumid", ""))
        elif target.get("path"):
            try:
                import subprocess
                subprocess.Popen([target["path"]])
            except Exception:
                return False
        else:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.4)
            hwnd = _find_window_for_exe(proc) if proc else None
            if hwnd is not None:
                time.sleep(0.8)  # let it finish loading and focus its input
                break
    if hwnd is None:
        return False
    _focus_window(hwnd)
    time.sleep(0.25)
    return True


def _grab_selection() -> str:
    """Copy the current selection (Ctrl+C) and return it; '' if nothing selected.

    Uses an empty-clipboard sentinel so we only treat text as a selection when
    Ctrl+C actually produced something – i.e. only when the user had text
    selected at the moment the shortcut fired.
    """
    mod = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl
    for key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                keyboard.Key.shift, keyboard.Key.shift_r):
        try:
            _kbd.release(key)
        except Exception:
            pass
    try:
        pyperclip.copy("")
    except Exception:
        pass
    time.sleep(0.05)
    with _kbd.pressed(mod):
        _kbd.press("c")
        _kbd.release("c")
    time.sleep(0.15)
    try:
        sel = pyperclip.paste()
        return sel if isinstance(sel, str) else ""
    except Exception:
        return ""


def looks_like_password(s: str) -> bool:
    """Heuristic: does this single token look like a password/secret/API key?

    Deliberately conservative to avoid flagging normal text: anything with
    whitespace (sentences), URLs and e-mail addresses are never flagged.
    """
    s = s.strip()
    if not s or any(c.isspace() for c in s):
        return False
    if len(s) < 6 or len(s) > 200:
        return False
    if _URL_RE.search(s) or _EMAIL_RE.match(s):
        return False

    has_lower = any(c.islower() for c in s)
    has_upper = any(c.isupper() for c in s)
    has_digit = any(c.isdigit() for c in s)
    has_symbol = any(not c.isalnum() for c in s)
    classes = sum([has_lower, has_upper, has_digit, has_symbol])

    # 3+ character classes -> strong signal (e.g. "Tr0ub4dour&3").
    if classes >= 3:
        return True
    # letters + digits mixed in a longish token -> likely a token/password
    # (e.g. "hunter2Password", camelCase with a number).
    if has_digit and (has_lower or has_upper) and len(s) >= 8:
        return True
    return False


def mask_secret(s: str) -> str:
    """Show enough to recognise it without exposing the whole secret."""
    s = s.strip()
    n = len(s)
    if n <= 4:
        shown = s[:1] + "•" * (n - 1)
    else:
        shown = s[:2] + "•" * min(n - 4, 12) + s[-2:]
    return f"{shown}   ({n} characters)"


def _paste_selected(mod) -> None:
    """Select-all then paste (replacing the field content)."""
    with _kbd.pressed(mod):
        _kbd.press("a")
        _kbd.release("a")
    time.sleep(0.02)
    with _kbd.pressed(mod):
        _kbd.press("v")
        _kbd.release("v")


def _combine(prompt: str, extra: str) -> str:
    """Join a trigger prompt with the appended text, guaranteeing a single
    space between them (e.g. 'Rephrase:' + 'text' -> 'Rephrase: text').

    The prompt is stored stripped, so we can't rely on a trailing space.
    """
    if not extra:
        return prompt
    if prompt and not prompt[-1].isspace():
        return prompt + " " + extra
    return prompt + extra


def _insert_prompt(text: str, append_clipboard: bool = True,
                   password_warning: bool = True, target=None) -> None:
    if not text:
        return

    mod = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl

    # ---- Target-app mode: grab the selection and paste into a fixed app ------
    if target and sys.platform == "win32":
        try:
            saved_clip = pyperclip.paste()
            if not isinstance(saved_clip, str):
                saved_clip = ""
        except Exception:
            saved_clip = ""

        # Auto-copy the current selection (only meaningful if we append it).
        selection = _grab_selection() if append_clipboard else ""

        if append_clipboard and password_warning and looks_like_password(selection):
            if _confirm_hook is not None and not _confirm_hook(mask_secret(selection)):
                try:
                    pyperclip.copy(saved_clip)
                except Exception:
                    pass
                return

        combined = _combine(text, selection) if append_clipboard else text

        if not _activate_target(target):
            _notify("Could not open the target app:\n\n"
                    + (target.get("label") or target.get("path") or
                       target.get("aumid") or "?"))
            try:
                pyperclip.copy(saved_clip)
            except Exception:
                pass
            return

        pyperclip.copy(combined)
        time.sleep(0.05)
        _paste_selected(mod)

        # Restore the user's clipboard.
        time.sleep(0.15)
        try:
            pyperclip.copy(saved_clip)
        except Exception:
            pass
        return

    # ---- OS-wide mode: paste into whatever window is focused -----------------
    # Remember which window is focused now (the target app), before any dialog
    # can steal focus, so we can hand it back before pasting.
    target_hwnd = _get_foreground_window()
    refocus = False

    # Read whatever the user just copied, so we can instruct in one action:
    # e.g. copy a sentence, press Ctrl+Shift+F3, get "Translate: <that sentence>".
    try:
        original = pyperclip.paste()
        if not isinstance(original, str):
            original = ""
    except Exception:
        original = ""

    # If we're about to paste copied clipboard text and it looks like a
    # password/secret, ask the user before it leaves the clipboard.
    if append_clipboard and password_warning and looks_like_password(original):
        if _confirm_hook is not None:
            if not _confirm_hook(mask_secret(original)):
                return  # user declined; clipboard is left untouched
            refocus = True  # the dialog stole focus from the target app

    combined = _combine(text, original) if append_clipboard else text
    pyperclip.copy(combined)
    # Give the clipboard a moment to settle.
    time.sleep(0.03)

    # The hotkey modifiers (Ctrl+Shift) are still physically held when the
    # callback fires. Release them so our simulated shortcuts aren't mangled.
    for key in (
        keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
        keyboard.Key.shift, keyboard.Key.shift_r,
    ):
        try:
            _kbd.release(key)
        except Exception:
            pass

    time.sleep(0.03)

    # If a confirmation dialog was shown, focus moved away from the target app;
    # hand it back before we paste, otherwise the paste goes nowhere.
    if refocus:
        _focus_window(target_hwnd)
        time.sleep(0.15)

    # macOS uses Cmd for both select-all and paste; other platforms use Ctrl.
    mod = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl

    # Select existing content first so a new prompt REPLACES whatever is there
    # (mirrors the original extension's selectAll-then-insert behaviour). This
    # means picking the wrong shortcut simply overwrites it instead of
    # appending.
    with _kbd.pressed(mod):
        _kbd.press("a")
        _kbd.release("a")
    time.sleep(0.02)

    with _kbd.pressed(mod):
        _kbd.press("v")
        _kbd.release("v")

    # Restore the user's original clipboard so repeated triggers stay clean
    # (otherwise the next trigger would append the combined text to itself).
    time.sleep(0.15)
    try:
        pyperclip.copy(original)
    except Exception:
        pass


def trigger(prompt_key: str) -> None:
    """Look up the prompt fresh (so edits apply live) and insert it."""
    prompts = load_config()
    text = prompts.get(prompt_key, "")
    append = get_append_clipboard()
    warn = get_password_warning()
    target = get_target()
    # Run the paste off the listener thread so we never block hotkey handling.
    threading.Thread(target=_insert_prompt, args=(text, append, warn, target),
                     daemon=True).start()


def build_hotkeys() -> keyboard.GlobalHotKeys:
    """Build the global hotkey listener from the user's configured shortcuts."""
    mapping = {}
    for key, combo in get_shortcuts().items():
        if not combo:
            continue
        try:
            keyboard.HotKey.parse(combo)  # validate; skip broken combos
        except ValueError:
            continue
        mapping[combo] = (lambda k=key: trigger(k))
    return keyboard.GlobalHotKeys(mapping)


# --------------------------------------------------------------------------- #
# Settings window (Tkinter)
# --------------------------------------------------------------------------- #

# Intro text mirrored from the original options.html (adapted for 10 prompts
# and the desktop shortcut scheme).
INTRO_PARA_1 = (
    "The first 4 prompts come pre-configured for translators and text editors, "
    "but can be fully customized. Prompts 5 to 10 are empty by default, but you "
    "can customize them as needed. Enter your prompt in the fields below; the "
    "shortcut for each prompt is shown next to it."
)
INTRO_PARA_2 = (
    "By default you trigger each prompt with Ctrl+Shift+F1 to Ctrl+Shift+F10 "
    "(F-keys rarely clash with the app's own shortcuts). You can change each "
    "shortcut with the dropdowns next to it. The shortcuts work in any "
    "application."
)


class SettingsWindow:
    def __init__(self, root: tk.Tk, on_shortcuts_changed=None):
        self.root = root
        self.on_shortcuts_changed = on_shortcuts_changed
        self.win = None
        self.entries = {}
        self.mod_vars = {}   # prompt_key -> StringVar (modifier preset label)
        self.key_vars = {}   # prompt_key -> StringVar (key display)
        self._imgs = []  # keep PhotoImage references alive

    def _logo(self, height: int):
        """Load the app logo scaled to a given pixel height (aspect-preserving)."""
        img = Image.open(resource_path("logo.png"))
        w, h = img.size
        new_w = max(1, int(round(w * height / h)))
        photo = ImageTk.PhotoImage(img.resize((new_w, height), Image.LANCZOS))
        self._imgs.append(photo)
        return photo

    def show(self):
        # Only one settings window at a time.
        if self.win is not None and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            return

        self._imgs = []
        self.entries = {}
        self.mod_vars = {}
        self.key_vars = {}

        self.win = tk.Toplevel(self.root)
        self.win.title(APP_TITLE)
        self.win.configure(bg=COL_BG)
        self.win.resizable(False, True)  # height adjustable; content scrolls
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- Body holds swappable views: settings and (lazily) help ----------
        self.body = tk.Frame(self.win, bg=COL_BG)
        self.body.pack(fill="both", expand=True)
        self.help_content = None

        # ---- Settings view: a vertically scrollable canvas -------------------
        self.settings_content = tk.Frame(self.body, bg=COL_BG)
        self.settings_content.pack(fill="both", expand=True)
        canvas = tk.Canvas(self.settings_content, bg=COL_BG, highlightthickness=0,
                           bd=0)
        vscroll = ttk.Scrollbar(self.settings_content, orient="vertical",
                                command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._settings_canvas = canvas
        self._settings_inner = tk.Frame(canvas, bg=COL_BG)
        inner_id = canvas.create_window((0, 0), window=self._settings_inner,
                                        anchor="nw")
        self._settings_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(inner_id, width=e.width))

        def _on_wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        content = tk.Frame(self._settings_inner, bg=COL_BG)
        content.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(content, text="Settings", bg=COL_BG, fg=COL_FG,
                 font=(UI_FONT, 16, "bold")).pack(anchor="w", pady=(0, 15))

        # Yellow intro box
        intro = tk.Frame(content, bg=COL_YELLOW)
        intro.pack(fill="x", pady=(0, 20))
        intro_inner = tk.Frame(intro, bg=COL_YELLOW)
        intro_inner.pack(fill="x", padx=15, pady=15)
        tk.Label(intro_inner, text="Manage your Prompts", bg=COL_YELLOW, fg=COL_FG,
                 font=(UI_FONT, 13, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(intro_inner, text=INTRO_PARA_1, bg=COL_YELLOW, fg=COL_FG,
                 font=(UI_FONT, 9), justify="left", wraplength=560).pack(
                     anchor="w", pady=(0, 8))
        tk.Label(intro_inner, text=INTRO_PARA_2, bg=COL_YELLOW, fg=COL_FG,
                 font=(UI_FONT, 9), justify="left", wraplength=560).pack(anchor="w")

        # Form: two columns of five prompts
        prompts = load_config()
        shortcuts = get_shortcuts()
        form = tk.Frame(content, bg=COL_BG)
        form.pack(fill="x", pady=(5, 0))
        columns = [
            tk.Frame(form, bg=COL_BG),
            tk.Frame(form, bg=COL_BG),
        ]
        columns[0].pack(side="left", fill="both", expand=True, padx=(0, 15))
        columns[1].pack(side="left", fill="both", expand=True, padx=(15, 0))

        for idx in range(NUM_PROMPTS):
            key = f"prompt{idx + 1}"
            col = columns[idx // 5]

            # Row 1: "Prompt N" label + shortcut dropdowns (modifier + key)
            top = tk.Frame(col, bg=COL_BG)
            top.pack(fill="x", pady=(12, 0))
            tk.Label(top, text=f"Prompt {idx + 1}:", bg=COL_BG, fg=COL_FG,
                     font=(UI_FONT, 9, "bold")).pack(side="left")

            mods, key_token = combo_to_parts(shortcuts.get(key, ""))
            mod_var = tk.StringVar(value=modtokens_to_label(mods) or "Ctrl+Shift")
            key_var = tk.StringVar(value=key_token_to_display(key_token) if key_token
                                   else "0")
            self.mod_vars[key] = mod_var
            self.key_vars[key] = key_var

            key_cb = ttk.Combobox(top, textvariable=key_var, values=KEY_CHOICES,
                                  width=4, height=22, state="readonly")
            key_cb.pack(side="right")
            mod_cb = ttk.Combobox(top, textvariable=mod_var,
                                  values=list(MODIFIER_PRESETS.keys()), width=13,
                                  state="readonly")
            mod_cb.pack(side="right", padx=(0, 4))

            # Row 2: the prompt text entry
            entry = tk.Entry(col, font=(UI_FONT, 10), bg=COL_WHITE,
                             fg=COL_INPUT_TEXT, relief="flat", bd=0,
                             highlightthickness=2, highlightbackground=COL_BORDER,
                             highlightcolor=COL_FOCUS, insertbackground=COL_INPUT_TEXT)
            entry.insert(0, prompts.get(key, ""))
            entry.pack(fill="x", ipady=5, pady=(6, 0))
            self.entries[key] = entry

        # One-action option: append copied clipboard text after the prompt
        self.append_var = tk.BooleanVar(value=get_append_clipboard())
        opt = tk.Frame(content, bg=COL_BG)
        opt.pack(anchor="w", pady=(18, 0))
        tk.Checkbutton(
            opt,
            text="Append copied text after the prompt (instruct in one action)",
            variable=self.append_var, bg=COL_BG, fg=COL_FG, font=(UI_FONT, 9),
            activebackground=COL_BG, activeforeground=COL_FG,
            selectcolor=COL_WHITE, anchor="w",
        ).pack(anchor="w")
        tk.Label(
            opt,
            text=("When on: copy a snippet, press a shortcut, and e.g. "
                  "'Rephrase: ' is inserted with your copied text right after it."),
            bg=COL_BG, fg=COL_FG, font=(UI_FONT, 8), justify="left",
            wraplength=560,
        ).pack(anchor="w", padx=(22, 0))

        # Password-safety option: warn before pasting secret-looking clipboard text
        self.pw_warn_var = tk.BooleanVar(value=get_password_warning())
        pwopt = tk.Frame(content, bg=COL_BG)
        pwopt.pack(anchor="w", pady=(10, 0))
        tk.Checkbutton(
            pwopt,
            text="Warn before pasting text that looks like a password or secret",
            variable=self.pw_warn_var, bg=COL_BG, fg=COL_FG, font=(UI_FONT, 9),
            activebackground=COL_BG, activeforeground=COL_FG,
            selectcolor=COL_WHITE, anchor="w",
        ).pack(anchor="w")
        tk.Label(
            pwopt,
            text=("Safety net for the one-action feature: if your copied text "
                  "looks like a password, API key or token, you'll be asked to "
                  "confirm before it is pasted."),
            bg=COL_BG, fg=COL_FG, font=(UI_FONT, 8), justify="left",
            wraplength=560,
        ).pack(anchor="w", padx=(22, 0))

        # Target-app option: send the prompt to a fixed app instead of the
        # focused window (Windows only).
        self.target_var = tk.BooleanVar(value=get_send_to_target())
        self.target = stored_target()  # dict or None
        tgt = tk.Frame(content, bg=COL_BG)
        tgt.pack(anchor="w", fill="x", pady=(10, 0))
        tk.Checkbutton(
            tgt,
            text="Send prompts to a specific app instead of the focused window",
            variable=self.target_var, bg=COL_BG, fg=COL_FG, font=(UI_FONT, 9),
            activebackground=COL_BG, activeforeground=COL_FG,
            selectcolor=COL_WHITE, anchor="w",
        ).pack(anchor="w")
        tk.Label(
            tgt,
            text=("When on: select text in your CAT tool, press a shortcut, and "
                  "the prompt + selected text is pasted straight into the chosen "
                  "app (it is launched if it isn't already running). Windows only."),
            bg=COL_BG, fg=COL_FG, font=(UI_FONT, 8), justify="left",
            wraplength=560,
        ).pack(anchor="w", padx=(22, 0))
        picker = tk.Frame(tgt, bg=COL_BG)
        picker.pack(anchor="w", fill="x", padx=(22, 0), pady=(6, 0))
        pick = tk.Button(picker, text="Pick installed app…",
                         command=self._pick_installed_app, bg=COL_WHITE, fg=COL_FG,
                         font=(UI_FONT, 9, "bold"), relief="solid", bd=1, padx=14,
                         pady=4, cursor="hand2", activebackground=COL_YELLOW,
                         activeforeground=COL_WHITE)
        pick.pack(side="left")
        self._add_hover(pick, COL_WHITE, COL_FG, COL_YELLOW, COL_WHITE)
        browse = tk.Button(picker, text="Browse .exe…", command=self._browse_target,
                           bg=COL_WHITE, fg=COL_FG, font=(UI_FONT, 9, "bold"),
                           relief="solid", bd=1, padx=14, pady=4, cursor="hand2",
                           activebackground=COL_YELLOW, activeforeground=COL_WHITE)
        browse.pack(side="left", padx=(8, 0))
        self._add_hover(browse, COL_WHITE, COL_FG, COL_YELLOW, COL_WHITE)
        selrow = tk.Frame(tgt, bg=COL_BG)
        selrow.pack(anchor="w", fill="x", padx=(22, 0), pady=(6, 0))
        tk.Label(selrow, text="Selected app:", bg=COL_BG, fg=COL_FG,
                 font=(UI_FONT, 9, "bold")).pack(side="left")
        self.target_label = tk.Label(selrow, text=self._target_label_text(),
                                     bg=COL_BG, fg=COL_FG, font=(UI_FONT, 9))
        self.target_label.pack(side="left", padx=(6, 0))

        # Buttons
        btns = tk.Frame(content, bg=COL_BG)
        btns.pack(anchor="w", pady=(22, 0))
        save = tk.Button(btns, text="Save Prompts", command=self._save,
                         bg=COL_YELLOW, fg=COL_FG, font=(UI_FONT, 10, "bold"),
                         relief="flat", bd=0, padx=22, pady=9, cursor="hand2",
                         activebackground=COL_WHITE, activeforeground=COL_YELLOW)
        save.pack(side="left", padx=(0, 15))
        reset = tk.Button(btns, text="Reset to Defaults", command=self._reset,
                          bg=COL_WHITE, fg=COL_FG, font=(UI_FONT, 10, "bold"),
                          relief="solid", bd=1, padx=22, pady=9, cursor="hand2",
                          activebackground=COL_YELLOW, activeforeground=COL_WHITE)
        reset.pack(side="left")
        self._add_hover(save, COL_YELLOW, COL_FG, COL_WHITE, COL_YELLOW)
        self._add_hover(reset, COL_WHITE, COL_FG, COL_YELLOW, COL_WHITE)
        helpb = tk.Button(btns, text="Help", command=self._enter_help,
                          bg=COL_WHITE, fg=COL_FG, font=(UI_FONT, 10, "bold"),
                          relief="solid", bd=1, padx=22, pady=9, cursor="hand2",
                          activebackground=COL_YELLOW, activeforeground=COL_WHITE)
        helpb.pack(side="left", padx=(15, 0))
        self._add_hover(helpb, COL_WHITE, COL_FG, COL_YELLOW, COL_WHITE)

        # Window footer with Close, matching the Help and About windows. It is
        # hidden while the inline help view is showing (that view has its own
        # "Back to settings" button in the same spot).
        self.footer = tk.Frame(self.win, bg=COL_BG)
        tk.Frame(self.footer, height=1, bg=COL_SEP).pack(fill="x")
        footer_inner = tk.Frame(self.footer, bg=COL_BG)
        footer_inner.pack(fill="x")
        close = tk.Button(footer_inner, text="Close", command=self._on_close,
                          bg=COL_YELLOW, fg=COL_FG, font=(UI_FONT, 10, "bold"),
                          relief="flat", bd=0, padx=22, pady=8, cursor="hand2",
                          activebackground=COL_WHITE, activeforeground=COL_YELLOW)
        close.pack(side="right", padx=20, pady=12)
        self._add_hover(close, COL_YELLOW, COL_FG, COL_WHITE, COL_YELLOW)
        self.footer.pack(side="bottom", fill="x")

        # Size to the content but keep the whole window on screen; the settings
        # area scrolls vertically when the content is taller than the screen.
        self.win.update_idletasks()
        inner_w = self._settings_inner.winfo_reqwidth()
        inner_h = self._settings_inner.winfo_reqheight()
        footer_h = self.footer.winfo_reqheight()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        w = inner_w + 18  # + vertical scrollbar
        max_h = screen_h - 120  # leave room for the taskbar and title bar
        h = min(inner_h + footer_h, max_h)
        x = max(0, (screen_w - w) // 2)
        y = max(0, (screen_h - h) // 2 - 20)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.minsize(w, min(320, h))
        self.win.maxsize(w, h)
        self.win.lift()
        self.win.focus_force()

    # ---- Inline help view (takes over the settings window) --------------- #
    def _enter_help(self):
        if self.help_content is None:
            self.help_content = self._build_help_view(self.body)
        try:
            self._settings_canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.settings_content.pack_forget()
        self.footer.pack_forget()
        self.help_content.pack(fill="both", expand=True)

    def _exit_help(self):
        if self.help_content is not None:
            self.help_content.pack_forget()
        self.settings_content.pack(fill="both", expand=True)
        self.footer.pack(side="bottom", fill="x")

    def _build_help_view(self, parent):
        frame = tk.Frame(parent, bg=COL_BG)

        title = tk.Frame(frame, bg=COL_BG)
        title.pack(fill="x", padx=30, pady=(16, 8))
        tk.Label(title, text="Help", bg=COL_BG, fg=COL_FG,
                 font=(UI_FONT, 16, "bold")).pack(side="left")

        area = tk.Frame(frame, bg=COL_WHITE)
        area.pack(fill="both", expand=True, padx=30)
        scroll = ttk.Scrollbar(area, orient="vertical")
        scroll.pack(side="right", fill="y")
        text = tk.Text(area, wrap="word", bg=COL_WHITE, fg=COL_FG, relief="flat",
                       bd=0, padx=20, pady=16, font=(UI_FONT, 10),
                       yscrollcommand=scroll.set, cursor="arrow", width=1, height=1)
        text.pack(side="left", fill="both", expand=True)
        scroll.config(command=text.yview)
        configure_help_tags(text)
        render_help_markdown(text, load_help_text())

        footer = tk.Frame(frame, bg=COL_BG)
        footer.pack(fill="x", padx=30, pady=12)
        back = tk.Button(footer, text="←  Back to settings",
                         command=self._exit_help, bg=COL_YELLOW, fg=COL_FG,
                         font=(UI_FONT, 10, "bold"), relief="flat", bd=0, padx=20,
                         pady=8, cursor="hand2", activebackground=COL_WHITE,
                         activeforeground=COL_YELLOW)
        back.pack(side="left")
        self._add_hover(back, COL_YELLOW, COL_FG, COL_WHITE, COL_YELLOW)
        return frame

    @staticmethod
    def _add_hover(widget, bg, fg, hover_bg, hover_fg):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover_bg, fg=hover_fg))
        widget.bind("<Leave>", lambda e: widget.configure(bg=bg, fg=fg))

    def _target_label_text(self) -> str:
        if not self.target:
            return "(no app selected)"
        kind = "Store app" if self.target.get("kind") == "appx" else "program"
        return f"{self.target.get('label', '?')}  ({kind})"

    def _browse_target(self):
        path = filedialog.askopenfilename(
            parent=self.win, title="Select the target application",
            filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
        if path:
            self.target = {"kind": "exe", "path": path,
                           "proc": os.path.basename(path),
                           "label": os.path.basename(path)}
            self.target_label.config(text=self._target_label_text())

    def _pick_installed_app(self):
        self.win.config(cursor="watch")
        self.win.update()
        apps = list_start_apps()
        self.win.config(cursor="")
        if not apps:
            messagebox.showwarning(
                "Desktop Prompt Manager",
                "Could not list installed apps. Use “Browse .exe…” instead.",
                parent=self.win)
            return
        choice = self._app_chooser(apps)
        if not choice:
            return
        name, appid = choice
        if "!" in appid:  # packaged / Store app -> AUMID
            self.win.config(cursor="watch")
            self.win.update()
            proc = resolve_appx_exe(appid)
            self.win.config(cursor="")
            self.target = {"kind": "appx", "aumid": appid, "proc": proc,
                           "label": name}
        elif appid.lower().endswith(".exe") and (os.sep in appid or "/" in appid):
            self.target = {"kind": "exe", "path": appid,
                           "proc": os.path.basename(appid), "label": name}
        else:
            messagebox.showinfo(
                "Desktop Prompt Manager",
                f"“{name}” isn't a Store app. Use “Browse .exe…” "
                "to point at its program file instead.", parent=self.win)
            return
        self.target_label.config(text=self._target_label_text())

    def _app_chooser(self, apps):
        """Modal filterable list of installed apps; returns (name, appid) or None."""
        dlg = tk.Toplevel(self.win)
        dlg.title("Pick an installed app")
        dlg.configure(bg=COL_BG)
        dlg.transient(self.win)
        dlg.grab_set()
        result = {"choice": None}

        tk.Label(dlg, text="Type to filter, then choose an app:", bg=COL_BG,
                 fg=COL_FG, font=(UI_FONT, 9)).pack(anchor="w", padx=16, pady=(14, 4))
        filt = tk.Entry(dlg, font=(UI_FONT, 10), bg=COL_WHITE, fg=COL_INPUT_TEXT,
                        relief="flat", bd=0, highlightthickness=2,
                        highlightbackground=COL_BORDER, highlightcolor=COL_FOCUS,
                        insertbackground=COL_INPUT_TEXT)
        filt.pack(fill="x", padx=16, ipady=4)

        listframe = tk.Frame(dlg, bg=COL_WHITE)
        listframe.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        scroll = ttk.Scrollbar(listframe, orient="vertical")
        scroll.pack(side="right", fill="y")
        lb = tk.Listbox(listframe, height=14, activestyle="none",
                        font=(UI_FONT, 10), bg=COL_WHITE, fg=COL_INPUT_TEXT,
                        yscrollcommand=scroll.set, highlightthickness=0, bd=0,
                        selectbackground=COL_YELLOW, selectforeground=COL_FG)
        lb.pack(side="left", fill="both", expand=True)
        scroll.config(command=lb.yview)

        shown = []

        def refill(*_):
            q = filt.get().strip().lower()
            lb.delete(0, tk.END)
            shown.clear()
            for name, appid in apps:
                if q in name.lower():
                    shown.append((name, appid))
                    lb.insert(tk.END, name)
            if shown:
                lb.selection_set(0)

        def choose(*_):
            sel = lb.curselection()
            if sel:
                result["choice"] = shown[sel[0]]
                dlg.destroy()

        def cancel(*_):
            dlg.destroy()

        filt.bind("<KeyRelease>", refill)
        lb.bind("<Double-Button-1>", choose)
        dlg.bind("<Return>", choose)
        dlg.bind("<Escape>", cancel)
        refill()

        btns = tk.Frame(dlg, bg=COL_BG)
        btns.pack(fill="x", padx=16, pady=12)
        ok = tk.Button(btns, text="Select", command=choose, bg=COL_YELLOW,
                       fg=COL_FG, font=(UI_FONT, 10, "bold"), relief="flat", bd=0,
                       padx=18, pady=6, cursor="hand2", activebackground=COL_WHITE,
                       activeforeground=COL_YELLOW)
        ok.pack(side="right")
        self._add_hover(ok, COL_YELLOW, COL_FG, COL_WHITE, COL_YELLOW)
        cancelb = tk.Button(btns, text="Cancel", command=cancel, bg=COL_WHITE,
                            fg=COL_FG, font=(UI_FONT, 10, "bold"), relief="solid",
                            bd=1, padx=18, pady=6, cursor="hand2",
                            activebackground=COL_YELLOW, activeforeground=COL_WHITE)
        cancelb.pack(side="right", padx=(0, 8))
        self._add_hover(cancelb, COL_WHITE, COL_FG, COL_YELLOW, COL_WHITE)

        dlg.geometry("380x430")
        filt.focus_set()
        dlg.wait_window()
        return result["choice"]

    def _collect_shortcuts(self):
        """Build {prompt_key: pynput combo} from the dropdowns."""
        shortcuts = {}
        for key in self.entries:
            mods = MODIFIER_PRESETS.get(self.mod_vars[key].get(), ["<ctrl>", "<shift>"])
            token = key_display_to_token(self.key_vars[key].get())
            shortcuts[key] = parts_to_combo(mods, token)
        return shortcuts

    def _persist(self):
        """Write all current settings to disk and reload the hotkeys."""
        prompts = {key: entry.get().strip() for key, entry in self.entries.items()}
        shortcuts = self._collect_shortcuts()
        save_config(prompts, append_clipboard=self.append_var.get(),
                    shortcuts=shortcuts, password_warning=self.pw_warn_var.get(),
                    send_to_target=self.target_var.get(),
                    target=self.target if self.target is not None else {})
        if self.on_shortcuts_changed:
            self.on_shortcuts_changed()

    def _save(self):
        shortcuts = self._collect_shortcuts()

        # Warn about duplicate shortcuts (only one of them would ever fire).
        seen, dupes = {}, []
        for key, combo in shortcuts.items():
            if combo in seen:
                dupes.append(combo_to_human(combo))
            seen[combo] = key
        if dupes:
            unique = ", ".join(sorted(set(dupes)))
            if not messagebox.askyesno(
                "Desktop Prompt Manager – duplicate shortcuts",
                f"These shortcuts are assigned to more than one prompt: {unique}.\n\n"
                "Only one prompt per combination will respond. Save anyway?",
                parent=self.win,
            ):
                return

        # If target mode is on but no app was chosen, it silently falls back to
        # the focused window – let the user know.
        if self.target_var.get() and not self.target:
            messagebox.showwarning(
                "Desktop Prompt Manager",
                "Target-app mode is on but no application is selected. Use "
                "“Pick installed app…” or “Browse .exe…”, otherwise prompts go "
                "to the focused window as usual.", parent=self.win)

        self._persist()
        messagebox.showinfo("Desktop Prompt Manager", "✅ Prompts saved.", parent=self.win)

    def _reset(self):
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, DEFAULT_PROMPTS[key])
            # Reset the shortcut dropdowns to their defaults too.
            mods, token = combo_to_parts(DEFAULT_SHORTCUTS[key])
            self.mod_vars[key].set(modtokens_to_label(mods) or "Ctrl+Shift")
            self.key_vars[key].set(key_token_to_display(token))
        self.append_var.set(True)
        self.pw_warn_var.set(True)
        self.target_var.set(False)
        self.target = None
        self.target_label.config(text=self._target_label_text())
        save_config(dict(DEFAULT_PROMPTS), append_clipboard=True,
                    shortcuts=dict(DEFAULT_SHORTCUTS), password_warning=True,
                    send_to_target=False, target={})
        if self.on_shortcuts_changed:
            self.on_shortcuts_changed()
        messagebox.showinfo(
            "Desktop Prompt Manager", "\U0001F504 Prompts reset to defaults.", parent=self.win
        )

    def _on_close(self):
        # Closing the window keeps your changes – no need to click Save first.
        try:
            self._persist()
        except Exception:
            pass
        try:
            self._settings_canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        if self.win is not None:
            self.win.destroy()
            self.win = None


# --------------------------------------------------------------------------- #
# Help window (renders the README)
# --------------------------------------------------------------------------- #

FALLBACK_HELP = (
    "# Desktop Prompt Manager\n\n"
    "Insert up to 10 custom prompts into any focused app with global shortcuts.\n\n"
    "## Shortcuts\n"
    "Default: Ctrl+Shift+F1..F10 for prompts 1-10. "
    "Change them per prompt in Settings.\n\n"
    "## One-action instructing\n"
    "Copy a snippet, press a shortcut, and the prompt is inserted with your "
    "copied text right after it. Toggle in Settings.\n\n"
    "## Password safety net\n"
    "Warns before pasting copied text that looks like a password or secret.\n\n"
    "## Send to a specific app\n"
    "Optionally route prompts to one fixed app (e.g. Claude Desktop) instead of "
    "the focused window: pick its .exe in Settings, then select text and press a "
    "shortcut to paste prompt + selection straight into it. Windows only.\n"
)


def load_help_text() -> str:
    """Read the README so the in-app help shows the same guide."""
    try:
        with open(resource_path("README.md"), "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return FALLBACK_HELP


def configure_help_tags(tw: "tk.Text") -> None:
    """Set the text tags used for lightweight markdown rendering."""
    tw.tag_configure("h1", font=(UI_FONT, 16, "bold"), foreground=COL_FG,
                     spacing1=10, spacing3=8)
    tw.tag_configure("h2", font=(UI_FONT, 13, "bold"), foreground=COL_FG,
                     spacing1=14, spacing3=6)
    tw.tag_configure("h3", font=(UI_FONT, 11, "bold"), foreground=COL_FG,
                     spacing1=10, spacing3=4)
    tw.tag_configure("normal", font=(UI_FONT, 10), foreground=COL_FG, spacing3=3)
    tw.tag_configure("b", font=(UI_FONT, 10, "bold"), foreground=COL_FG)
    tw.tag_configure("code", font=("Courier New", 10),
                     background="#e9ecef", foreground="#333333")
    tw.tag_configure("note", font=(UI_FONT, 9, "italic"), foreground="#8a6d00",
                     lmargin1=12, lmargin2=12, spacing3=3)
    tw.tag_configure("bullet", font=(UI_FONT, 10), foreground=COL_FG,
                     lmargin1=12, lmargin2=26, spacing3=3)


def _insert_help_inline(tw, s: str, base="normal"):
    """Insert a line, rendering **bold** and `code` spans."""
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*|`([^`]+?)`", s):
        if m.start() > pos:
            tw.insert("end", s[pos:m.start()], (base,))
        if m.group(1) is not None:
            tw.insert("end", m.group(1), ("b",))
        else:
            tw.insert("end", m.group(2), ("code",))
        pos = m.end()
    if pos < len(s):
        tw.insert("end", s[pos:], (base,))


def render_help_markdown(tw: "tk.Text", md: str) -> None:
    """Render a subset of markdown into a Text widget, then lock it read-only."""
    tw.configure(state="normal")
    tw.delete("1.0", "end")
    in_code = False
    for raw in md.splitlines():
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            tw.insert("end", raw + "\n", ("code",))
            continue
        if raw.startswith("# "):
            tw.insert("end", raw[2:] + "\n", ("h1",))
        elif raw.startswith("## "):
            tw.insert("end", raw[3:] + "\n", ("h2",))
        elif raw.startswith("### "):
            tw.insert("end", raw[4:] + "\n", ("h3",))
        elif raw.startswith("> "):
            _insert_help_inline(tw, raw[2:] + "\n", base="note")
        elif raw.strip() == "":
            tw.insert("end", "\n")
        else:
            m = re.match(r"^(\s*[-*]\s+)(.*)", raw)
            if m:
                tw.insert("end", "•  ", ("bullet",))
                _insert_help_inline(tw, m.group(2) + "\n", base="bullet")
            else:
                _insert_help_inline(tw, raw + "\n", base="normal")
    tw.configure(state="disabled")


class HelpWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win = None
        self._imgs = []

    def _logo(self, height: int):
        img = Image.open(resource_path("logo.png"))
        w, h = img.size
        new_w = max(1, int(round(w * height / h)))
        photo = ImageTk.PhotoImage(img.resize((new_w, height), Image.LANCZOS))
        self._imgs.append(photo)
        return photo

    def show(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            return

        self._imgs = []
        self.win = tk.Toplevel(self.root)
        self.win.title(f"{APP_TITLE} – Help")
        self.win.configure(bg=COL_BG)
        self.win.geometry("660x620")
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Header
        header = tk.Frame(self.win, bg=COL_WHITE)
        header.pack(fill="x")
        head_inner = tk.Frame(header, bg=COL_WHITE)
        head_inner.pack(anchor="w", padx=20, pady=15)
        try:
            tk.Label(head_inner, image=self._logo(22), bg=COL_WHITE).pack(
                side="left", padx=(0, 8))
        except Exception:
            pass
        tk.Label(head_inner, text="Help", bg=COL_WHITE, fg=COL_FG,
                 font=(UI_FONT, 13, "bold")).pack(side="left")
        tk.Frame(self.win, height=1, bg=COL_SEP).pack(fill="x")

        # Scrollable text area
        body = tk.Frame(self.win, bg=COL_WHITE)
        body.pack(fill="both", expand=True, padx=0, pady=0)
        scroll = ttk.Scrollbar(body, orient="vertical")
        scroll.pack(side="right", fill="y")
        text = tk.Text(body, wrap="word", bg=COL_WHITE, fg=COL_FG,
                       relief="flat", bd=0, padx=24, pady=18,
                       font=(UI_FONT, 10), yscrollcommand=scroll.set,
                       cursor="arrow")
        text.pack(side="left", fill="both", expand=True)
        scroll.config(command=text.yview)

        configure_help_tags(text)
        render_help_markdown(text, load_help_text())

        # Close button
        footer = tk.Frame(self.win, bg=COL_BG)
        footer.pack(fill="x")
        close = tk.Button(footer, text="Close", command=self._on_close,
                          bg=COL_YELLOW, fg=COL_FG, font=(UI_FONT, 10, "bold"),
                          relief="flat", bd=0, padx=22, pady=8, cursor="hand2",
                          activebackground=COL_WHITE, activeforeground=COL_YELLOW)
        close.pack(anchor="e", padx=20, pady=12)

        self.win.lift()
        self.win.focus_force()

    def _on_close(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


# --------------------------------------------------------------------------- #
# About window (+ update check)
# --------------------------------------------------------------------------- #

def _version_tuple(s: str, length: int):
    parts = [int(x) for x in re.findall(r"\d+", s)]
    parts += [0] * (length - len(parts))
    return tuple(parts)


def remote_is_newer(remote: str, local: str) -> bool:
    """True if `remote` version string is strictly newer than `local`."""
    n = max(len(re.findall(r"\d+", remote)), len(re.findall(r"\d+", local)), 1)
    return _version_tuple(remote, n) > _version_tuple(local, n)


def fetch_remote_version(url: str, timeout: int = 8) -> str:
    """Fetch the plain-text version file; return the first non-empty line."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    for line in raw.splitlines():
        if line.strip():
            return line.strip()
    return ""


class AboutWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win = None

    def show(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            return

        self.win = tk.Toplevel(self.root)
        self.win.title(f"About {APP_TITLE}")
        self.win.configure(bg=COL_WHITE)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # White content card
        card = tk.Frame(self.win, bg=COL_WHITE)
        card.pack(fill="both", expand=True, padx=28, pady=(24, 12))

        # Bold app name + version
        tk.Label(card, text=f"{APP_TITLE}  v{APP_VERSION}", bg=COL_WHITE, fg=COL_FG,
                 font=(UI_FONT, 14, "bold")).pack(anchor="w")

        # Short description
        tk.Label(card, text=APP_DESCRIPTION, bg=COL_WHITE, fg=COL_FG,
                 font=(UI_FONT, 9), justify="left", wraplength=420).pack(
                     anchor="w", pady=(8, 14))

        # Author / License
        tk.Label(card, text=f"Author: {APP_AUTHOR}", bg=COL_WHITE, fg=COL_FG,
                 font=(UI_FONT, 9)).pack(anchor="w")
        tk.Label(card, text=f"License: {APP_LICENSE}", bg=COL_WHITE, fg=COL_FG,
                 font=(UI_FONT, 9)).pack(anchor="w", pady=(2, 0))

        # Footer with Check for updates + Close, both right-aligned
        tk.Frame(self.win, height=1, bg=COL_SEP).pack(fill="x")
        footer = tk.Frame(self.win, bg=COL_BG)
        footer.pack(fill="x")

        close = tk.Button(footer, text="Close", command=self._on_close,
                          bg=COL_YELLOW, fg=COL_FG, font=(UI_FONT, 10, "bold"),
                          relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                          activebackground=COL_WHITE, activeforeground=COL_YELLOW)
        close.pack(side="right", padx=(0, 20), pady=12)
        SettingsWindow._add_hover(close, COL_YELLOW, COL_FG, COL_WHITE, COL_YELLOW)

        self.update_btn = tk.Button(
            footer, text="Check for updates", command=self._check_updates,
            bg=COL_WHITE, fg=COL_FG, font=(UI_FONT, 10, "bold"),
            relief="solid", bd=1, padx=18, pady=8, cursor="hand2",
            activebackground=COL_YELLOW, activeforeground=COL_WHITE)
        self.update_btn.pack(side="right", padx=(0, 10), pady=12)
        SettingsWindow._add_hover(self.update_btn, COL_WHITE, COL_FG,
                                  COL_YELLOW, COL_WHITE)

        self.win.lift()
        self.win.focus_force()

    # ---- Update check ----------------------------------------------------- #
    def _check_updates(self):
        self.update_btn.configure(text="Checking…", state="disabled")
        threading.Thread(target=self._do_check, daemon=True).start()

    def _do_check(self):
        # Build a plain message synchronously (never reference the exception
        # object in a deferred callback – Python clears it after the except
        # block, which would raise inside the Tk thread).
        try:
            remote = fetch_remote_version(VERSION_CHECK_URL)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                msg = ("The version file was not found (HTTP 404).\n\n"
                       "If your GitHub repository is private, its raw file URLs "
                       "are not publicly accessible. Make the repository public, "
                       "or host the version file somewhere public.")
            else:
                msg = f"The update server returned HTTP {exc.code}."
            self._show("warning", msg)
            return
        except Exception as exc:
            self._show("warning", f"Could not reach the update server.\n\n{exc}")
            return

        if not remote or not re.search(r"\d", remote):
            self._show("warning",
                       "Could not read a version number from the update source.")
            return

        if remote_is_newer(remote, APP_VERSION):
            self._show("update", remote)
        else:
            self._show("info", f"You have the latest version ({APP_VERSION}).")

    def _show(self, kind: str, payload: str):
        """Restore the button and show a result on the Tk thread.

        Values are bound via default arguments so the scheduled callback is
        safe regardless of thread or timing.
        """
        def run(kind=kind, payload=payload):
            if self.win is not None and self.win.winfo_exists():
                self.update_btn.configure(text="Check for updates", state="normal")
            if kind == "update":
                if messagebox.askyesno(
                    "Desktop Prompt Manager",
                    f"A new version ({payload}) is available – you have "
                    f"{APP_VERSION}.\n\nOpen the download page?",
                    parent=self.win,
                ):
                    webbrowser.open(GITHUB_URL)
            elif kind == "info":
                messagebox.showinfo("Desktop Prompt Manager", payload, parent=self.win)
            else:
                messagebox.showwarning("Desktop Prompt Manager", payload, parent=self.win)
        self.root.after(0, run)

    def _on_close(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


# --------------------------------------------------------------------------- #
# Tray icon
# --------------------------------------------------------------------------- #

def resource_path(name: str) -> str:
    """Resolve a bundled resource, both from source and from a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def make_icon_image() -> Image.Image:
    """Use the original app logo; fall back to a drawn icon if it's missing."""
    try:
        return Image.open(resource_path("logo.png"))
    except Exception:
        img = Image.new("RGB", (64, 64), "#2d6cdf")
        draw = ImageDraw.Draw(img)
        draw.rectangle([12, 12, 52, 52], outline="white", width=3)
        draw.line([20, 24, 44, 24], fill="white", width=3)
        draw.line([20, 32, 44, 32], fill="white", width=3)
        draw.line([20, 40, 36, 40], fill="white", width=3)
        return img


class App:
    def __init__(self):
        # Hidden Tk root that owns the settings window and runs the main loop.
        self.root = tk.Tk()
        self.root.withdraw()

        # Use the app logo as the window/title-bar icon (replaces the default
        # Tk feather). Applied to the root as default, so every Toplevel – the
        # settings window included – inherits it. Keep a reference alive.
        try:
            self._icon_photo = ImageTk.PhotoImage(Image.open(resource_path("logo.png")))
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

        self.help = HelpWindow(self.root)
        self.about = AboutWindow(self.root)
        self.settings = SettingsWindow(self.root,
                                       on_shortcuts_changed=self.reload_hotkeys)

        # Let a background paste ask for confirmation / show messages on Tk.
        set_confirm_hook(self._confirm_paste)
        set_notify_hook(self._notify)

        self.hotkeys = build_hotkeys()
        self.icon = pystray.Icon(
            APP_NAME,
            make_icon_image(),
            "Desktop Prompt Manager",
            menu=pystray.Menu(
                pystray.MenuItem("Settings", self._open_settings),
                pystray.MenuItem("Help", self._open_help),
                pystray.MenuItem("About", self._open_about),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    # Tray callbacks run on the pystray thread, so marshal UI work onto Tk.
    def _open_settings(self, icon=None, item=None):
        self.root.after(0, self.settings.show)

    def _open_help(self, icon=None, item=None):
        self.root.after(0, self.help.show)

    def _open_about(self, icon=None, item=None):
        self.root.after(0, self.about.show)

    def _notify(self, message: str):
        """Show an informational message from a background thread, on the Tk thread."""
        self.root.after(0, lambda: messagebox.showwarning(
            "Desktop Prompt Manager", message))

    def reload_hotkeys(self):
        """Rebuild the global hotkey listener after the user changes shortcuts."""
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        self.hotkeys = build_hotkeys()
        self.hotkeys.start()

    def _confirm_paste(self, masked_preview: str) -> bool:
        """Ask (on the Tk thread) whether to paste secret-looking text.

        Called from a background paste thread; blocks it until the user answers.
        """
        result = {"ok": False}
        done = threading.Event()

        def ask():
            try:
                result["ok"] = messagebox.askyesno(
                    "Desktop Prompt Manager – possible password",
                    "The text you're about to paste looks like it could be a "
                    "password or secret:\n\n"
                    f"    {masked_preview}\n\n"
                    "Paste it anyway?",
                    icon="warning", parent=self.root,
                )
            finally:
                done.set()

        self.root.after(0, ask)
        done.wait()
        return result["ok"]

    def _quit(self, icon=None, item=None):
        self.root.after(0, self._shutdown)

    def _shutdown(self):
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self.icon.stop()
        except Exception:
            pass
        self.root.quit()

    def run(self):
        self.hotkeys.start()
        # pystray runs in its own thread; Tk owns the main thread.
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
