#!/usr/bin/env python3
"""
Yap for Windows v3 — Premium Push-to-Talk Dictation
Dark purple theme | Frameless | Glow animations
"""

import sys, os, io, json, time, wave, threading, math, ctypes, queue, traceback, difflib, re
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
CORRECT_FILE = CONFIG_DIR / "corrections.json"

# Whisper copies the STYLE of this text, not just its vocabulary. So the hint
# is written as real code-switched sentences: that is what teaches it "this
# speaker mixes Vietnamese and English, and English words stay in English".
# A bare word list alone still let "Ctrl" come back as "căn chuồn".
DEFAULT_PROMPT = (
    "Anh review lại cái commit này giúp em, xong thì push lên branch main. "
    "Mình cần fix cái bug ở workflow n8n trước deadline rồi deploy production. "
    "Let me know if the API key is still valid, tôi sẽ check lại trong file config. "
    "Chú mở terminal chạy cái script Python đó, nhớ backup database trước. "
    "Bấm Ctrl, Alt, Shift, Enter, Tab, Esc. "
    "Tên hay dùng: Claude, Codex, Linear, GitHub, Shopify, Klaviyo, Printify, "
    "WordPress, Etsy, Meta, YouTube, Chrome, Excel."
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

# Bao nhieu cau vua noi duoc nhet vao mo. Whisper bam theo ngu canh gan: dang
# noi ve Shopify thi cau sau nghieng ve tu vung Shopify.
RECENT_CONTEXT   = 2
RECENT_MAX_CHARS = 160   # mot cau dai khong duoc an het ngan sach mo

# Groq TU CHOI thang neu mo dai qua — khong cat bot, ma tra loi 400.
# Va no dem BYTE UTF-8, khong dem ky tu: 773 ky tu tieng Viet = 901 byte, vi
# moi chu co dau ton 2-3 byte. Dem bang len() la hut mot phan tu.
MAX_PROMPT_BYTES = 880

# Kho sua loi: nguoi dung sua mot lan trong cua so Lich su, app nho mai.
CORRECT_BYTES    = 200   # phan ngan sach mo danh cho tu da sua
CORRECT_MAX_WORDS = 4    # cum dai hon thi la viet lai cau, khong phai sua tu
AUTO_MIN_CHARS   = 5     # ngan hon va chi mot tu thi chi moi, khong thay tay
CONTEXT_GROW     = 3     # so lan noi cum ra hai ben cho du dac trung

# Cham nhanh hai lan = mo Lich su. Thanh song chi hien luc dang giu phim, va
# Windows giau icon khay moi cai — khong co cai nay thi khong vao duoc.
DOUBLE_TAP = 0.6

# Normal users paste the key in Settings (saved to config.json). A key in this
# project's .env still wins - the dev / override path - and Settings says so.
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


def load_corrections() -> dict:
    """{nghe nhầm: đúng}. Người dùng sửa một lần, app nhớ mãi."""
    if CORRECT_FILE.exists():
        try:
            d = json.loads(CORRECT_FILE.read_text("utf-8"))
            return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)}
        except Exception:
            traceback.print_exc()
    return {}


def save_corrections(c: dict) -> None:
    _write_atomic(CORRECT_FILE, json.dumps(c, indent=2, ensure_ascii=False))


_STRIP = " 	.,!?;:\"'()[]…"


def learn_corrections(before: str, after: str) -> list:
    """So bản máy nghe với bản người sửa, rút ra các cặp (nhầm, đúng).

    Chỉ nhận thay thế ngắn. Một cụm dài bị đổi thường là người dùng viết lại
    câu cho gọn, không phải máy nghe sai — học cái đó vào là hỏng về sau.
    """
    a, b = before.split(), after.split()
    pairs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag != "replace":
            continue
        if i2 - i1 > CORRECT_MAX_WORDS or j2 - j1 > CORRECT_MAX_WORDS:
            continue                  # viết lại cả câu, không phải sửa từ

        # Cụm quá ngắn thì NỚI RA HAI BÊN thay vì vứt đi. Sửa "nỗi"→"lỗi" một
        # mình là nguy hiểm (phá "nỗi buồn"), nhưng "bị nỗi nhiều"→"bị lỗi
        # nhiều" thì an toàn. Nhờ vậy học được đúng loại lỗi hay gặp nhất.
        lo, hi, dlo, dhi = i1, i2, j1, j2
        for _ in range(CONTEXT_GROW):
            wrong = " ".join(a[lo:hi]).strip(_STRIP)
            if auto_safe(wrong):
                break
            if lo > 0 and dlo > 0:            # lấy thêm một từ bên trái
                lo -= 1; dlo -= 1
            elif hi < len(a) and dhi < len(b):  # hoặc bên phải
                hi += 1; dhi += 1
            else:
                break

        wrong = " ".join(a[lo:hi]).strip(_STRIP)
        right = " ".join(b[dlo:dhi]).strip(_STRIP)
        if not wrong or not right or wrong.casefold() == right.casefold():
            continue
        if len(wrong) < 3:
            continue
        pairs.append((wrong, right))
    return pairs


