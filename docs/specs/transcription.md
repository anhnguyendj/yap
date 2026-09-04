# Nhận dạng — `Transcriber`

`app.py:462`

## API

```python
Transcriber().transcribe(audio_bytes, cfg) -> str
```

Đọc từ `cfg`: `provider`, `language`, `prompt`, `model`. Key lấy qua
`provider_key()` — xem [config-and-secrets.md](config-and-secrets.md).

| Provider | Model | Ghi chú |
|---|---|---|
| `groq` (mặc định) | `whisper-large-v3` | 2000 phút/ngày free |
| `openai` | `whisper-1` | Cần `pip install openai` |

## Model: đầy đủ, không dùng bản turbo

`whisper-large-v3-turbo` nhanh hơn nhưng là bản chưng cất — yếu hơn ở tiếng
không phải tiếng Anh. Chênh lệch giá (~$0.04 vs ~$0.11/giờ) không phải ràng
buộc; bị nghe nhầm mới là.

> **Chưa đo được trên giọng người dùng thật.** Phép đo duy nhất chạy được là
> giọng tổng hợp tiếng Anh, và nó **không ủng hộ** large-v3. Chọn large-v3 dựa
> trên lý lẽ (mạnh hơn ở tiếng Việt theo thiết kế), không phải bằng chứng.
> `so-sanh.bat` ghi 6 giây giọng thật rồi thử cả 4 tổ hợp model × mồi để người
> dùng tự chọn. Đó là phép thử duy nhất có giá trị.

## `language`: để `auto`

Người dùng chính code-switch liên tục. Khoá sang `vi` làm hỏng ngay khi có
một hai câu tiếng Anh. Whisper tự nhận diện từng đoạn.

## `prompt` — mồi từ vựng, thứ quan trọng nhất

Tham số `prompt` của Whisper là **gợi ý ngữ cảnh**, không phải mệnh lệnh. Không
có nó, từ tiếng Anh nói trong câu tiếng Việt bị phiên âm theo âm Việt:

```
"Ctrl"  →  "căn chuồn" / "cân trồn"
```

`DEFAULT_PROMPT` (`app.py:55`) được viết thành **những câu thật có trộn hai thứ
tiếng**, không phải danh sách từ trần. Whisper bắt chước **văn phong** của đoạn
mồi, nên câu mẫu dạy nó "người này trộn Việt-Anh, từ tiếng Anh giữ nguyên
tiếng Anh".

Bằng chứng A/B trên cùng một file audio:

| | Kết quả |
|---|---|
| Không mồi | `press ctrl, then open klaviyo nn8n, and push the commit to github` |
| Có mồi | `Press Ctrl, then open Klaviyo and n8n, and push the commit to GitHub.` |

Không mồi thì `n8n` dính thành `nn8n`, mất viết hoa và dấu câu.

Người dùng sửa danh sách này trong Settings → mục **TỪ VỰNG**. Quy tắc: viết
từ **đúng dạng muốn nó hiện ra**.

Giới hạn: prompt của Whisper tối đa ~224 token. Thêm quá nhiều thì phần đầu
bị cắt.

## Lỗi

Không có key → `ValueError` nêu rõ tên biến và đường dẫn `.env`. Mọi lỗi khác
để nguyên cho `YapApp._error()` hiện lên, đã đóng băng `str(exc)` từ trước.
