#!/usr/bin/env python3
"""
Yap for Windows v3 — Premium Push-to-Talk Dictation
Dark purple theme | Frameless | Glow animations
"""

import sys, os, io, json, time, wave, threading, math, ctypes, queue, traceback
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import sounddevice as sd
    import pyperclip
    from PIL import Image, ImageDraw
    import pystray
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import messagebox
except ImportError as e:
    print(f"\n[ERROR] Missing: {e}\nRun setup.bat\n")
    sys.exit(1)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Design System ──────────────────────────────────────────
BG      = "#0b0b18"
BG2     = "#111128"
BG3     = "#191933"
BORDER  = "#23233d"
BORDER2 = "#2e2e50"
TEXT    = "#eaeaf8"
DIM     = "#60609a"
DIM2    = "#38385a"
RED     = "#f04555"
BLUE    = "#4d80f5"
GREEN   = "#2ecc71"
PURPLE  = "#8b5cf6"
PURPLED = "#6d3fd4"

APP_NAME    = "YapWindows"
VERSION     = "3.0"
CONFIG_DIR  = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE  = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

# Whisper copies the STYLE of this text, not just its vocabulary. So the hint
# is written as real code-switched sentences: that is what teaches it "this
# speaker mixes Vietnamese and English, and English words stay in English".
# A bare word list alone still let "Ctrl" come back as "căn chuồn".
DEFAULT_PROMPT = (
    "Anh review lại cái commit này giúp em, xong thì push lên branch main. "
    "Mình cần fix cái bug ở workflow n8n trước deadline, rồi deploy lên production. "
    "Let me know if the API key is still valid, tôi sẽ check lại trong file config. "
    "Chú mở terminal lên chạy cái script Python đó, nhớ backup database trước. "
    "Cái landing page bên Shopify với flow bên Klaviyo đang lỗi, em xem lại template. "
    "Bấm Ctrl, Alt, Shift, Enter, Tab, Esc — mấy phím này anh hay nhắc tới. "
    "Các tên hay dùng: Claude, Codex, Cursor, Linear, GitHub, Printify, WordPress, "
    "Etsy, Meta, YouTube, Google Drive, Gmail, Excel, Notepad, Chrome, Windows. "
    "Từ hay gặp: file, folder, repo, merge, log, server, query, build, test, debug, "
    "token, campaign, segment, SKU, JSON, PDF, URL, link, app, screenshot, budget."
)

DEFAULT_CONFIG = {
    "api_key": "",
    "provider": "groq",
    "language": "auto",
    # Right Ctrl, not Space: the hook does NOT suppress the key, so a Space
    # default types real spaces into whatever the user is writing in.
    "hotkey": "right ctrl",
    # Whisper's `prompt`: a vocabulary hint, not an instruction. Without it,
    # English terms spoken inside Vietnamese come back transliterated —
    # "Ctrl" heard as "căn chuồn". Listing the words fixes exactly that.
    "prompt": DEFAULT_PROMPT,
    # large-v3, not turbo. Turbo is the distilled model — faster, but noticeably
    # weaker on Vietnamese and on accented English, which is most of the traffic
    # here. The extra ~$0.07/hour is not the constraint; being misheard is.
    "model": "whisper-large-v3",
}

GROQ_MODELS = {
    "whisper-large-v3":       ("Large v3", "Chính xác nhất · tiếng Việt tốt hơn"),
    "whisper-large-v3-turbo": ("Large v3 Turbo", "Nhanh hơn · kém chính xác hơn"),
}

HOLD_THRESHOLD = 0.4   # seconds the key must be held before it counts as dictation

# The API key lives in this project's own .env, not in a shared store and not
# in another repo's file. config.json stays as a fallback for existing installs.
ENV_FILE      = Path(__file__).resolve().parent / ".env"
ENV_KEY_NAMES = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY"}

SAMPLE_RATE = 16000
CHANNELS    = 1
MAX_HISTORY = 100

# Gate before we spend an API call. Tuned conservatively: it is cheaper to
# transcribe the odd quiet clip than to swallow someone speaking softly.
MIN_DURATION = 0.35   # seconds of audio
MIN_RMS      = 80     # int16 units (full scale 32768); below this is room tone

PASTE_WAIT   = 1.0    # max seconds to wait for held modifiers to clear


def blend(c1: str, c2: str, t: float) -> str:
    r1,g1,b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
    r2,g2,b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1*(1-t)+r2*t), int(g1*(1-t)+g2*t), int(b1*(1-t)+b2*t))


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try: cfg.update(json.loads(CONFIG_FILE.read_text("utf-8")))
        except: pass
    # Normalise here so nothing downstream has to defend itself. A hand-edited
    # config.json with `"hotkey": null` used to kill the app on hk.upper()
    # before it ever reached the fallback below.
    for key in ("api_key", "provider", "language", "hotkey"):
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            cfg[key] = DEFAULT_CONFIG[key]
        else:
            cfg[key] = cfg[key].strip()
    return cfg