def auto_safe(wrong: str) -> bool:
    """Cụm này có đủ đặc trưng để thay tự động không?

    Một từ ngắn thì KHÔNG. Học "ông"→"không" rồi thay khắp nơi sẽ biến
    "ông ấy đi rồi" thành "không ấy đi rồi"; học "xác"→"để" làm hỏng
    "chính xác". Những cặp đó vẫn được mồi cho Whisper, nhưng không thay tay.
    """
    return len(wrong.split()) >= 2 or len(wrong) >= AUTO_MIN_CHARS


def apply_corrections(text: str, corr: dict) -> str:
    """Thay các cụm đã học. Khớp theo BIÊN TỪ để 'ông' không ăn vào 'không'."""
    if not text or not corr:
        return text
    for wrong in sorted(corr, key=len, reverse=True):   # cụm dài ưu tiên
        if not auto_safe(wrong):
            continue                                    # chỉ mồi, không thay
        # Thay bằng lambda, không bằng chuỗi: một bản sửa chứa \1 hay \g sẽ bị
        # re.sub hiểu thành backreference và ném lỗi giữa lúc đang dùng.
        right = corr[wrong]
        text = re.sub(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)",
                      lambda _m, r=right: r, text, flags=re.IGNORECASE)
    return text


# Whisper large-v3 hoc tu hang trieu video YouTube. Gap doan im lang hay tieng
# phong, no KHONG tra ve rong — no lap cho trong bang cau outro quen thuoc nhat.
# Day la artifact cua model, khong tat duoc bang tham so; phai loc o dau ra.
#
# Neo `^` la thu giu an toan: chi bo cau NGUYEN VEN la outro. Nguoi dung noi
# "co cai phan cac ban nho like va share ... la sao nhi?" thi cau do bat dau
# bang "co cai phan" nen khong khop — noi that ve outro khong bi an mat.
HALLUCINATION_RE = re.compile(
    r"^\W*(?:"

    # Loi keu goi like/share/subscribe. Dieu kien "kênh" la thu giu an toan:
    # KHONG co no thi "Share cho anh cai link Drive" hay "Dang ky cho anh mot
    # tai khoan Groq" — cau nguoi that noi hang ngay — bi an oan. Da thu, da
    # thay 3 cau nhu vay bien mat truoc khi them dieu kien nay.
    r"(?=[^.!?]*\b(?:kênh|channel)\b)"
    r"(?:(?:hãy|nhớ|có\s+thể|đừng\s+quên|các\s+bạn|mọi\s+người|quý\s+vị|please)[\s,]+){0,4}"
    r"(?:like|đăng\s*ký|subscribe|share|chia\s*sẻ|ủng\s*hộ|theo\s*dõi)\b.*"

    # Cac cau outro co dang co dinh — khong can dieu kien "kênh".
    r"|cảm\s*ơn\s+(?:các\s+bạn|mọi\s+người|quý\s+vị)\s+đã\s+(?:theo\s*dõi|xem|lắng\s*nghe).*"
    r"|hẹn\s+gặp\s+lại\s+(?:các\s+bạn|mọi\s+người|quý\s+vị|trong)\b.*"
    r"|ghiền\s+mì\s+gõ\b.*"
    r"|phụ\s*đề\s+(?:được\s+)?(?:thực\s+hiện|dịch)\s+bởi\b.*"

    # Tieng Anh: doi dung cap "like ... subscribe", vi "Subscribe cho anh cai
    # newsletter" la cau that. "Thanks for watching" thi khong the la cau that.
    r"|thanks?\s+(?:you\s+)?for\s+watching\b.*"
    r"|(?:don't\s+forget\s+to\s+|please\s+)?like[\s,]+(?:and\s+)?subscribe\b.*"

    r")\W*$",
    re.IGNORECASE,
)

