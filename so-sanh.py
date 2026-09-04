#!/usr/bin/env python3
"""So sanh cac cau hinh nhan dang bang CHINH GIONG CUA BAN.

Ghi mot lan, roi gui cung mot doan audio qua tat ca to hop model x tu-vung
va in ket qua canh nhau. Do la cach duy nhat de biet cai nao hop giong ban.

Chay:  py so-sanh.py
"""
import sys, io, time, wave, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import numpy as np, sounddevice as sd
import app

GIAY = 6

def ghi_am(giay=GIAY):
    print(f"\n  Noi mot cau BAT DAU SAU 1 GIAY, co ca tu tieng Anh ban hay dung.")
    print(f"  Vi du: 'Anh review lai cai commit nay roi push len GitHub nhe.'")
    for i in range(3, 0, -1):
        print(f"    {i}...", end="\r", flush=True); time.sleep(1)
    print("  >>> DANG GHI, noi di! <<<          ")
    buf = sd.rec(int(giay * app.SAMPLE_RATE), samplerate=app.SAMPLE_RATE,
                 channels=1, dtype="int16")
    sd.wait()
    print("  Xong.\n")
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(app.SAMPLE_RATE)
        w.writeframes(buf.tobytes())
    return b.getvalue()

def main():
    cfg = app.load_config()
    if not app.provider_key(cfg["provider"], cfg):
        print("  Chua co API key. Dan vao .env truoc."); return

    audio = ghi_am()
    d, r = app.wav_stats(audio)
    print(f"  Audio: {d:.1f}s  rms={r:.0f}")
    if r < app.MIN_RMS:
        print("  Qua nho, mic khong bat duoc tieng. Thu lai va noi to hon."); return

    open("mau-giong.wav", "wb").write(audio)
    print("  Da luu mau-giong.wav (dung lai duoc cho lan sau)\n")

    t = app.Transcriber()
    for model in ("whisper-large-v3", "whisper-large-v3-turbo"):
        for ten, moi in (("KHONG moi", ""), ("CO moi  ", app.DEFAULT_PROMPT)):
            c = dict(cfg); c["model"] = model; c["prompt"] = moi
            t0 = time.time()
            try:
                out = t.transcribe(audio, c)
                print(f"  [{model:22}] {ten} {time.time()-t0:4.1f}s")
                print(f"      {out}\n")
            except Exception as e:
                print(f"  [{model:22}] {ten} LOI: {str(e)[:150]}\n")

    print("  --> Chon cau hinh nao ra dung nhat, roi vao Settings dat theo.")

if __name__ == "__main__":
    main()
