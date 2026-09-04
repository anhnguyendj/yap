# Giao diện

`MainWindow` · `HistoryWindow` · `SettingsDialog`

## Thanh sóng — `MainWindow`

Một viên nhộng mỏng 300×46 ở giữa đỉnh màn hình. Bên trong chỉ có sóng âm,
không chữ, không nút.

**Chỉ hiện khi có việc.** Ẩn lúc khởi động; `set_state()` gọi `show()` cho mọi
trạng thái trừ `idle`. Nhả phím xong là biến mất. Nó không phải thứ đóng đô
thường trực trên desktop.

`show()` chỉ `deiconify()` + `lift()`, **không bao giờ `focus_force()`** —
cướp focus sẽ đổi cửa sổ đang ở trước và làm hỏng cổng dán
(xem [paste.md](paste.md)).

### Vẽ sóng

| Hằng số | Giá trị | Ghi chú |
|---|---|---|
| `N_BARS` | 44 | Nhiều cột mảnh, không phải vài cột dày |
| `BAR_STEP` | 6 px | **Phải lớn hơn bề rộng quầng sáng** |
| Quầng sáng | nét 4 px, `GLOW` | Rộng hơn bước là các cột dính thành mảng đặc |
| Lõi | nét 2 px, `CORE_LO→HI` | Cột càng cao càng sáng |

`_levels` là hàng đợi trượt, mới nhất bên phải. Mỗi 40ms đẩy một mức vào:

| Trạng thái | Nguồn mức âm |
|---|---|
| `recording` | `recorder.level` thật, mũ 0.6 để nâng phần nhỏ |
| `transcribing` | Nhịp sin, báo đang chờ API |
| `idle` | Gần phẳng, thở nhẹ |

Hai cột ngoài cùng được vuốt thấp dần để sóng không đâm vào đầu tròn của vỏ.

### Hai bẫy vẽ đã trả giá

1. **`create_polygon(smooth=True)` không cho ra nửa đường tròn.** Nó ra hình
   vuông bo mềm. Viên nhộng thật phải ghép: hai `create_oval` hai đầu + một
   `create_rectangle` ở giữa — đó là `_capsule()`.
2. **Quầng sáng rộng hơn khoảng cách cột thì chúng dính vào nhau.** Bước 5px
   với quầng 6px cho ra một khối đặc, mất hết cảm giác sóng.

Vỏ trong suốt ở góc nhờ `attributes("-transparentcolor", TRANS)`. Windows cũ
không hỗ trợ thì bọc `try` — góc vuông nhưng vẫn dùng được.

### Tương tác

Kéo để dời chỗ · chuột phải mở menu (Lịch sử / Settings / Thoát) · nhấp đúp mở
Settings. Thanh chỉ hiện khi đang thu nên tray icon mới là đường vào chính.

### Nhãn thông báo

Trạng thái không thuộc `idle/recording/transcribing` được coi là nhãn: thay
sóng bằng một dòng chữ trong 1.4 giây rồi tự về `idle`. Dùng bộ đếm thế hệ
`_flash_gen` để hai nhãn liên tiếp cùng chữ không cắt ngắn nhau.

## `HistoryWindow`

Cửa sổ riêng, mở từ menu chuột phải hoặc tray. Hiện 60 mục gần nhất, mới nhất
trên cùng. Nhấp một dòng là copy lại, ô sáng lên 250ms để xác nhận.

Tách khỏi thanh sóng có chủ ý — thanh phải mỏng và chỉ làm một việc.

## `SettingsDialog`

Provider · API key (kèm dòng nói key đang lấy từ đâu) · ngôn ngữ · **từ vựng
mồi** · phím nóng.

Hotkey sai thì `messagebox` báo lỗi và **không đóng dialog, không lưu** — xem
[hotkey.md](hotkey.md).

Ô từ vựng là chỗ người dùng dạy Whisper các từ hay bị nghe nhầm; có nút khôi
phục danh sách mặc định.

## Luật luồng

Chỉ luồng main được đụng widget. Luồng nền đi qua `win.after(0, ...)`, và
`_set_state` bọc `try` phòng trường hợp cửa sổ đã bị huỷ giữa lúc kiểm tra.
