# Vòng đời tiến trình

`acquire_single_instance` · `YapApp.__init__` / `YapApp.quit`

## Một bản chạy một lúc

```python
handle = CreateMutexW(None, False, r"Local\YapWindows-SingleInstance")
if GetLastError() == ERROR_ALREADY_EXISTS: -> thoát
```

Bản thứ hai hiện `MessageBoxW` chỉ về tray icon rồi thoát. Không có khoá này
thì hai bản cùng nghe phím, cùng mở mic, cùng tính tiền API, dán hai lần và
tranh nhau ghi `config.json`.

Handle giữ ở biến module `_instance_lock` để khỏi bị thu gom sớm; Windows tự
đóng khi tiến trình thoát.

Tiền tố `Local\` — phạm vi **một phiên Windows**. Hai phiên Remote Desktop
hoặc hai người dùng khác nhau vẫn chạy được mỗi nơi một bản.

## Khởi động

```
acquire_single_instance()
  → load_config() + load_history()
  → MainWindow (ẩn sẵn)
  → win.recorder = self._recorder      # thanh sóng đọc mức âm
  → tray icon
  → _register_hotkey()
  → nếu provider_key() rỗng thì mở Settings sau 800ms
```

Điều kiện mở Settings dùng `provider_key()`, **không** dùng `cfg["api_key"]` —
kiểm mỗi `config.json` sẽ nhắc mỗi lần khởi động dù `.env` đã có key tốt.

## Thoát

```python
def quit(self):
    self._shutdown.set()        # đặt TRƯỚC mọi thứ khác
    self._unregister_hotkey()   # đã tự huỷ phiên ghi đang dở
    self.win._alive = False
    tray.stop()
    self._recorder.stop()
    self.win.destroy()
```

`_shutdown` (một `threading.Event`) phải đặt **trước tiên**. Một `_transcribe`
đang bay về không được phép quay lại dán vào máy sau khi người dùng đã thoát,
cũng không được chạm vào cửa sổ đã bị huỷ.

Cờ được kiểm **lại trước từng tác dụng phụ**, không phải một lần ở đầu:

```python
if text and not self._shutdown.is_set(): self._paste(...)
if text and not self._shutdown.is_set(): self._save_hist(...)
```

Vì `Event` chỉ ảnh hưởng các lần kiểm sau nó — đoạn code đã vượt qua chốt vẫn
chạy tiếp. `_paste` cũng tự kiểm giữa các lần chờ.

`MainWindow._alive` dừng vòng `after(40, _tick)`; nếu không, một lỗi vẽ lúc
tắt sẽ ném ra từ một cửa sổ không còn tồn tại.

## Tray icon

`pystray` chạy trên luồng riêng. Menu: Show · Lịch sử · Settings · Quit — mọi
mục đều đi qua `win.after(0, ...)` để về luồng main.

Vì thanh sóng chỉ hiện lúc thu, tray là đường vào chính của app.

## Chạy từ shortcut

Shortcut Desktop trỏ `pyw.exe -3 app.py` (bản Python không cửa sổ console),
`WorkingDirectory` đặt về thư mục dự án để `app.py` tìm thấy `.env` cạnh nó.

`tao-shortcut.py` tự đọc vị trí của chính nó nên **chuyển thư mục đi đâu cũng
được** — chạy lại nó một lần sau khi move.
