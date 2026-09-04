# Thu âm — `AudioRecorder`, `input_candidates`, `wav_stats`

`app.py:355` · `app.py:400` · `app.py:188`

## Chọn thiết bị: thử thật, không hỏi suông

`input_candidates()` trả về **một danh sách** (thiết bị, tần số) theo thứ tự
chất lượng giảm dần. `AudioRecorder.start()` đi từng cái, **mở stream thật**,
hỏng thì tụt xuống cái kế:

1. Mic mặc định của **WASAPI** ở tần số gốc (48 kHz) — không resample lần nào
2. Mic mặc định hệ thống ở tần số gốc của nó
3. `device=None` @ 16 kHz — đường cũ, luôn chạy được

> `sd.check_input_settings()` **nói dối**. Nó trả về OK cho WASAPI rồi
> `stream.start()` vẫn ném `WdmSyncIoctl ... [Windows WDM-KS error 0]`.
> Chỉ có mở thật mới biết.

Trước khi liệt kê, hàm gọi `sd._terminate(); sd._initialize()` để PortAudio
đánh số lại thiết bị. Chỉ số bị **lệch giữa các tiến trình** — "device 12,
WASAPI" trong tiến trình này lại là WDM-KS trong tiến trình kia, và đó chính
là nguyên nhân mở nhầm backend. Thiết bị được hỏi qua
`hostapi["default_input_device"]`, không đoán theo tên.

## Vì sao không ép 16 kHz

Whisper cần 16 kHz, nhưng **đừng để Windows hạ mẫu**. Mic chạy 44.1/48 kHz;
bộ resample của MME thô, và 44100→16000 không phải tỉ lệ chẵn. Nó làm nhoè
các âm xát — `ph` và `ch` gần nhau về phổ, nên `"phết"` ra `"chết"`.

Thu ở tần số gốc, ghi WAV đúng `self.samplerate`, để Whisper tự hạ mẫu bằng
bộ lọc chống răng cưa tử tế của nó.

## `start()` phải an toàn khi lỗi

Dựng stream vào **biến local** trước. Nếu `.start()` ném lỗi thì đóng nó, đặt
`recording=False`, `_stream=None`. Không được để một stream nửa vời trong
`self._stream` cho lần nhấn sau ghi đè lên.

Điều này quan trọng hơn từ khi mic mở ở **mỗi lần nhấn phím**, kể cả chạm nhầm.

## Mức âm trực tiếp

Callback tính RMS mỗi block, chuẩn hoá về `0..1` vào `self.level`. Thanh sóng
trong UI đọc trường này. Đây là số thật từ mic, không phải hoạt hình chạy sẵn.

## Cổng chặn trước khi tốn tiền API

`wav_stats(audio) -> (duration, rms)`

| Ngưỡng | Giá trị | Ý nghĩa |
|---|---|---|
| `MIN_DURATION` | 0.35s | Ngắn hơn thì không có lời nào |
| `MIN_RMS` | 80 | Dưới mức này là tiếng ồn phòng |

RMS tính trên **cửa sổ 30ms, lấy cửa sổ to nhất**, không phải trung bình toàn
đoạn. Một câu ngắn nói nhỏ kẹp giữa 2 giây im lặng sẽ bị trung bình kéo tụt
xuống dưới ngưỡng và bị loại oan.

Ngưỡng đặt rộng có chủ ý: gửi nhầm một đoạn im lặng rẻ hơn nhiều so với nuốt
mất một câu người dùng nói khẽ.

Bị chặn thì UI hiện `too short` / `no speech` — người dùng biết vì sao, không
phải đoán.
