# Phím nóng — `SmartHook`

`app.py:242`

## Nguyên tắc nền

Hook này **không chặn phím**. Nó chỉ đọc `GetAsyncKeyState` mỗi 5ms, phím vẫn
đi thẳng xuống ứng dụng người dùng đang gõ.

Hệ quả bắt buộc: **hotkey phải là phím không dùng để gõ**. Mặc định `right ctrl`.
Nếu đặt `space`, giữ 0.4 giây trong Word là Windows đã gõ ra một dãy dấu cách
trước khi Yap kịp phản ứng.

## Ba sự kiện

```python
SmartHook(key_name, threshold, on_press, on_arm, on_release)
```

| Sự kiện | Khi nào | Việc cần làm |
|---|---|---|
| `on_press()` | Phím vừa nhấn xuống | **Mở mic ngay** |
| `on_arm()` | Vẫn giữ quá `threshold` (0.4s) | Đây là dictation thật → hiện UI |
| `on_release(armed)` | Nhả phím | `armed=False` là chạm nhầm → vứt audio |

Vì sao tách `on_press` khỏi `on_arm`: nếu đợi hết ngưỡng rồi mới mở mic thì
**mất 0.4 giây đầu câu**, từ đầu tiên luôn cụt. Giờ ngưỡng chỉ quyết định
*giữ hay vứt*, không quyết định *bắt đầu thu lúc nào*.

Đã kiểm bằng giả lập: giữ 1.5s → thu được **1.56s** audio.

## Thứ tự sự kiện

Luồng poll **chỉ đẩy vào `queue.Queue`**. Một luồng dispatch duy nhất lấy ra và
chạy callback. Trước đây mỗi sự kiện spawn một thread riêng, nên `release` có
thể chạy trước `press` của chính nó.

## `stop()` là rào chắn, không phải cờ

```python
def stop(self):
    self._running = False
    for th in self._threads:
        if th.is_alive(): th.join(timeout=1.0)
```

Dispatch cũng kiểm lại `_running` **sau khi** lấy sự kiện khỏi queue, để không
chạy callback của một hook đã bị thay thế.

Lý do: đổi hotkey trong lúc đang giữ phím thì `on_release` của hook cũ không bao
giờ tới → mic kẹt mở, hook mới thừa hưởng `_recording=True`. `_unregister_hotkey`
gọi thêm `_cancel_recording()` để đóng phiên đang dở.

## Xác thực tên phím

`SmartHook.resolve(name)` trả `None` nếu không hỗ trợ. Constructor ném
`ValueError`. `SettingsDialog._save` chặn không cho lưu. `_register_hotkey`
cảnh báo rồi quay về mặc định.

**Tuyệt đối không fallback ngầm.** `VK_MAP.get(name, 0x20)` cũ khiến `right_ctrl`
(gạch dưới) âm thầm thành `space`.

Phím hỗ trợ: xem `SmartHook.VK_MAP` — các phím F, `right/left ctrl`,
`right/left alt`, `scroll lock`, `caps lock`, `tab`, `insert`, `home`, `end`,
và `space` (chọn được nhưng không nên).
