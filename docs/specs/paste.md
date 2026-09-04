# Đưa text vào cửa sổ — `YapApp._paste`

`app.py` — `_paste`, `_foreground_hwnd`, `_modifiers_held`

Đây là phần dễ gây hại nhất trong app: nó **gõ phím vào máy người dùng** và
**ghi đè clipboard của họ**. Mọi cổng ở đây đều **fail-closed** — nghi ngờ thì
chỉ copy, không dán.

## Ba cổng, theo thứ tự

### ① Đúng cửa sổ đích chưa

HWND được chụp ở **`_on_press`**, tức lúc phím vừa nhấn xuống — trước khi thanh
sóng kịp hiện lên. Hiện một cửa sổ có thể đổi cửa sổ đang ở trước, và khi đó
text sẽ dán vào chính thanh sóng của Yap.

`_foreground_hwnd()` trả `None` nếu cửa sổ trước thuộc **tiến trình của chính
Yap**, so bằng PID.

`target_ok()` kiểm ba điều, sai một là chỉ copy:
- `target_hwnd` khác rỗng
- `win32gui.IsWindow(target_hwnd)` — cửa sổ chưa đóng
- Nó vẫn đang là foreground

Ngoại lệ khi gọi Win32 → **trả `False`**, không phải bỏ qua cổng. Bản trước
in traceback rồi vẫn dán tiếp, tức fail-open.

Cổng được kiểm **lại** sau mỗi lần chờ: sau vòng chờ modifier, và ngay trước
khi bắn `Ctrl+V`.

**Giới hạn đã biết:** đổi tab Chrome hay đổi cuộc chat trong Slack vẫn là cùng
một HWND. Cổng không phát hiện được. Muốn chặn phải dùng UI Automation.

### ② Người dùng còn giữ phím nào không

`_modifiers_held()` đọc `GetAsyncKeyState` cho Ctrl, Shift, Alt, LWin, RWin.
Nếu còn giữ, chờ tối đa `PASTE_WAIT` = 1.0 giây. Hết giờ mà còn giữ → chỉ copy.

Lý do: bắn `Ctrl+V` khi người dùng đang giữ Shift thành `Ctrl+Shift+V` —
"Paste Special", hoặc một shortcut khác hẳn.

### ③ Mượn clipboard rồi trả lại

```
lưu bản cũ  →  copy transcript  →  ghi lại số thứ tự  →  Ctrl+V
            →  chờ 0.35s  →  nếu số thứ tự chưa đổi thì trả bản cũ về
```

Dùng **`GetClipboardSequenceNumber()`**, không so nội dung. Hai thứ khác nhau
có thể có cùng đoạn text, và so nội dung sẽ đè mất bản người dùng vừa copy.

**Chỉ khôi phục được chữ thuần.** `pyperclip` không đọc/ghi được ảnh, danh sách
file hay rich text. Nếu clipboard đang giữ thứ đó, nó **mất**. App phát hiện
bằng `IsClipboardFormatAvailable(CF_UNICODETEXT)` + `CountClipboardFormats()`
và báo `clipboard replaced` để người dùng biết mà cứu.

## Nhả phím: chỉ nhả cái đã nhấn

```python
ctrl_down = v_down = False
try:
    keybd_event(VK_CONTROL, ...); ctrl_down = True
    keybd_event(ord('V'), ...);   v_down = True
finally:
    try:
        if v_down: keybd_event(ord('V'), ..., KEYEUP)
    finally:
        if ctrl_down: keybd_event(VK_CONTROL, ..., KEYUP)
```

`try/finally` lồng nhau: nếu lệnh nhả V ném lỗi, Ctrl **vẫn** được nhả. Ctrl
kẹt xuống làm hỏng toàn bộ bàn phím của máy.

Và chỉ nhả phím đã thật sự nhấn — nhả một phím chưa từng nhấn có thể can thiệp
vào thao tác người dùng đang làm.

## Nhãn báo cho người dùng

| Nhãn | Nghĩa |
|---|---|
| `copied — window changed` | Đã đổi cửa sổ, text nằm sẵn trong clipboard |
| `copied — keys held` | Còn giữ Ctrl/Shift/Alt/Win |
| `clipboard replaced` | Ảnh/file trong clipboard cũ đã mất |
