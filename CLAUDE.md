# Yap for Windows

Push-to-talk dictation: giữ phím nóng, nói, transcript được dán vào chỗ con trỏ.
Người dùng trộn Việt–Anh liên tục — đó là lưu lượng chính, không phải ngoại lệ.

## Tech stack

Python 3.13 · `sounddevice` · `customtkinter` · `pystray` · `pywin32` ·
Groq Whisper (`groq`), OpenAI tuỳ chọn. Toàn bộ trong `app.py`.

## Lệnh

| Việc | Lệnh |
|---|---|
| Cài | `setup.bat` |
| Chạy (có log) | `run.bat` · chạy nền: `pyw -3 app.py` |
| Kiểm cú pháp | `py -m py_compile app.py` |
| Đo độ chính xác | `so-sanh.bat` |
| Đặt lại shortcut sau khi move | `tao-shortcut.bat` |

Không có test tự động. Mọi thay đổi phải chạy app thật và giữ phím nóng thử.

## Quy chuẩn

- **`py -3`, không phải `python`** trong `.bat` — `python` máy này trỏ venv khác.
- **Không ghim path tuyệt đối** — thư mục sẽ bị move. Dùng `Path(__file__).resolve().parent`.
- **Docs trỏ bằng TÊN KÝ HIỆU, không số dòng** — 10/10 ref `app.py:NNN` cũ đã sai.
- `.bat`: ASCII + CRLF. Key từ `.env`. Comment nói **vì sao**, không tả lại code.

## CẤM lặp lại (đã trả giá)

1. **Không trỏ test vào `%APPDATA%\YapWindows\config.json` thật.** Đã xoá mất
   key người dùng một lần. Gán `app.CONFIG_FILE` sang file tạm.
2. **Không tin `sd.check_input_settings()`** — nó báo OK rồi `.start()` vẫn ném
   lỗi. Mở stream thật, hỏng thì lùi sang lựa chọn kế.
3. **Không tham chiếu `e` của `except` trong lambda hoãn lại** — Python xoá nó khi
   ra khỏi khối, `NameError` che mất lỗi thật. Đóng băng `str(exc)`.
4. **Không đặt `after()` khung kế tiếp trong `try`** — một lỗi vẽ là animation chết vĩnh viễn.
5. **Không fallback ngầm khi hotkey sai** — rơi về `space` là app tự ghi âm mỗi
   lần người dùng gõ dấu cách.
6. **Cổng paste phải fail-closed** — nghi ngờ cửa sổ đích thì chỉ copy. Dán lạc
   cửa sổ là rò rỉ nội dung.
7. **Không ép mic về 16 kHz** — resample thô 44100→16000 làm nhoè âm xát
   (`phết`→`chết`). Thu tần số gốc, để Whisper tự hạ mẫu.
8. **Không mồi Whisper bằng transcript chưa lọc** — câu bịa vào lịch sử thành mồi
   rồi tự nhân lên; lọc đủ 3 chốt. Sửa bộ lọc phải chạy lại **đối chứng âm** —
   bản đầu nuốt oan 3 câu thật. [hallucination.md](docs/specs/hallucination.md)

## Tài liệu — `docs/specs/architecture.md` là điểm vào, mỗi module một file cạnh nó.
