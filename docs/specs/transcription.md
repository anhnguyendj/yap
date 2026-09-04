# Nhận dạng — `Transcriber`

`Transcriber` · `GROQ_MODELS`

```python
Transcriber().transcribe(audio_bytes, cfg) -> str
```

Đọc từ `cfg`: `provider`, `language`, `prompt`, `model`. Key lấy qua
`provider_key()` — xem [config-and-secrets.md](config-and-secrets.md).
Nội dung `prompt` được dựng ở [prompting.md](prompting.md).

| Provider | Model | Ghi chú |
|---|---|---|
| `groq` (mặc định) | `whisper-large-v3` | 2000 phút/ngày free |
| `openai` | `whisper-1` | Cần `pip install openai` |

## Model: đầy đủ, không dùng bản turbo

`whisper-large-v3-turbo` nhanh hơn nhưng là bản chưng cất — yếu hơn ở tiếng
không phải tiếng Anh. Chênh lệch giá (~$0.04 vs ~$0.11/giờ) không phải ràng
buộc; bị nghe nhầm mới là. Cả hai để người dùng chọn trong Settings
(`GROQ_MODELS`).

> **Chưa đo được trên giọng người dùng thật.** Phép đo duy nhất chạy được là
> giọng tổng hợp tiếng Anh, và nó **không ủng hộ** large-v3. Chọn large-v3 dựa
> trên lý lẽ (mạnh hơn ở tiếng Việt theo thiết kế), không phải bằng chứng.
> `so-sanh.bat` ghi 6 giây giọng thật rồi thử cả 4 tổ hợp model × mồi để người
> dùng tự chọn. Đó là phép thử duy nhất có giá trị.

## `language`: để `auto`

Người dùng chính code-switch liên tục. Khoá sang `vi` làm hỏng ngay khi có một
hai câu tiếng Anh. Whisper tự nhận diện từng đoạn.

## `temperature=0`

Để mặc định, Whisper được phép "sáng tạo" khi nghe không rõ — đúng là lúc nó đẻ
ra câu outro YouTube. Đặt 0 buộc nó lấy đường giải mã chắc chắn nhất. Giảm nhẹ,
**không hết** — vẫn phải lọc, xem [hallucination.md](hallucination.md).

## Sau khi có text

Text đi qua ba bước trước khi tới người dùng, đúng thứ tự này:

```
transcribe() ──► apply_corrections() ──► strip_hallucination() ──► _paste()
                 corrections.md           hallucination.md         paste.md
```

## Lỗi

Không có key → `ValueError` nêu rõ tên biến và đường dẫn `.env`. Mọi lỗi khác để
nguyên cho `YapApp._error()` hiện lên, đã đóng băng `str(exc)` từ trước.
