# Học sửa lỗi — `corrections.json`

`learn_corrections` · `auto_safe` · `apply_corrections` · `YapApp.learn_from_edit`

Người dùng sửa tay **một lần** trong cửa sổ Lịch sử, app nhớ mãi. Đây là cách
duy nhất dạy được máy những từ Whisper luôn nghe sai trên giọng cụ thể này.

## Schema

`%APPDATA%\YapWindows\corrections.json` — object phẳng, `{nghe nhầm: đúng}`:

```json
{
  "căn chuồn": "Ctrl",
  "Sopify": "Shopify",
  "bị nỗi": "bị lỗi"
}
```

Khoá là chuỗi máy nghe nhầm, giá trị là chuỗi đúng. Cả hai bắt buộc là `str` —
`load_corrections` lọc bỏ mọi cặp không phải chuỗi thay vì để nổ về sau.

## Luồng

```
người dùng sửa một dòng trong cửa sổ Lịch sử
              │  (before, after, timestamp)
              ▼
   YapApp.learn_from_edit
              ├──► sửa đúng bản ghi trong history.json (khớp cả ts lẫn text cũ)
              │
              ▼
   learn_corrections(before, after)      difflib.SequenceMatcher, chỉ opcode "replace"
              │
              ├─ cụm > CORRECT_MAX_WORDS (4 từ)  → BỎ, đó là viết lại câu
              ├─ cụm chưa đặc trưng             → NỚI ra hai bên tối đa CONTEXT_GROW (3) lần
              └─ wrong < 3 ký tự · wrong == right → BỎ
              │
              ▼
   {wrong: right} vào self.corrections ──► save_corrections()
```

## Hai cổng an toàn

**Cổng 1 — không học bản viết lại.** Đổi một cụm dài thường là người dùng viết
lại câu cho gọn, không phải máy nghe sai. Học vào là mỗi lần chép lời sau đó
đều bị thay bậy. Chặn bằng `CORRECT_MAX_WORDS`.

**Cổng 2 — `auto_safe()` quyết định *thay tay* hay *chỉ mồi*.** Một từ ngắn thì
không đủ đặc trưng:

| Học được | `auto_safe` | Vì sao |
|---|---|---|
| `"ông"` → `"không"` | ✗ chỉ mồi | thay khắp nơi biến `"ông ấy đi rồi"` thành `"không ấy đi rồi"` |
| `"xác"` → `"để"` | ✗ chỉ mồi | phá `"chính xác"` |
| `"bị nỗi nhiều"` → `"bị lỗi nhiều"` | ✓ thay tay | 3 từ, đủ đặc trưng |

Cụm trượt cổng 2 **không bị vứt đi** — nó vẫn được mồi cho Whisper qua
[prompting.md](prompting.md), chỉ là không thay bằng tay.

## Nới cụm ra hai bên

Sửa `"nỗi"`→`"lỗi"` một mình là nguy hiểm (phá `"nỗi buồn"`), nhưng đó lại đúng
là loại lỗi hay gặp nhất. Nên khi cụm quá ngắn, `learn_corrections` **lấy thêm
từ hai bên** cho tới khi `auto_safe` chịu, tối đa `CONTEXT_GROW` lần. Nhờ vậy
`"nỗi"` thành `"bị nỗi nhiều"` — vẫn học được, mà an toàn.

## Thay: khớp theo biên từ

`apply_corrections` dùng `(?<!\w)…(?!\w)`, không phải `str.replace`. Không có
biên từ thì `"ông"` ăn vào `"không"`. Cụm dài được thay trước cụm ngắn.

Bản thay truyền qua **lambda**, không phải chuỗi: một bản sửa chứa `\1` hay
`\g` sẽ bị `re.sub` hiểu thành backreference và ném lỗi giữa lúc đang dùng.

## Không học ngược lại chính mình

Nếu vế *đúng* lại đang là một vế *nhầm* đã có, `learn_from_edit` bỏ qua. Không
có chốt này thì hai luật đá nhau mỗi lần chép lời.

## Quên

`YapApp.forget_correction(wrong)` — cửa sổ Lịch sử hiện các cặp đã học để gỡ.
Không có đường nào khác xoá được, kể cả sửa lại lần nữa.
