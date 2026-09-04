# Mồi gửi Whisper — `build_prompt`

`build_prompt` · `DEFAULT_PROMPT` · `MAX_PROMPT_BYTES` · `_fit_bytes`

Tham số `prompt` của Whisper là **gợi ý ngữ cảnh**, không phải mệnh lệnh. Đây là
đòn bẩy lớn nhất lên độ chính xác, và cũng là đường để câu bịa quay lại —
xem [hallucination.md](hallucination.md) trước khi sửa file này.

## Vì sao cần mồi

Không có mồi, từ tiếng Anh nói trong câu tiếng Việt bị phiên âm theo âm Việt:

```
"Ctrl"  →  "căn chuồn" / "cân trồn"
```

A/B trên cùng một file audio:

| | Kết quả |
|---|---|
| Không mồi | `press ctrl, then open klaviyo nn8n, and push the commit to github` |
| Có mồi | `Press Ctrl, then open Klaviyo and n8n, and push the commit to GitHub.` |

Không mồi thì `n8n` dính thành `nn8n`, mất viết hoa và dấu câu.

## `DEFAULT_PROMPT` viết thành CÂU THẬT, không phải danh sách từ

Whisper bắt chước **văn phong** của đoạn mồi, không chỉ lấy từ vựng. Nên mồi mặc
định là những câu thật có trộn hai thứ tiếng — nó dạy máy *"người này trộn
Việt–Anh, từ tiếng Anh giữ nguyên tiếng Anh"*. Danh sách từ trần vẫn để `Ctrl`
ra `"căn chuồn"`.

Người dùng sửa danh sách trong Settings → mục **TỪ VỰNG**. Quy tắc: viết từ
**đúng dạng muốn nó hiện ra**.

## Thứ tự ghép — thứ quý nhất đứng cuối

Whisper chỉ giữ **224 token CUỐI** của mồi:

```
[ngữ cảnh gần]   [từ vựng người dùng]   [các cặp đã sửa tay]
  bị cắt trước                            sống sót cuối cùng
```

Cặp người dùng tự sửa ([corrections.md](corrections.md)) đứng cuối vì chính họ
dạy — đáng tin nhất. Ngữ cảnh gần đứng đầu: mất cũng không hỏng gì cốt lõi.

| Hằng số | Giá trị | Ý nghĩa |
|---|---|---|
| `MAX_PROMPT_BYTES` | 880 | trần cứng cho cả mồi |
| `CORRECT_BYTES` | 200 | phần dành riêng cho cặp đã sửa |
| `RECENT_CONTEXT` | 2 | số transcript gần nhất được nhét vào |
| `RECENT_MAX_CHARS` | 160 | một câu dài không được ăn hết ngân sách |

## Bẫy: đếm BYTE, không đếm ký tự

Groq **từ chối thẳng** nếu mồi dài quá — trả 400, không tự cắt bớt. Và nó đếm
byte UTF-8: 773 ký tự tiếng Việt = 901 byte, vì mỗi chữ có dấu tốn 2–3 byte.
Đếm bằng `len()` là hụt một phần tư.

Dùng `_nbytes` / `_fit_bytes`. Có `assert` chốt trần ở cuối `build_prompt` —
tràn thì nổ ngay tại chỗ, không để Groq trả 400 mơ hồ.

## Ngữ cảnh gần phải được LỌC trước khi vào mồi

`build_prompt` chạy `strip_hallucination` lên từng bản ghi lịch sử. Không phải
thừa: `history.json` của bản cũ đã nhiễm sẵn câu bịa, dọn file một lần không đủ.
Lý do đầy đủ ở [hallucination.md](hallucination.md).
