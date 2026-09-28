# Yap for Windows

Hold a key, speak, and your words appear where the cursor is. A push-to-talk
dictation tool for Windows, built for people who mix languages mid-sentence.

## Install in one line

Open **PowerShell** (Start menu → type `powershell`) and paste:

```powershell
irm https://raw.githubusercontent.com/anhnguyendj/yap/main/install.ps1 | iex
```

- **Needs** Windows 10/11. Python 3.10+ is installed for you via `winget` if
  missing (it asks first). Everything goes into `%LOCALAPPDATA%\Yap`, with a
  Yap shortcut on the Desktop and in the Start menu.
- **Key:** the installer opens [console.groq.com/keys](https://console.groq.com/keys)
  (free) and a Notepad with `.env` — paste the key after `GROQ_API_KEY=`, save.
  Run the same line again any time to update; your `.env` and settings are kept.
- **Uninstall:** quit Yap from its tray icon, then delete `%LOCALAPPDATA%\Yap`,
  `%APPDATA%\YapWindows` and the two `Yap` shortcuts.

Nothing sits on your desktop until you speak: a thin waveform bar fades in at
the top of the screen while you hold the key, then disappears.

```
   ╭──────────────────────────────────────────────╮
   │  ▪▪▫▫▮▮▯▯▮▮▮▯▯▫▪▪▫▫▮▮▯▯▮▮▯▯▫▫▪▪▫▫▮▮▯▯▮▮▫▫▪  │
   ╰──────────────────────────────────────────────╯
```

## Why this exists

Most dictation tools assume you speak one language. If you say *"anh review lại
cái commit này rồi push lên GitHub"*, they either mangle the Vietnamese or
transliterate the English — `Ctrl` comes back as `căn chuồn`.

Yap primes Whisper with example sentences in **both** languages, so English
technical terms stay in English inside Vietnamese speech. The vocabulary hint is
editable — add the words your own work is full of.

## Features

- **Push-to-talk** — hold Right Ctrl (configurable), speak, release
- **No lost first word** — the mic opens on key-down, not after the hold threshold
- **Won't paste into the wrong window** — if you alt-tab while it transcribes,
  the text waits on your clipboard instead of landing in someone's chat
- **Gives your clipboard back** — text is borrowed, then restored
- **Won't waste API calls** — clips that are too short or silent never get sent
- **Native-rate capture** — no crude 16 kHz downsample smearing your consonants
- **Live waveform** — real mic levels, not a canned animation
- **Groq Whisper large-v3** (free tier: 2000 min/day) or OpenAI Whisper

## Install from source

For hacking on Yap. Everyone else: use the [one-line install](#install-in-one-line).
Requires **Python 3.10+** on Windows 10/11.

```bat
git clone https://github.com/anhnguyendj/yap.git
cd yap
setup.bat
```

Get a free API key at [console.groq.com](https://console.groq.com) → API Keys →
Create API key. Then:

```bat
copy .env.example .env
```

Open `.env`, paste the key after `GROQ_API_KEY=`, save. No restart needed — the
file is re-read on every transcription.

```bat
run.bat                 :: run with a log window
tao-shortcut.bat        :: put a desktop shortcut there (runs with no console)
```

## Use

1. Click into any text field — Word, Chrome, your terminal
2. **Hold Right Ctrl**, speak, let go
3. The text is pasted at your cursor

A quick tap does nothing, so you cannot trigger it by accident.

When no text appears, the bar tells you why instead of failing silently:

| Message | Meaning |
|---|---|
| `too short` / `no speech` | Hold longer, or speak up — nothing was sent |
| `copied — window changed` | You switched windows; text is on the clipboard |
| `copied — keys held` | You were holding Ctrl/Shift/Alt; press Ctrl+V yourself |
| `clipboard replaced` | An image or file in your clipboard could not be restored |

Right-click the bar (or the tray icon) for **History**, **Settings**, **Quit**.

## Tuning accuracy

Settings has a **vocabulary** box. Add words you say that come out wrong,
comma-separated, spelled the way you want them to appear. Whisper copies the
*style* of that text, so full sentences work better than a bare word list.

Not sure which model or hint works for your voice? Run:

```bat
so-sanh.bat
```

It records six seconds of you talking, then sends that same clip through every
combination of model and vocabulary hint and prints the results side by side.
Your own voice is the only benchmark that counts.

## Configuration

| Where | What |
|---|---|
| `.env` (next to `app.py`) | `GROQ_API_KEY`, `OPENAI_API_KEY` — never committed |
| `%APPDATA%\YapWindows\config.json` | hotkey, model, language, vocabulary hint |
| `%APPDATA%\YapWindows\history.json` | last 100 transcripts |

Pick a hotkey you never type with. The hook does **not** suppress the key, so
`space` would type real spaces into your document. Right Ctrl, F9, Scroll Lock
and Right Alt are all safe.

## Hướng dẫn tiếng Việt

Giữ **Right Ctrl**, nói, thả ra — chữ tự dán vào chỗ con trỏ.

Cài: mở PowerShell, dán đúng một dòng ở mục
[Install in one line](#install-in-one-line). Trình cài mở sẵn trang lấy key free
và Notepad — dán key vào sau `GROQ_API_KEY=`, lưu lại là xong. Chạy lại dòng đó
để cập nhật; key và cài đặt của anh được giữ nguyên.

Nói lẫn tiếng Anh mà máy nghe sai thì vào Settings, mục **TỪ VỰNG**, thêm từ đó
vào — viết đúng dạng anh muốn nó hiện ra. Muốn biết cấu hình nào hợp giọng mình
nhất thì chạy `so-sanh.bat`.

## Architecture

`app.py` is a single file. The design notes live in
[`docs/specs/`](docs/specs/) — start with
[`architecture.md`](docs/specs/architecture.md) for the data flow, then read the
one module you need.

## Contributing

Issues and pull requests welcome. Two things before you send one:

- Run the app and hold the hotkey. There are no automated tests; the only real
  check is that dictation still works end to end.
- Run `quet-key.sh` — it fails the push if a real key would be committed.

`CLAUDE.md` lists the mistakes this project has already paid for. Worth two
minutes before touching the audio or paste paths.

## License

MIT — see [LICENSE](LICENSE).