# Tach cau theo dau ket cau. Outro luon la mot cau tron, nen don vi loc la cau —
# loc theo cum se an vao giua cau that.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def strip_hallucination(text: str) -> str:
    """Bo nhung CAU do Whisper bia ra tu doan im lang.

    Bo o BAT KY vi tri nao, khong chi cuoi: mot khoang lang GIUA luc doc chinh
    ta cung de no chen cau outro vao giua hai y that.

    Cai bi bo duoc IN RA, khong nuot im lang — nuot im lang thi lan sau mat
    chu that cung khong ai biet.
    """
    if not text:
        return text
    kept, dropped = [], []
    for s in _SENTENCE_SPLIT.split(text.strip()):
        (dropped if s.strip() and HALLUCINATION_RE.match(s) else kept).append(s)
    if dropped:
        print("[loc] bo cau Whisper bia: " + " | ".join(d.strip() for d in dropped))
    return " ".join(k for k in kept if k.strip()).strip()


def _nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


def _fit_bytes(s: str, budget: int) -> str:
    """Cắt chuỗi cho vừa `budget` byte UTF-8, không cắt giữa một ký tự."""
    b = s.encode("utf-8")
    if len(b) <= budget:
        return s
    return b[:budget].decode("utf-8", "ignore")


def build_prompt(cfg: dict, history: list, corr: dict = None) -> str:
    """Mồi gửi cho Whisper = vài câu vừa nói + danh sách từ vựng.

    Whisper chỉ giữ **224 token CUỐI** của prompt. Nên từ vựng đặt sau cùng để
    luôn sống sót; ngữ cảnh gần đứng trước, bị cắt cũng không mất gì cốt lõi.
    """
    # Tu da sua tay dat CUOI cung: dung nhat vi chinh nguoi dung day, va Whisper
    # coi trong phan duoi cua mo nhat.
    fixed = ""
    if corr:
        seen, words = set(), []
        for right in reversed(list(corr.values())):
            k = right.casefold()
            if k not in seen:
                seen.add(k); words.append(right)
        fixed = _fit_bytes(", ".join(words), CORRECT_BYTES).rstrip(", ")
        if fixed:
            fixed = " " + fixed + "."

    budget = MAX_PROMPT_BYTES - _nbytes(fixed)
    vocab  = _fit_bytes((cfg.get("prompt") or "").strip(), budget)

    # Tu vung duoc uu tien: nguoi dung tu soan, va no la thu sua duoc "Ctrl".
    # Ngu canh chi lap phan con thua — het cho thi bo, khong bao gio tran.
    room   = budget - _nbytes(vocab)
    recent = []
    for item in reversed(history[-RECENT_CONTEXT:]):        # moi nhat truoc
        # Loc lai o day nua: history.json cua ban cu da co cau bia nam san.
        # Khong loc thi cau bia lai duoc mom cho Whisper -> no bia tiep -> lai
        # vao lich su. Chinh vong lap do la thu sinh ra loi nay.
        t = strip_hallucination((item.get("text") or "").strip())[:RECENT_MAX_CHARS]
        if not t or _nbytes(t) + 1 > room:
            continue
        recent.insert(0, t)                                  # giu dung thu tu
        room -= _nbytes(t) + 1

    out = " ".join(recent + ([vocab] if vocab else [])) + fixed
    assert _nbytes(out) <= MAX_PROMPT_BYTES, f"mo {_nbytes(out)} byte, vuot tran"
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


# .env beating a key pasted in Settings used to be silent: the user saw "wrong
# key" with no way to guess why. Shown only when .env really has a key, so the
# empty .env the installer creates never scares anyone.
ENV_OVERRIDE_NOTE = "⚠ Đang dùng key từ .env, ô này bị bỏ qua."


