# Key và cấu hình

`load_env` · `load_config` · `save_config` · `_write_atomic` · `provider_key`

## API key: `.env` thắng

```
.env  (cạnh app.py)   →  config.json  →  không có
```

| Hàm | Việc |
|---|---|
| `load_env()` | Đọc `.env` cạnh `app.py`, đọc lại **mỗi lần gọi** |
| `provider_key(provider, cfg)` | `.env` trước, `config.json` là đường lùi |
| `key_source(provider, cfg)` | Trả `"env"` / `"config"` / `"none"` cho UI |

Đọc lại mỗi lần chép lời, nên **dán key vào `.env` không cần khởi động lại app**.

Tên biến: `GROQ_API_KEY`, `OPENAI_API_KEY` (`ENV_KEY_NAMES`).

`.env` bị `.gitignore` chặn; `.env.example` chỉ có **tên biến**, không có giá
trị. `config.json` giữ lại chỉ để bản cài cũ không mất key khi nâng cấp.

## Cấu hình — `%APPDATA%\YapWindows\config.json`

| Khoá | Mặc định | Xem thêm |
|---|---|---|
| `hotkey` | `right ctrl` | [hotkey.md](hotkey.md) |
| `provider` | `groq` | |
| `model` | `whisper-large-v3` | [transcription.md](transcription.md) |
| `language` | `auto` | Đừng khoá `vi` — người dùng code-switch |
| `prompt` | `DEFAULT_PROMPT` | Mồi từ vựng, thứ quan trọng nhất |
| `api_key` | `""` | Đường lùi, `.env` mới là chính |

## Chuẩn hoá ngay khi đọc

`load_config()` ép mọi khoá chuỗi về `str` không rỗng, sai thì lấy mặc định.

Lý do: một `config.json` sửa tay có `"hotkey": null` từng làm **chết app** ở
`hk.upper()` — trước cả khi kịp tới nhánh fallback. Chuẩn hoá tại một chỗ để
mọi nơi phía sau khỏi phải tự phòng thủ.

## Ghi file nguyên tử

`_write_atomic(path, data)` ghi ra file `.<pid>.tmp` cùng thư mục rồi
`os.replace()`. Lỗi giữa chừng thì xoá file tạm, không để lại rác.

Dùng cho cả `config.json` và `history.json`. Tắt máy giữa lúc ghi không làm
mất key hay cụt lịch sử.

`history.json` giữ tối đa `MAX_HISTORY` = 100 mục, bảo vệ bằng `_hist_lock`.

## Nếp giữ key

- Mỗi dự án một `.env` riêng. **Không mượn `.env` của repo khác** — revoke một
  nơi thì nơi kia chết lặng lẽ.
- Bản thứ hai để trong 1Password, vault riêng của dự án.
- Nói về key thì **chỉ nói tên biến**, không in giá trị ra màn hình hay log.
- Đẩy key lên trình quản lý thì đi qua file template rồi xoá, đừng truyền qua
  dòng lệnh — nó lọt vào danh sách tiến trình.

> **CẤM:** không bao giờ trỏ test vào `%APPDATA%\YapWindows\config.json` thật.
> Một lần ghi đè rồi `unlink()` đã xoá mất key của người dùng, không qua Thùng
> rác, không có bản sao. Test phải gán `app.CONFIG_FILE` sang file tạm.