def _write_atomic(path: Path, data: str) -> None:
    """Write via a temp file + replace, so a crash mid-write cannot leave a
    truncated config/history that silently loses the API key or the log."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        try: tmp.unlink()          # don't litter a half-written file behind us
        except Exception: pass
        raise

def save_config(cfg: dict) -> None:
    _write_atomic(CONFIG_FILE, json.dumps(cfg, indent=2, ensure_ascii=False))

def load_history() -> list:
    if HISTORY_FILE.exists():
        try: return json.loads(HISTORY_FILE.read_text("utf-8"))
        except: pass
    return []

def save_history(h: list) -> None:
    _write_atomic(HISTORY_FILE,
                  json.dumps(h[-MAX_HISTORY:], indent=2, ensure_ascii=False))


def load_env() -> dict:
    """Parse this project's .env. Re-read on every call, so pasting a key in
    takes effect without restarting the app."""
    out = {}
    try:
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text("utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                out[name.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        traceback.print_exc()
    return out


def provider_key(provider: str, cfg: dict) -> str:
    """.env wins over config.json — one key, one place, per project."""
    from_env = load_env().get(ENV_KEY_NAMES.get(provider, ""), "").strip()
    return from_env or (cfg.get("api_key") or "").strip()


def key_source(provider: str, cfg: dict) -> str:
    if load_env().get(ENV_KEY_NAMES.get(provider, ""), "").strip():
        return "env"
    if (cfg.get("api_key") or "").strip():
        return "config"
    return "none"


def wav_stats(audio: bytes):
    """(duration_seconds, rms) for a WAV blob — the gate before paying for STT."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as wf:
            frames = wf.getnframes()
            rate   = wf.getframerate() or SAMPLE_RATE
            raw    = wf.readframes(frames)
    except Exception:
        return 0.0, 0.0
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0, 0.0
    # Loudest 30 ms window, not the average: a short quiet "vâng" surrounded by
    # a second of silence averages down to nothing and would be thrown away.
    win   = max(1, int(rate * 0.03))
    n_win = samples.size // win
    if n_win == 0:
        rms = float(np.sqrt(np.mean(samples ** 2)))
    else:
        blocks = samples[:n_win * win].reshape(n_win, win)
        rms = float(np.sqrt(np.mean(blocks ** 2, axis=1)).max())
    return frames / float(rate), rms


def acquire_single_instance():
    """Named mutex; returns None if another Yap already owns it.

    Two copies both poll the hotkey, both open the mic, both bill an API call
    and both paste — and they fight over config.json.
    """
    ERROR_ALREADY_EXISTS = 183
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = wintypes.HANDLE
    handle = k32.CreateMutexW(None, False, f"Local\\{APP_NAME}-SingleInstance")
    if not handle or k32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


# ═══════════════════════════════════════════════════════════
# SMART HOOK  — GetAsyncKeyState polling only, no suppression
#
# Keys pass through hardware normally (no interception), so the hotkey
# must be one the user does not type with — see DEFAULT_CONFIG.
#
# Three callbacks, in order:
#   on_press()          key went down — start capturing at once, so the
#                       first word is not lost while we wait out the hold
#   on_arm()            still held past `threshold` — a real dictation
#   on_release(armed)   key up; armed=False means it was a tap, drop the audio
#
# The poll thread only enqueues; one dispatch thread runs the callbacks in
# order, so a release can never be handled before its own press.
# ═══════════════════════════════════════════════════════════
class SmartHook:
    VK_MAP = {
        'space': 0x20,
        'right ctrl': 0xA3, 'right control': 0xA3,
        'left ctrl':  0xA2, 'left control':  0xA2,
        'ctrl': 0x11, 'control': 0x11,
        'right alt': 0xA5, 'left alt': 0xA4, 'alt': 0x12,
        'f1':0x70,'f2':0x71,'f3':0x72,'f4':0x73,
        'f5':0x74,'f6':0x75,'f7':0x76,'f8':0x77,
        'f9':0x78,'f10':0x79,'f11':0x7A,'f12':0x7B,
        'scroll lock':0x91, 'caps lock':0x14,
        'tab':0x09, 'insert':0x2D, 'home':0x24, 'end':0x23,
    }

    @classmethod
    def resolve(cls, key_name: str):
        """VK code for key_name, or None if we cannot listen for that key."""
        return cls.VK_MAP.get((key_name or "").lower().strip())

    @classmethod
    def supported_keys(cls) -> str:
        return "  ".join(sorted(set(cls.VK_MAP)))

    def __init__(self, key_name: str, threshold: float,
                 on_press, on_arm, on_release):
        self.key_name = (key_name or "").lower().strip()
        vk = self.resolve(self.key_name)
        if vk is None:
            # Never fall back silently: a bad name used to become Space, which
            # then fired every time the user hit the space bar.
            raise ValueError(f"Unsupported hotkey: {key_name!r}")
        self.vk        = vk
        self.threshold = threshold
        self.on_press   = on_press
        self.on_arm     = on_arm
        self.on_release = on_release
        self._running  = False
        self._events   = queue.Queue()
        self._threads  = []

    def _poll(self):
        u32      = ctypes.windll.user32
        was_down = False
        press_t  = None
        armed    = False

        while self._running:
            is_down = bool(u32.GetAsyncKeyState(self.vk) & 0x8000)
            now     = time.time()

            if is_down and not was_down:
                was_down = True
                press_t  = now
                armed    = False
                self._events.put(("press", None))

            elif not is_down and was_down:
                was_down = False
                press_t  = None
                self._events.put(("release", armed))
                armed    = False

            elif is_down and not armed and press_t is not None:
                if (now - press_t) >= self.threshold:
                    armed = True
                    self._events.put(("arm", None))

            time.sleep(0.005)

    def _dispatch(self):
        while self._running:
            try:
                kind, payload = self._events.get(timeout=0.2)
            except queue.Empty:
                continue
            if not self._running:
                # Stopped while we were blocked on get() — do not run a callback
                # for a hook that has already been replaced.
                break
            try:
                if   kind == "press":   self.on_press()
                elif kind == "arm":     self.on_arm()
                elif kind == "release": self.on_release(payload)
            except Exception:
                traceback.print_exc()

    def start(self):
        self._running = True
        self._threads = [
            threading.Thread(target=self._poll, daemon=True,
                             name="SmartHook-Poll"),
            threading.Thread(target=self._dispatch, daemon=True,
                             name="SmartHook-Dispatch"),
        ]
        for th in self._threads: th.start()
        print(f"[SmartHook] key={self.key_name!r}  threshold={self.threshold}s")

    def stop(self):
        """Block until no callback of this hook can start or still be running.

        Without the join, swapping the hotkey could leave the outgoing hook's
        callbacks racing the incoming one over the same recorder.
        """
        self._running = False
        for th in self._threads:
            if th.is_alive():
                th.join(timeout=1.0)
        self._threads = []


