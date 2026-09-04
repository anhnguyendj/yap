# Kiến trúc tổng thể

Một tiến trình, một file `app.py`. Không có server, không có database — trạng
thái nằm ở hai file JSON trong `%APPDATA%\YapWindows\` và một `.env` cạnh code.

## Luồng dữ liệu

```
      phím vật lý (Right Ctrl)
              │
              ▼
   ┌──────────────────────┐   poll 5ms, KHÔNG chặn phím
   │ SmartHook            │   → hotkey.md
   │  poll thread         │
   │  dispatch thread     │   một hàng đợi, callback chạy đúng thứ tự
   └──────────┬───────────┘
              │  on_press          on_arm            on_release(armed)
              ▼                       │                    │
   ┌──────────────────────┐           │                    │
   │ AudioRecorder        │◄──────────┘                    │
   │  mở mic NGAY lúc nhấn│  (armed → UI hiện thanh sóng)  │
   │  thu ở tần số GỐC    │                                 │
   └──────────┬───────────┘◄────────────────────────────────┘
              │  WAV bytes                      → audio.md
              ▼
   ┌──────────────────────┐   duration < 0.35s  → bỏ
   │ cổng wav_stats()     │   rms < 80          → bỏ    KHÔNG gọi API
   └──────────┬───────────┘
              │  qua cổng
              ▼
   ┌──────────────────────┐   Groq whisper-large-v3
   │ Transcriber          │   + prompt mồi từ vựng Anh-Việt
   └──────────┬───────────┘                     → transcription.md
              │  text
              ▼
   ┌──────────────────────┐   3 cổng, fail-closed
   │ _paste()             │   ① đúng cửa sổ?  ② modifier đã nhả?
   │                      │   ③ mượn clipboard rồi trả lại
   └──────────┬───────────┘                     → paste.md
              │
              ├──► Ctrl+V vào cửa sổ đích
              └──► history.json  +  cửa sổ Lịch sử
```

## Các thành phần

| Thành phần | Vai trò | Tài liệu |
|---|---|---|
| `SmartHook` | Nghe phím nóng, phát 3 sự kiện | [hotkey.md](hotkey.md) |
| `AudioRecorder`, `input_candidates`, `wav_stats` | Thu âm, chọn thiết bị, cổng chặn | [audio.md](audio.md) |
| `Transcriber` | Gọi Groq/OpenAI, mồi từ vựng | [transcription.md](transcription.md) |
| `YapApp._paste` | Đưa text vào cửa sổ đích an toàn | [paste.md](paste.md) |
| `load_env`, `load_config`, `_write_atomic` | Key và cấu hình | [config-and-secrets.md](config-and-secrets.md) |
| `MainWindow`, `HistoryWindow`, `SettingsDialog` | Giao diện | [ui.md](ui.md) |
| `acquire_single_instance`, `YapApp.quit` | Vòng đời tiến trình | [lifecycle.md](lifecycle.md) |

## Máy trạng thái

`YapApp.state` có 3 trạng thái chính, cộng các nhãn thông báo tạm thời:

```
idle ──on_press──► (đang thu, chưa hiện gì)
                      │
                      ├─ nhả trước 0.4s ──────────────► idle   (vứt audio)
                      │
                      └─ giữ quá 0.4s ──► recording ──► transcribing ──► idle
                                          (hiện UI)      (gọi API)
```

Nhãn tạm (hiện 1.4s rồi về `idle`): `too short`, `no speech`,
`copied — window changed`, `copied — keys held`, `clipboard replaced`.
Chúng thay thế thanh sóng bằng một dòng chữ — người dùng luôn biết vì sao
không có text hiện ra, thay vì im lặng.

## Mô hình luồng (thread)

| Luồng | Việc | Ràng buộc |
|---|---|---|
| Main (tkinter) | Vẽ, mọi thao tác widget | Chỉ luồng này được đụng tkinter |
| `SmartHook-Poll` | Đọc `GetAsyncKeyState` mỗi 5ms | Chỉ đẩy sự kiện vào queue |
| `SmartHook-Dispatch` | Chạy callback tuần tự | Một luồng duy nhất → giữ đúng thứ tự |
| PortAudio callback | Gom frame, tính mức âm | Không được block |
| `_transcribe` (mỗi lần) | Gọi API rồi paste | Kiểm `_shutdown` trước mỗi tác dụng phụ |

Luồng nền chạm UI qua `win.after(0, ...)`. Khoá: `_lock` (trạng thái ghi âm),
`_hist_lock` (ghi lịch sử). Không có đường khoá chéo.

## Điều chưa làm

- Chưa tuần tự hoá nhiều phiên chồng nhau: nhả phím lần hai lúc lần một còn
  đang gọi API thì hai `_transcribe` chạy song song, dán theo thứ tự API trả về.
- Chưa đưa toàn bộ cập nhật UI qua `queue.Queue` như `SmartHook` đã làm.