def key_note(provider: str, cfg: dict) -> str:
    """The line under the key box in Settings."""
    return {
        "env":    f"{ENV_OVERRIDE_NOTE}\n({ENV_FILE})",
        "config": "✓ Đã lưu key.",
        "none":   "Chưa có key. Dán key vào ô trên rồi bấm Save & Apply.",
    }[key_source(provider, cfg)]


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
    # use_last_error=True + get_last_error(): ctypes chụp mã lỗi NGAY tại lời
    # gọi. Gọi kernel32.GetLastError() riêng ra thì Python có thể đã gọi Win32
    # API khác ở giữa và xoá mất mã — khoá im lặng không chặn được ai.
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype  = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    handle = k32.CreateMutexW(None, False, f"Local\\{APP_NAME}-SingleInstance")
    err = ctypes.get_last_error()
    if not handle or err == ERROR_ALREADY_EXISTS:
        print(f"[instance] da co ban khac dang chay (err={err})")
        return None
    print(f"[instance] pid {os.getpid()} giu khoa")
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
        self._drops = 0         # so lan PortAudio bao tran/mat mau

    def start(self) -> None:
        # Walk the candidates until one really opens AND starts. Never let the
        # quality preference cost us the ability to record at all.
        self._frames = []
        self._drops  = 0
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
        """Callback thời gian thực: CHỈ sao chép, không tính toán gì.

        Bản trước tính RMS ngay tại đây — mỗi block một lần cấp phát mảng
        float32 mới. PortAudio không chờ: callback chậm là nó báo
        `input_overflow` và VỨT các mẫu tiếp theo. Mất 30-100ms là mất trọn
        một phụ âm, nên nói chậm thì chép đúng mà nói nhanh thì sai.
        """
        if status:
            self._drops += 1          # gần như luôn là input_overflow
        if not self.recording:
            return
        self._frames.append(indata.copy())

    @property
    def level(self) -> float:
        """Mức âm cho thanh sóng, tính ở luồng đọc chứ không ở callback."""
        try:
            blk = self._frames[-1]
        except IndexError:
            return 0.0
        if blk.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(blk.astype(np.float32) ** 2)))
        return min(1.0, rms / 4000.0)

    def stop(self) -> Optional[bytes]:
        self.recording = False
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
            raise ValueError(
                "Chưa có API key.\n\nMở Settings (chuột phải icon Yap ở khay → Settings), "
                "dán key vào ô API KEY rồi bấm Save & Apply.\n\n"
                "Lấy key free ở: console.groq.com/keys"
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
        # temperature=0: buoc Whisper lay duong giai ma chac chan nhat.
        # De mac dinh, no duoc phep "sang tao" khi khong nghe ro —
        # dung la luc no de ra cau outro YouTube.
        p = {"file": f, "model": model, "response_format": "json",
             "temperature": 0}
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
        provider = self.cfg.get("provider", "groq")
        src = key_source(provider, self.cfg)
        ctk.CTkLabel(ac, text=key_note(provider, self.cfg), font=("Segoe UI", 10),
                     justify="left", wraplength=420,
                     text_color={"env": RED, "config": GREEN}.get(src, DIM)).pack(
            anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(ac, text="Get free key at  console.groq.com/keys",
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
        self._hist_win = HistoryWindow(self, self.history, self.app_ref)

    def _open_settings(self, e=None):
        if self.app_ref:
            self.app_ref.open_settings()

    def _quit(self):
        if self.app_ref:
            self.app_ref.quit()


class HistoryWindow(ctk.CTkToplevel):
    """The transcript log, no longer crowding the bar. Click a row to copy."""

    def __init__(self, parent, history, app_ref=None):
        super().__init__(parent)
        self.app_ref = app_ref
        self.title("Lich su - Yap")
        self.geometry("460x600")
        self.configure(fg_color=BG)
        self.attributes("-topmost", True)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(bar, text="Nhấp = copy   ·   Nhấp đúp = sửa (app sẽ nhớ)",
                     font=("Segoe UI", 10), text_color=DIM).pack(side="left")
        self._fix_btn = ctk.CTkButton(
            bar, text="Đã học 0", width=92, height=26, corner_radius=8,
            font=("Segoe UI", 10), fg_color=BG3, hover_color=BORDER2,
            text_color=DIM, command=self._show_learned)
        self._fix_btn.pack(side="right")

        self._list = ctk.CTkScrollableFrame(
            self, fg_color=BG, scrollbar_button_color=BG3,
            scrollbar_button_hover_color=BORDER2)
        self._list.pack(fill="both", expand=True, padx=8, pady=8)
        self._refresh_count()
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
        body = ctk.CTkLabel(row, text=text, font=("Segoe UI", 11), text_color=TEXT,
                            wraplength=380, justify="left")
        body.pack(anchor="w", padx=12, pady=(2, 7))
        row._body, row._text, row._ts = body, text, ts

        def edit(_=None):
            self._open_editor(row)


    # -- sua va hoc -------------------------------------------------
    def _refresh_count(self):
        n = len(self.app_ref.corrections) if self.app_ref else 0
        self._fix_btn.configure(text=f"Da hoc {n}")

    def _open_editor(self, row):
        """Hop sua mot dong. Luu xong thi app rut ra cap (nham -> dung)."""
        d = ctk.CTkToplevel(self)
        d.title("Sua ban chep")
        d.geometry("520x260")
        d.configure(fg_color=BG)
        d.attributes("-topmost", True)
        d.after(60, d.lift)

        ctk.CTkLabel(d, text="May nghe thanh:", font=("Segoe UI", 10),
                     text_color=DIM).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(d, text=row._text, font=("Segoe UI", 10), text_color=DIM2,
                     wraplength=480, justify="left").pack(anchor="w", padx=16)

        ctk.CTkLabel(d, text="Sua lai cho dung:", font=("Segoe UI", 10),
                     text_color=DIM).pack(anchor="w", padx=16, pady=(12, 2))
        box = ctk.CTkTextbox(d, height=80, font=("Segoe UI", 12), fg_color=BG3,
                             border_color=BORDER2, border_width=1,
                             text_color=TEXT, wrap="word")
        box.pack(fill="x", padx=16)
        box.insert("1.0", row._text)
        box.focus_set()

        def save():
            after = box.get("1.0", "end").strip()
            d.destroy()
            if not after or after == row._text:
                return
            self._commit_edit(row, after)

        btns = ctk.CTkFrame(d, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(btns, text="Luu va ghi nho", height=36, corner_radius=10,
                      font=("Segoe UI", 12, "bold"), fg_color=PURPLE,
                      hover_color=PURPLED, command=save).pack(side="left")
        ctk.CTkButton(btns, text="Thoi", height=36, width=80, corner_radius=10,
                      font=("Segoe UI", 12), fg_color=BG3, hover_color=BORDER2,
                      text_color=DIM, command=d.destroy).pack(side="left", padx=8)

    def _commit_edit(self, row, after):
        before = row._text
        learned = self.app_ref.learn_from_edit(before, after, row._ts) if self.app_ref else []
        row._text = after
        row._body.configure(text=after)
        self._refresh_count()
        if learned:
            msg = chr(10).join(
                f'  "{w}"  ->  "{r}"'
                + ("" if auto_safe(w) else "   (chi nhac may, khong tu thay)")
                for w, r in learned)
            messagebox.showinfo(
                "Yap",
                f"Da ghi nho {len(learned)} cho sua:{chr(10)}{chr(10)}{msg}",
                parent=self)
        else:
            messagebox.showinfo(
                "Yap", "Da sua trong lich su, nhung khong rut ra duoc cap tu nao "
                       "de hoc (doan sua qua dai hoac qua ngan).", parent=self)

    def _show_learned(self):
        corr = dict(self.app_ref.corrections) if self.app_ref else {}
        d = ctk.CTkToplevel(self)
        d.title("Nhung cho da hoc")
        d.geometry("470x520")
        d.configure(fg_color=BG)
        d.attributes("-topmost", True)
        d.after(60, d.lift)
        if not corr:
            ctk.CTkLabel(d, text="Chua hoc duoc gi." + chr(10) * 2 +
                                 "Nhap dup mot dong trong Lich su" + chr(10) +
                                 "roi sua lai cho dung.",
                         font=("Segoe UI", 12), text_color=DIM,
                         justify="center").pack(expand=True)
            return
        lst = ctk.CTkScrollableFrame(d, fg_color=BG, scrollbar_button_color=BG3)
        lst.pack(fill="both", expand=True, padx=10, pady=10)
        for wrong, right in reversed(list(corr.items())):
            r = ctk.CTkFrame(lst, fg_color=BG2, corner_radius=10,
                             border_width=1, border_color=BORDER)
            r.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(r, text=wrong, font=("Segoe UI", 11), text_color=RED,
                         wraplength=280, justify="left").pack(
                side="left", padx=(12, 4), pady=8)
            ctk.CTkLabel(r, text="->", font=("Segoe UI", 10),
                         text_color=DIM).pack(side="left")
            ctk.CTkLabel(r, text=right, font=("Segoe UI", 11, "bold"),
                         text_color=GREEN if auto_safe(wrong) else BLUE,
                         wraplength=140, justify="left").pack(side="left", padx=4)
            if not auto_safe(wrong):
                ctk.CTkLabel(r, text="chi nhac", font=("Segoe UI", 9),
                             text_color=DIM2).pack(side="left", padx=4)

            def drop(_=None, w=wrong, frame=r):
                self.app_ref.forget_correction(w)
                frame.destroy()
                self._refresh_count()
            ctk.CTkButton(r, text="x", width=26, height=26, corner_radius=6,
                          font=("Segoe UI", 11), fg_color=BG3,
                          hover_color=RED, text_color=DIM,
                          command=drop).pack(side="right", padx=8)

        def copy(_=None):
            pyperclip.copy(text)
            row.configure(fg_color=blend(BG2, PURPLE, 0.35))
            row.after(250, lambda: row.configure(fg_color=BG2))

        for w in [row] + list(row.winfo_children()):
            w.bind("<Button-1>", copy)
            w.bind("<Double-Button-1>", edit)
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
        self._last_tap    = 0.0
        self.corrections  = load_corrections()
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
            # But two quick taps opens History: the bar only exists while you
            # hold the key, and Windows hides new tray icons, so without this
            # there is no reachable way in.
            now = time.time()
            if now - self._last_tap < DOUBLE_TAP:
                self._last_tap = 0.0
                self.win.after(0, self.win._open_history)
            else:
                self._last_tap = now
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

        # Ghi lai de con doi chieu khi chep sai: tin hieu qua nho hay qua to
        # (vo tieng) deu lam Whisper doan bua, nhat la khi noi nhanh.
        peak = 0
        try:
            with wave.open(io.BytesIO(audio), "rb") as _wf:
                _s = np.frombuffer(_wf.readframes(_wf.getnframes()), dtype=np.int16)
                peak = int(np.abs(_s).max()) if _s.size else 0
        except Exception:
            pass
        drops = getattr(self._recorder, "_drops", 0)
        print(f"[audio] {duration:.2f}s  rms={rms:.0f}  dinh={peak}"
              f" ({peak / 327.68:.0f}% thang do)"
              f"{'  <-- VO TIENG' if peak >= 32700 else ''}"
              f"{f'  <-- MAT MAU x{drops}' if drops else ''}")

        self._set_state("transcribing")
        threading.Thread(target=self._transcribe, args=(audio, target),
                         daemon=True).start()

    def _transcribe(self, audio: bytes, target_hwnd=None):
        try:
            cfg = dict(self.cfg)
            with self._hist_lock:
                cfg["prompt"] = build_prompt(self.cfg, self.history, self.corrections)
            text = self._transcriber.transcribe(audio, cfg)
            text = apply_corrections(text, self.corrections)
            # Truoc _paste VA truoc _save_hist: chan ca hai duong. Neu chi chan
            # duong dan thi cau bia van vao lich su roi quay lai mom Whisper.
            text = strip_hallucination(text)
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

    # ── Học từ chỗ người dùng sửa ─────────────────────────
    def learn_from_edit(self, before: str, after: str, ts: str) -> list:
        """Ghi bản sửa vào lịch sử, và rút ra các cặp (nghe nhầm → đúng)."""
        with self._hist_lock:
            for item in self.history:
                if item.get("timestamp") == ts and item.get("text") == before:
                    item["text"] = after
                    break
            save_history(self.history)

        learned = []
        for wrong, right in learn_corrections(before, after):
            # Không học ngược lại chính bản sửa của mình: nếu "đúng" lại là một
            # vế "nhầm" đã có, hai luật sẽ đá nhau mỗi lần chép lời.
            if right in self.corrections:
                continue
            self.corrections[wrong] = right
            learned.append((wrong, right))
        if learned:
            save_corrections(self.corrections)
            print(f"[hoc] {learned}")
        return learned

    def forget_correction(self, wrong: str):
        if self.corrections.pop(wrong, None) is not None:
            save_corrections(self.corrections)

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