# ═══════════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════════
def input_candidates():
    """(device, samplerate) options to try opening, best quality first.

    Recording at 16 kHz makes Windows resample 44.1/48 kHz down with a crude
    filter, and 44100→16000 is not even a whole ratio. That smears fricatives —
    it is why "phết" came back as "chết". So try the mic at its native rate and
    let Whisper do the downsampling with a proper filter on its side.

    But check_input_settings() saying yes does NOT mean the stream will start:
    some host APIs only fail on the real open. So this returns a LIST, and the
    caller walks it until one actually starts. The last entry is always the
    plain default at 16 kHz — the path that shipped and is known to work.
    """
    out, seen = [], set()

    def add(dev, rate):
        if (dev, rate) not in seen:
            seen.add((dev, rate)); out.append((dev, rate))

    try:
        # Re-enumerate: PortAudio caches the device list at init, and a stale
        # index is how "device 12, WASAPI" tried to open as WDM-KS and threw.
        try:
            sd._terminate(); sd._initialize()
        except Exception:
            pass

        # Ask each host API for ITS OWN default input, rather than guessing an
        # index by name. WASAPI first: modern, and no resampling at all.
        for api in sd.query_hostapis():
            if api["name"] == "Windows WASAPI":
                idx = api.get("default_input_device", -1)
                if idx is not None and idx >= 0:
                    add(idx, int(sd.query_devices(idx)["default_samplerate"]))

        default_in = sd.default.device[0]
        info = sd.query_devices(default_in)
        add(default_in, int(info["default_samplerate"]))
    except Exception:
        traceback.print_exc()

    add(None, SAMPLE_RATE)      # original behaviour, the safety net
    return out


class AudioRecorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.recording = False
        self.samplerate = SAMPLE_RATE
        self.level = 0.0        # live mic amplitude 0..1, drives the waveform

    def start(self) -> None:
        # Walk the candidates until one really opens AND starts. Never let the
        # quality preference cost us the ability to record at all.
        self._frames = []
        last = None
        for device, rate in input_candidates():
            stream = None
            try:
                stream = sd.InputStream(device=device, samplerate=rate,
                                        channels=CHANNELS, dtype="int16",
                                        callback=self._cb)
                self.recording = True
                stream.start()
            except Exception as exc:
                last = exc
                self.recording = False
                if stream is not None:
                    try: stream.close()
                    except Exception: pass
                print(f"[mic] {device} @ {rate} Hz khong mo duoc: {str(exc)[:80]}")
                continue
            self._stream    = stream
            self.samplerate = rate
            print(f"[mic] dang thu tu device={device} @ {rate} Hz")
            return
        self._stream = None
        raise last or RuntimeError("Khong mo duoc microphone nao")

    def _cb(self, indata, frames, t, status):
        if not self.recording: return
        self._frames.append(indata.copy())
        # Live level for the waveform, 0..1. Cheap enough to do per block.
        block = indata.astype(np.float32)
        rms = float(np.sqrt(np.mean(block * block))) if block.size else 0.0
        self.level = min(1.0, rms / 4000.0)

    def stop(self) -> Optional[bytes]:
        self.recording = False
        self.level = 0.0
        if self._stream:
            self._stream.stop(); self._stream.close(); self._stream = None
        if not self._frames: return None
        audio = np.concatenate(self._frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS); wf.setsampwidth(2)
            wf.setframerate(self.samplerate)   # native rate, not forced 16 kHz
            wf.writeframes(audio.tobytes())
        return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# STT
# ═══════════════════════════════════════════════════════════
class Transcriber:
    def transcribe(self, audio: bytes, cfg: dict) -> str:
        provider = cfg.get("provider", "groq")
        language = cfg.get("language", "auto")
        lang     = None if language == "auto" else language
        api_key  = provider_key(provider, cfg)

        if not api_key:
            var = ENV_KEY_NAMES.get(provider, "GROQ_API_KEY")
            raise ValueError(
                f"Chưa có API key.\n\nDán key vào {var}= trong file:\n{ENV_FILE}\n\n"
                "Lấy key free ở: console.groq.com"
            )

        prompt = (cfg.get("prompt") or "").strip()

        model = cfg.get("model") or DEFAULT_CONFIG["model"]

        f = io.BytesIO(audio); f.name = "audio.wav"
        if provider == "groq":   return self._groq(f, api_key, lang, prompt, model)
        if provider == "openai": return self._openai(f, api_key, lang, prompt)
        raise ValueError(f"Unknown provider: {provider}")

    def _groq(self, f, key, lang, prompt="", model="whisper-large-v3") -> str:
        from groq import Groq
        c = Groq(api_key=key)
        p = {"file": f, "model": model, "response_format": "json"}
        if lang:   p["language"] = lang
        if prompt: p["prompt"]   = prompt
        return c.audio.transcriptions.create(**p).text.strip()

    def _openai(self, f, key, lang, prompt="") -> str:
        try: import openai
        except ImportError: raise ValueError("Run: pip install openai")
        c = openai.OpenAI(api_key=key)
        p = {"file": f, "model": "whisper-1", "response_format": "text"}
        if lang:   p["language"] = lang
        if prompt: p["prompt"]   = prompt
        r = c.audio.transcriptions.create(**p)
        return (r if isinstance(r, str) else r.text).strip()


