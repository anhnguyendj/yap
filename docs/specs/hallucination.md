# Lọc câu Whisper bịa — `strip_hallucination`

`strip_hallucination` · `HALLUCINATION_RE` · `_SENTENCE_SPLIT`

`whisper-large-v3` học từ hàng triệu video YouTube. Gặp im lặng hoặc tiếng
phòng, nó **không** trả về rỗng — nó lấp chỗ trống bằng câu outro quen nhất:

> *"Các bạn có thể nhớ like, share và đăng ký kênh để ủng hộ kênh của mình nhé."*
> *"Cảm ơn các bạn đã theo dõi. Hẹn gặp lại các bạn trong những video tiếp theo."*

Đây là artifact của model, **không tắt được bằng tham số**. `temperature=0` làm
nhẹ đi, không hết. Phải lọc ở đầu ra.

## Vòng tự siết — lý do phải lọc ở BA chỗ

```
Whisper bịa một câu
      │
      ▼
câu bịa vào history.json
      │
      ▼
build_prompt lấy RECENT_CONTEXT câu gần nhất làm mồi
      │
      ▼
Whisper được dạy "người này hay nói câu này"  ──► bịa tiếp ──┐
      ▲                                                       │
      └───────────────────────────────────────────────────────┘
```

Đã xảy ra thật (04/09/2026): `history.json` có 4 bản ghi nhiễm — entry #75 bịa
nguyên câu, #76 dính theo, #81 lại bịa, #97 dính tiếp.

| Chốt chặn | Vì sao không bỏ được chỗ nào |
|---|---|
| trước `_paste` | không thì câu bịa dán thẳng vào chỗ người dùng đang gõ |
| trước `_save_hist` | không thì nó vào lịch sử rồi quay lại làm mồi |
| trong `build_prompt` | `history.json` bản cũ **đã nhiễm sẵn** — dọn file một lần không đủ |

## Đơn vị lọc là CÂU TRỌN VẸN

Tách theo `_SENTENCE_SPLIT` = `(?<=[.!?…])\s+`, bỏ **cả câu**, ở **bất kỳ vị trí
nào** — một khoảng lặng giữa lúc đọc cũng làm nó chèn outro vào *giữa* hai ý
thật, không chỉ ở cuối.

Lọc theo cụm thay vì theo câu sẽ ăn vào giữa câu thật.

## Neo `^` là thứ giữ an toàn

Chỉ bỏ câu **bắt đầu** bằng mẫu outro. Câu người dùng nói thật về chính chuyện
này — *"Kìa kìa, có cái phần các bạn nhớ like và share… là sao nhỉ?"* — bắt đầu
bằng `"Kìa kìa"` nên không khớp, không bị ăn oan.

## Điều kiện "kênh"

Nhánh like/share/subscribe **bắt buộc cùng câu phải có `kênh` hoặc `channel`**
(lookahead `(?=[^.!?]*\b(?:kênh|channel)\b)`). Bản đầu không có điều kiện này
đã nuốt 3 câu hoàn toàn bình thường:

| Câu thật | Bản đầu | Bản hiện tại |
|---|---|---|
| "Share cho anh cái link Google Drive đó với." | ✗ mất | ✓ giữ |
| "Đăng ký cho anh một tài khoản Groq mới nhé." | ✗ mất | ✓ giữ |
| "Chia sẻ màn hình đi em, anh không thấy gì cả." | ✗ mất | ✓ giữ |

Nhánh tiếng Anh đòi đúng cặp `like … subscribe`, vì `"Subscribe cho anh cái
newsletter đó"` là câu thật. `\b` sau mỗi động từ chặn `"Likewise, tôi nghĩ…"`.

Các câu outro có dạng cố định (`cảm ơn các bạn đã theo dõi`, `hẹn gặp lại các
bạn`, `thanks for watching`, `ghiền mì gõ`, `phụ đề thực hiện bởi`) không cần
điều kiện "kênh" — chúng không thể là câu thật.

## Không nuốt im lặng

Câu bị bỏ được in `[loc] bo cau Whisper bia: …` ra stdout, thấy trong `run.bat`.
Lọc âm thầm thì lần sau mất chữ thật cũng không ai biết.

## Sửa bộ lọc thì BẮT BUỘC chạy lại đối chứng âm

Thêm mẫu mới rất dễ nuốt oan câu thật, và đếm số câu bị bỏ thì phép thử nào
cũng "pass". Phải thử **cả hai chiều**:

- câu bịa phải mất — 5 mẫu
- câu thật phải còn — 13 mẫu, gồm cả câu người dùng nói *về* outro

Lần gần nhất chạy: 18/18 pass. Chính đối chứng âm bắt được 3 lỗi nuốt oan ở
bảng trên — không phải suy đoán, là phép thử.

## Dọn dữ liệu đã nhiễm

Vá code không sửa được `history.json` cũ. Chạy lọc lên toàn bộ lịch sử, xoá hẳn
bản ghi chỉ còn rỗng, **backup trước**. Lần chạy 04/09: sửa 2, xoá 2, còn 98/100.