# ═══════════════════════════════════════════════════════════
# SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, cfg: dict, on_save):
        super().__init__(parent)
        self.cfg = cfg
        self.on_save = on_save

        self.title("Settings — Yap")
        self.geometry("480x570")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.attributes("-topmost", True)
        self.after(50, self.lift)
        self.after(100, self.focus_force)
        self._build()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=62)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        icon_bg = ctk.CTkFrame(hdr, fg_color=PURPLE, corner_radius=10,
                               width=36, height=36)
        icon_bg.pack(side="left", padx=16, pady=13); icon_bg.pack_propagate(False)
        ctk.CTkLabel(icon_bg, text="⚙", font=("Segoe UI", 16),
                     text_color="white").pack(expand=True)

        txt_col = ctk.CTkFrame(hdr, fg_color="transparent")
        txt_col.pack(side="left", padx=8, pady=13)
        ctk.CTkLabel(txt_col, text="Settings",
                     font=("Segoe UI", 15, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(txt_col, text=f"Yap v{VERSION}",
                     font=("Segoe UI", 10), text_color=DIM).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color=BG,
                                       scrollbar_button_color=BG3,
                                       scrollbar_button_hover_color=BORDER2)
        body.pack(fill="both", expand=True)

        def section(label):
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=(14, 5))
            ctk.CTkLabel(row, text=label, font=("Segoe UI", 9, "bold"),
                         text_color=DIM).pack(side="left")
            ctk.CTkFrame(row, fg_color=BORDER2, height=1).pack(
                side="left", fill="x", expand=True, padx=(10, 0), pady=6)

        def card():
            f = ctk.CTkFrame(body, fg_color=BG2, corner_radius=14,
                             border_width=1, border_color=BORDER)
            f.pack(fill="x", padx=16, pady=2)
            return f

        # Provider
        section("STT PROVIDER")
        pc = card()
        self._provider = ctk.StringVar(value=self.cfg.get("provider", "groq"))
        for val, name, sub in [
            ("groq",   "Groq Whisper Large v3 Turbo", "Free · 2000 min/day · Fastest"),
            ("openai", "OpenAI Whisper-1",             "Paid · Standard quality"),
        ]:
            row = ctk.CTkFrame(pc, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=7)
            ctk.CTkRadioButton(row, text=name, variable=self._provider, value=val,
                               font=("Segoe UI", 12, "bold"), text_color=TEXT,
                               fg_color=PURPLE, hover_color=PURPLED).pack(side="left")
            ctk.CTkLabel(row, text=sub, font=("Segoe UI", 10),
                         text_color=DIM).pack(side="left", padx=10)

        # API Key
        section("API KEY")
        ac = card()
        self._api_key = ctk.StringVar(value=self.cfg.get("api_key", ""))
        row = ctk.CTkFrame(ac, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)
        self._key_entry = ctk.CTkEntry(
            row, textvariable=self._api_key, show="•",
            font=("Consolas", 12), fg_color=BG3,
            border_color=BORDER2, text_color=TEXT, height=40,
            placeholder_text="gsk_xxxxxxxxxxxxxxxxxxxx")
        self._key_entry.pack(side="left", fill="x", expand=True)
        self._show = False
        def toggle():
            self._show = not self._show
            self._key_entry.configure(show="" if self._show else "•")
            eye.configure(text="Hide" if self._show else "Show")
        eye = ctk.CTkButton(row, text="Show", width=58, height=40,
                            fg_color=BG3, hover_color=BORDER2, text_color=DIM,
                            font=("Segoe UI", 10), command=toggle)
        eye.pack(side="left", padx=(6, 0))
        src = key_source(self.cfg.get("provider", "groq"), self.cfg)
        note = {
            "env":    f"✓ Đang dùng key trong .env — ô trên bỏ trống là đúng",
            "config": "Key đang lưu ở config.json. Nên chuyển sang .env.",
            "none":   "Chưa có key. Dán vào .env cạnh app.py, hoặc điền ô trên.",
        }[src]
        ctk.CTkLabel(ac, text=note, font=("Segoe UI", 10),
                     text_color=(GREEN if src == "env" else DIM)).pack(
            anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(ac, text="Get free key at  console.groq.com",
                     font=("Segoe UI", 10), text_color=DIM).pack(
            anchor="w", padx=14, pady=(0, 8))

        # Language
        section("LANGUAGE")
        lc = card()
        self._language = ctk.StringVar(value=self.cfg.get("language", "auto"))
        lrow = ctk.CTkFrame(lc, fg_color="transparent")
        lrow.pack(anchor="w", padx=14, pady=10)
        for val, label in [("auto", "Auto detect"), ("vi", "Vietnamese"), ("en", "English")]:
            ctk.CTkRadioButton(lrow, text=label, variable=self._language, value=val,
                               font=("Segoe UI", 12), text_color=TEXT,
                               fg_color=PURPLE, hover_color=PURPLED).pack(
                side="left", padx=(0, 20))

        # Vocabulary hint
        section("TỪ VỰNG  —  từ tiếng Anh hay bị nghe nhầm")
        vc = card()
        self._prompt_box = ctk.CTkTextbox(
            vc, height=110, font=("Segoe UI", 11), fg_color=BG3,
            border_color=BORDER2, border_width=1, text_color=TEXT, wrap="word")
        self._prompt_box.pack(fill="x", padx=14, pady=(10, 4))
        self._prompt_box.insert("1.0", self.cfg.get("prompt") or "")
        ctk.CTkLabel(vc, text="Thêm từ anh hay nói mà máy nghe sai, cách nhau bằng dấu phẩy.\n"
                              "Viết đúng dạng anh muốn nó hiện ra (ví dụ: Ctrl, chứ không phải căn chuồn).",
                     font=("Segoe UI", 10), justify="left", text_color=DIM).pack(
            anchor="w", padx=14, pady=(0, 4))
        ctk.CTkButton(vc, text="Khôi phục danh sách mặc định", height=30,
                      font=("Segoe UI", 10), fg_color=BG3, hover_color=BORDER2,
                      text_color=DIM, corner_radius=8,
                      command=lambda: (self._prompt_box.delete("1.0", "end"),
                                       self._prompt_box.insert("1.0", DEFAULT_PROMPT))).pack(
            anchor="w", padx=14, pady=(0, 10))

        # Hotkey
        section("HOLD KEY  —  to record")
        hc = card()
        self._hotkey = ctk.StringVar(
            value=self.cfg.get("hotkey") or DEFAULT_CONFIG["hotkey"])
        ctk.CTkEntry(hc, textvariable=self._hotkey, width=200, height=40,
                     font=("Consolas", 13), fg_color=BG3,
                     border_color=BORDER2, text_color=TEXT).pack(
            anchor="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(hc, text="Examples:  right ctrl   f9   scroll lock   right alt",
                     font=("Segoe UI", 10), text_color=DIM).pack(
            anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(hc, text="Avoid keys you type with — the key is not "
                              "suppressed,\nso it still reaches the app you are writing in.",
                     font=("Segoe UI", 10), justify="left", text_color=DIM).pack(
            anchor="w", padx=14, pady=(0, 10))

        # Save
        ctk.CTkButton(body, text="Save & Apply", height=50,
                      font=("Segoe UI", 14, "bold"), corner_radius=14,
                      fg_color=PURPLE, hover_color=PURPLED, text_color="white",
                      command=self._save).pack(fill="x", padx=16, pady=(14, 20))

    def _save(self):
        hotkey = self._hotkey.get().strip()
        if SmartHook.resolve(hotkey) is None:
            messagebox.showerror(
                "Yap",
                f"Hotkey không hỗ trợ: {hotkey!r}\n\n"
                f"Chọn một trong:\n{SmartHook.supported_keys()}",
                parent=self)
            return
        self.cfg.update({
            "api_key":  self._api_key.get().strip(),
            "provider": self._provider.get(),
            "language": self._language.get(),
            "hotkey":   hotkey,
            "prompt":   self._prompt_box.get("1.0", "end").strip(),
        })
        save_config(self.cfg)
        self.on_save(self.cfg)
        self.destroy()


# ═══════════════════════════════════════════════════════════
# MAIN WINDOW — Frameless Premium UI
# ═══════════════════════════════════════════════════════════
class MainWindow(ctk.CTk):
    """A slim floating bar at the top of the screen.

    Nothing but a live waveform: vertical rounded bars, teal at the crown
    fading to violet at the foot, rising and falling with what the mic hears.
    """

    W, H      = 300, 46
    N_BARS    = 44                # many thin bars, not a few fat ones
    BAR_STEP  = 6                 # centre-to-centre; must exceed GLOW_W or
                                  # the halos merge into one solid slab
    TRANS     = "#ff00fe"         # keyed out, gives the pill rounded ends
    CORE_HI   = "#9ffff7"         # crest of a loud bar
    CORE_MID  = "#4fe4de"
    CORE_LO   = "#2b7f8d"         # a quiet one, sunk into the glow
    GLOW      = "#0d5460"         # halo drawn behind each core
    PILL      = "#04111a"
    PILL_EDGE = "#17434c"

    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", self.TRANS)
        except Exception:
            pass                  # older Windows: square corners, still fine

        sw = self.winfo_screenwidth()
        self.geometry("%dx%d+%d+14" % (self.W, self.H, (sw - self.W) // 2))
        self.configure(fg_color=self.TRANS)
        self.resizable(False, False)

        self._state   = "idle"
        self._alive   = True
        self._hotkey  = ""
        self.app_ref  = None
        self.recorder = None                      # set by YapApp
        self.history  = []
        self._levels  = [0.0] * self.N_BARS       # newest on the right
        self._msg     = ""
        self._msg_col = DIM
        self._drag    = {"x": 0, "y": 0}
        self._hist_win = None

        self._cv = tk.Canvas(self, width=self.W, height=self.H,
                             bg=self.TRANS, highlightthickness=0, bd=0)
        self._cv.pack(fill="both", expand=True)
        self._cv.bind("<ButtonPress-1>", self._ds)
        self._cv.bind("<B1-Motion>", self._dm)
        self._cv.bind("<Button-3>", self._menu)
        self._cv.bind("<Double-Button-1>", self._open_settings)

        self._visible = True
        self.hide()              # nothing on screen until the key is held
        self._tick()

    # -- window drag -------------------------------------------------
    def _ds(self, e):
        self._drag = {"x": e.x, "y": e.y}

    def _dm(self, e):
        self.geometry("+%d+%d" % (self.winfo_x() + e.x - self._drag["x"],
                                  self.winfo_y() + e.y - self._drag["y"]))

    def _menu(self, e):
        m = tk.Menu(self, tearoff=0, bg=BG2, fg=TEXT, bd=0,
                    activebackground=PURPLE, activeforeground="white")
        m.add_command(label="Lich su", command=self._open_history)
        m.add_command(label="Settings", command=self._open_settings)
        m.add_separator()
        m.add_command(label="Thoat", command=self._quit)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # -- drawing -----------------------------------------------------
    @staticmethod
    def _capsule(c, x1, y1, x2, y2, fill, outline):
        """A true lozenge: two half-circle ends joined by a straight middle.

        create_polygon(smooth=True) only approximates this and leaves the ends
        looking like a squared-off box with soft corners.
        """
        r = (y2 - y1) / 2.0
        c.create_oval(x1, y1, x1 + 2*r, y2, fill=fill, outline=outline)
        c.create_oval(x2 - 2*r, y1, x2, y2, fill=fill, outline=outline)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
        c.create_line(x1 + r, y1, x2 - r, y1, fill=outline)
        c.create_line(x1 + r, y2, x2 - r, y2, fill=outline)

    def _bar(self, c, x, cy, h, lvl):
        """One hair-thin bar, mirrored about the centre line, with a halo.

        Two strokes: a wide dim one for the bloom, a 2px bright one on top.
        Round caps do the rounding, so a bar of zero height reads as a dot.
        """
        half = max(1.0, h / 2.0)
        y1, y2 = cy - half, cy + half
        c.create_line(x, y1, x, y2, fill=self.GLOW, width=4, capstyle=tk.ROUND)
        core = (blend(self.CORE_LO, self.CORE_MID, lvl / 0.45)
                if lvl < 0.45 else
                blend(self.CORE_MID, self.CORE_HI, (lvl - 0.45) / 0.55))
        c.create_line(x, y1, x, y2, fill=core, width=2, capstyle=tk.ROUND)

    def _tick(self):
        try:
            self._sample()
            if self._visible:
                self._draw()
        except Exception:
            traceback.print_exc()
        if self._alive:
            self.after(40, self._tick)

    def _sample(self):
        """Push one new level onto the right of the scrolling waveform."""
        t = time.time()
        if self._state == "recording":
            lvl = getattr(self.recorder, "level", 0.0) if self.recorder else 0.0
            lvl = min(1.0, lvl ** 0.6)               # ease the quiet end up
        elif self._state == "transcribing":
            lvl = 0.30 + 0.26 * math.sin(t * 7.0)    # travelling pulse
        elif self._state == "idle":
            lvl = 0.05 + 0.03 * math.sin(t * 1.6)    # barely breathing
        else:
            lvl = 0.0                                # a message is showing
        self._levels = self._levels[1:] + [lvl]

    def _draw(self):
        c = self._cv
        c.delete("all")
        # Capsule: radius is half the height, so the ends are true semicircles.
        self._capsule(c, 1, 1, self.W - 2, self.H - 2,
                      self.PILL, self.PILL_EDGE)

        if self._msg:
            c.create_text(self.W / 2, self.H / 2, text=self._msg,
                          fill=self.CORE_MID, font=("Segoe UI", 10))
            return

        cy    = self.H / 2.0
        span  = (self.N_BARS - 1) * self.BAR_STEP
        x0    = (self.W - span) / 2.0
        max_h = self.H - 16
        for i, lvl in enumerate(self._levels):
            # Fade the outer bars so the wave sits inside the capsule instead
            # of running into its rounded ends.
            edge = min(1.0, min(i, self.N_BARS - 1 - i) / (self.N_BARS / 5.0))
            self._bar(c, x0 + i * self.BAR_STEP, cy,
                      max(1.0, lvl * max_h * (0.25 + 0.75 * edge)), lvl)

    # -- public API used by YapApp -----------------------------------
    def set_state(self, state):
        self._state = state
        if state in ("idle", "recording", "transcribing"):
            self._msg = ""
        else:
            self._msg = state
            self._msg_col = RED if ("held" in state or "changed" in state) else DIM
        # The bar is not a permanent fixture on the desktop: it appears when
        # you hold the key to speak and goes away when there is nothing to say.
        self.hide() if state == "idle" else self.show()

    def set_hotkey_label(self, hk):
        self._hotkey = hk

    def add_entry(self, text, ts):
        self.history.append({"text": text, "timestamp": ts})
        if self._hist_win is not None:
            try:
                self._hist_win.add(text, ts)
            except Exception:
                self._hist_win = None

    def load_history(self, history):
        self.history = list(history)

    def show(self):
        if self._visible: return
        self._visible = True
        self.deiconify()
        # lift only — never focus_force: stealing focus would change the
        # foreground window and send the paste to this bar instead of your app.
        self.lift()

    def hide(self):
        if not self._visible: return
        self._visible = False
        self.withdraw()

    def _open_history(self):
        try:
            if self._hist_win is not None and self._hist_win.winfo_exists():
                self._hist_win.lift()
                return
        except Exception:
            pass
        self._hist_win = HistoryWindow(self, self.history)

    def _open_settings(self, e=None):
        if self.app_ref:
            self.app_ref.open_settings()

    def _quit(self):
        if self.app_ref:
            self.app_ref.quit()


class HistoryWindow(ctk.CTkToplevel):
    """The transcript log, no longer crowding the bar. Click a row to copy."""

    def __init__(self, parent, history):
        super().__init__(parent)
        self.title("Lich su - Yap")
        self.geometry("420x560")
        self.configure(fg_color=BG)
        self.attributes("-topmost", True)
        self._list = ctk.CTkScrollableFrame(
            self, fg_color=BG, scrollbar_button_color=BG3,
            scrollbar_button_hover_color=BORDER2)
        self._list.pack(fill="both", expand=True, padx=8, pady=8)
        for item in reversed(history[-60:]):
            self._row(item.get("text", ""), item.get("timestamp", ""))

    def add(self, text, ts):
        self._row(text, ts, top=True)

    def _row(self, text, ts, top=False):
        row = ctk.CTkFrame(self._list, fg_color=BG2, corner_radius=10,
                           border_width=1, border_color=BORDER)
        kids = self._list.winfo_children()
        if top and kids:
            row.pack(fill="x", pady=(0, 4), before=kids[0])
        else:
            row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(row, text=ts, font=("Segoe UI", 9),
                     text_color=DIM).pack(anchor="w", padx=12, pady=(6, 0))
        ctk.CTkLabel(row, text=text, font=("Segoe UI", 11), text_color=TEXT,
                     wraplength=350, justify="left").pack(
            anchor="w", padx=12, pady=(2, 7))

        def copy(_=None):
            pyperclip.copy(text)
            row.configure(fg_color=blend(BG2, PURPLE, 0.35))
            row.after(250, lambda: row.configure(fg_color=BG2))

        for w in [row] + list(row.winfo_children()):
            w.bind("<Button-1>", copy)
            w.bind("<Enter>", lambda e, r=row: r.configure(fg_color=BG3))
            w.bind("<Leave>", lambda e, r=row: r.configure(fg_color=BG2))




# ═══════════════════════════════════════════════════════════
# APP CONTROLLER
# ═══════════════════════════════════════════════════════════
class YapApp:
    def __init__(self):
        self.cfg     = load_config()
        self.history = load_history()
        self.state   = "idle"

        self._recorder    = AudioRecorder()
        self._transcriber = Transcriber()
        self._recording   = False
        self._lock        = threading.Lock()
        self._hist_lock   = threading.Lock()
        self._shutdown    = threading.Event()
        self._flash_gen   = 0
        self._target_hwnd = None
        self._hook        = None

        self.win = MainWindow()
        self.win.app_ref  = self
        self.win.recorder = self._recorder   # the waveform reads live mic level
        self.win.load_history(self.history)
        self.win.set_hotkey_label(self.cfg.get("hotkey") or DEFAULT_CONFIG["hotkey"])

        self._tray = self._build_tray()
        self._register_hotkey()

        # Ask for a key only if there genuinely isn't one. Checking config.json
        # alone would nag on every launch even with a good key sitting in .env.
        if not provider_key(self.cfg.get("provider", "groq"), self.cfg):
            self.win.after(800, self.open_settings)

    # ── Settings ──────────────────────────────────────────
    def open_settings(self):
        SettingsDialog(self.win, self.cfg, self._on_cfg_saved)

    def _on_cfg_saved(self, new_cfg: dict):
        self.cfg = new_cfg
        self.win.set_hotkey_label(new_cfg.get("hotkey") or DEFAULT_CONFIG["hotkey"])
        self._unregister_hotkey()
        self._register_hotkey()

    # ── Hotkey ────────────────────────────────────────────
    def _register_hotkey(self):
        hk = (self.cfg.get("hotkey") or "").strip()
        if SmartHook.resolve(hk) is None:
            # Only reachable via a hand-edited config.json — the dialog blocks
            # bad names. Say so out loud rather than listening to the wrong key.
            bad, hk = hk, DEFAULT_CONFIG["hotkey"]
            self.cfg["hotkey"] = hk
            save_config(self.cfg)
            self.win.set_hotkey_label(hk)
            self.win.after(0, lambda b=bad, f=hk: messagebox.showwarning(
                "Yap", f"Hotkey không hỗ trợ: {b!r}\nĐã quay lại {f!r}."))
        self._hook = SmartHook(
            key_name   = hk,
            threshold  = HOLD_THRESHOLD,
            on_press   = self._on_press,
            on_arm     = self._on_arm,
            on_release = self._on_release,
        )
        self._hook.start()
        print(f"Hotkey: [{hk}]  hold {self._hook.threshold}s to record")

    def _unregister_hotkey(self):
        if self._hook:
            self._hook.stop()
            self._hook = None
        # The key may still be physically held: its release belonged to the hook
        # we just killed, so it will never arrive. Close the session ourselves,
        # or the mic stays open and the next hook inherits a stuck _recording.
        self._cancel_recording()

    def _cancel_recording(self):
        with self._lock:
            if not self._recording: return
            self._recording = False
        try:
            self._recorder.stop()      # audio discarded — never armed for us
        except Exception:
            traceback.print_exc()
        self._set_state("idle")

    # ── Recording ─────────────────────────────────────────
    def _error(self, title: str, exc: Exception):
        # Freeze the text now: Python deletes the `except ... as e` name when the
        # block ends, so a lambda closing over it raises NameError instead of
        # ever showing the real cause.
        msg = str(exc)
        self.win.after(0, lambda m=msg: messagebox.showerror("Yap", f"{title}:\n{m}"))

    def _on_press(self):
        """Key down — open the mic straight away so the first word survives."""
        # Capture the target NOW, before the waveform bar appears: showing a
        # window can change which window is in front, and we must not end up
        # pasting into our own bar.
        self._target_hwnd = self._foreground_hwnd()
        with self._lock:
            if self._recording: return
            self._recording = True
        try:
            self._recorder.start()
        except Exception as exc:
            with self._lock: self._recording = False
            self._error("Mic error", exc)

    def _on_arm(self):
        """Held past the threshold — this is dictation, not a stray tap."""
        with self._lock:
            if not self._recording: return
        self._set_state("recording")

    def _on_release(self, armed: bool):
        target = self._target_hwnd
        with self._lock:
            if not self._recording: return
            self._recording = False
        try:
            audio = self._recorder.stop()
        except Exception as exc:
            self._set_state("idle")
            self._error("Mic error", exc)
            return
        if not armed:
            # Tap, not a hold — the user never meant to dictate. Drop it.
            self._set_state("idle"); return
        if not audio:
            self._set_state("idle"); return

        # Don't pay for silence: a clip this short or this quiet has no speech
        # in it, and Whisper will happily invent something from room tone.
        duration, rms = wav_stats(audio)
        if duration < MIN_DURATION:
            print(f"[skip] too short: {duration:.2f}s")
            self._flash_state("too short"); return
        if rms < MIN_RMS:
            print(f"[skip] no speech: rms={rms:.0f} over {duration:.2f}s")
            self._flash_state("no speech"); return

        self._set_state("transcribing")
        threading.Thread(target=self._transcribe, args=(audio, target),
                         daemon=True).start()

    def _transcribe(self, audio: bytes, target_hwnd=None):
        try:
            text = self._transcriber.transcribe(audio, self.cfg)
            # Re-check before EACH side effect, not once up front: quit() can
            # land while _paste is waiting, and a dead app must not type.
            if text and not self._shutdown.is_set():
                self._paste(text, target_hwnd)
            if text and not self._shutdown.is_set():
                self._save_hist(text)
                ts = datetime.now().strftime("%d/%m %H:%M")
                try:
                    self.win.after(0, lambda t=text, s=ts: self.win.add_entry(t, s))
                except Exception:
                    pass
        except Exception as exc:
            if not self._shutdown.is_set():
                self._error("Transcription error", exc)
        finally:
            self._set_state("idle")

    @staticmethod
    def _foreground_hwnd():
        """Front window, unless it is one of ours — pasting into our own bar
        would swallow the text instead of typing it where the user is."""
        try:
            import win32gui, win32process
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return None if pid == os.getpid() else hwnd
        except Exception:
            traceback.print_exc()
            return None

    @staticmethod
    def _modifiers_held() -> bool:
        """Is the user physically holding Ctrl / Shift / Alt / Win right now?"""
        u32 = ctypes.windll.user32
        for vk in (0x11, 0x10, 0x12, 0x5B, 0x5C):   # CONTROL SHIFT MENU LWIN RWIN
            if u32.GetAsyncKeyState(vk) & 0x8000:
                return True
        return False

    def _paste(self, text: str, target_hwnd=None):
        import win32api, win32con, win32gui
        u32 = ctypes.windll.user32
        CF_UNICODETEXT = 13

        def target_ok() -> bool:
            """Fail CLOSED: on any doubt we leave the text on the clipboard
            rather than risk typing it into the wrong window."""
            if not target_hwnd:
                return False
            try:
                return (bool(win32gui.IsWindow(target_hwnd)) and
                        win32gui.GetForegroundWindow() == target_hwnd)
            except Exception:
                traceback.print_exc()
                return False

        def bail(label):
            pyperclip.copy(text)
            self._flash_state(label)

        # 1. Still the window you were speaking into? Transcription takes a
        #    second or two, and people alt-tab.
        if not target_ok():
            return bail("copied — window changed")

        # 2. Don't fire Ctrl+V under a modifier the user is holding —
        #    Ctrl+Shift+V and Ctrl+Alt+V mean something else entirely.
        waited = 0.0
        while self._modifiers_held() and waited < PASTE_WAIT:
            time.sleep(0.05); waited += 0.05
        if self._modifiers_held():
            return bail("copied — keys held")

        # Focus can have moved during that wait.
        if not target_ok():
            return bail("copied — window changed")
        if self._shutdown.is_set():
            return

        # 3. Borrow the clipboard. Only plain text can be given back — see the
        #    limitation noted in README; an image or a file list is lost.
        saved = None
        lost_other = False
        try:
            if u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                saved = pyperclip.paste()
            elif u32.CountClipboardFormats():
                lost_other = True
        except Exception:
            traceback.print_exc()

        pyperclip.copy(text)
        our_seq = u32.GetClipboardSequenceNumber()
        time.sleep(0.15)

        if self._shutdown.is_set():
            return
        if not target_ok():
            return bail("copied — window changed")

        ctrl_down = v_down = False
        try:
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0); ctrl_down = True
            win32api.keybd_event(ord('V'), 0, 0, 0);            v_down = True
            time.sleep(0.05)
        finally:
            # Release only what we actually pressed, and never let a failure to
            # lift V leave Ctrl stuck down across the whole machine.
            try:
                if v_down:
                    win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            finally:
                if ctrl_down:
                    win32api.keybd_event(win32con.VK_CONTROL, 0,
                                         win32con.KEYEVENTF_KEYUP, 0)

        if saved is not None and saved != text:
            time.sleep(0.35)   # let the target app finish reading the clipboard
            try:
                # Sequence number, not content: two different things can hold
                # identical text, and comparing text would clobber a fresh copy.
                if u32.GetClipboardSequenceNumber() == our_seq:
                    pyperclip.copy(saved)
            except Exception:
                traceback.print_exc()
        elif lost_other:
            self._flash_state("clipboard replaced")

    def _save_hist(self, text: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._hist_lock:
            self.history.append({"text": text, "timestamp": ts})
            save_history(self.history)

    def _set_state(self, state: str):
        if self._shutdown.is_set(): return
        self.state = state
        try:
            self.win.after(0, lambda s=state: self.win.set_state(s))
        except Exception:
            pass   # window destroyed between the check above and here

    def _flash_state(self, label: str, seconds: float = 1.4):
        """Say why nothing happened, without a modal box in the user's face."""
        with self._lock:
            self._flash_gen += 1
            gen = self._flash_gen
        self._set_state(label)
        def back():
            # Generation, not label: two flashes of the same text in a row must
            # not have the first one cutting the second one short.
            if self._flash_gen == gen and not self._shutdown.is_set():
                self._set_state("idle")
        t = threading.Timer(seconds, back); t.daemon = True; t.start()

    def _build_tray(self):
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse([8, 8, 56, 56], fill=(139, 92, 246, 255))
            icon = pystray.Icon("Yap", img, "Yap — Push to talk")
            icon.menu = pystray.Menu(
                pystray.MenuItem("Show", lambda: self.win.after(0, self.win.show)),
                pystray.MenuItem("Lich su", lambda: self.win.after(0, self.win._open_history)),
                pystray.MenuItem("Settings", lambda: self.win.after(0, self.open_settings)),
                pystray.MenuItem("Quit", lambda: self.win.after(0, self.quit)),
            )
            threading.Thread(target=icon.run, daemon=True).start()
            return icon
        except Exception as e:
            print(f"Tray: {e}")
            return None

    def quit(self):
        # Set first: an in-flight transcription must not come back after this
        # and paste into whatever the user is doing, or touch a dead window.
        self._shutdown.set()
        self._unregister_hotkey()      # also closes a recording still running
        self.win._alive = False
        if self._tray:
            try: self._tray.stop()
            except Exception: traceback.print_exc()
        try: self._recorder.stop()     # belt and braces if a stream survived
        except Exception: pass
        self.win.destroy()

    def run(self):
        self.win.mainloop()


# ═══════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    _instance_lock = acquire_single_instance()
    if _instance_lock is None:
        ctypes.windll.user32.MessageBoxW(
            None,
            "Yap đang chạy rồi.\n\nTìm biểu tượng Yap ở khay hệ thống "
            "(góc dưới phải màn hình).",
            "Yap", 0x40)          # MB_ICONINFORMATION
        sys.exit(0)
    try:
        app = YapApp()
        app.run()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit...")
