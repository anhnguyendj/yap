#!/usr/bin/env python3
"""Dat shortcut Yap ra Desktop, tro vao dung thu muc dang chua file nay.

Chay lai sau moi lan chuyen thu muc di noi khac — no tu doc vi tri hien tai,
khong ghim cung duong dan nao.

Chay:  py tao-shortcut.py     (hoac double-click tao-shortcut.bat)
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "Yap.lnk"


def find_launcher():
    """pyw.exe truoc: chay khong hien cua so console den.

    Tra ve (duong_dan_exe, tham_so). Chi lay cai co that tren dia.
    """
    candidates = [
        (Path(os.environ.get("WINDIR", r"C:\Windows")) / "pyw.exe", "-3 "),
        (Path(sys.executable).with_name("pythonw.exe"), ""),
        (Path(sys.executable), ""),
    ]
    for exe, prefix in candidates:
        if exe.exists():
            return exe, prefix
    raise SystemExit("Khong tim thay pyw.exe hay pythonw.exe")


def desktop_dir():
    for env in ("OneDrive", "USERPROFILE"):
        base = os.environ.get(env)
        if base and (Path(base) / "Desktop").is_dir():
            return Path(base) / "Desktop"
    return Path.home() / "Desktop"


def main():
    app = HERE / "app.py"
    if not app.exists():
        raise SystemExit("Khong thay app.py canh file nay: %s" % HERE)

    icon = HERE / "yap_icon.ico"
    if not icon.exists():
        print("Chua co yap_icon.ico, dang ve lai...")
        import runpy
        runpy.run_path(str(HERE / "tao-icon.py"), run_name="__main__")

    exe, prefix = find_launcher()
    link = desktop_dir() / NAME

    try:
        import win32com.client
    except ImportError:
        raise SystemExit("Thieu pywin32. Chay setup.bat truoc.")

    sh = win32com.client.Dispatch("WScript.Shell")
    sc = sh.CreateShortCut(str(link))
    sc.TargetPath = str(exe)
    sc.Arguments = '%s"%s"' % (prefix, app)
    sc.WorkingDirectory = str(HERE)      # de app tim thay .env canh no
    sc.IconLocation = "%s,0" % icon
    sc.Description = "Yap - doc chinh ta, giu Right Ctrl de noi"
    sc.WindowStyle = 7                   # thu nho, khong nhay len man hinh
    sc.save()

    print("Da dat shortcut : %s" % link)
    print("Tro toi         : %s %s" % (exe.name, sc.Arguments))
    print("Chay trong      : %s" % HERE)
    print()
    print("Chuyen thu muc di noi khac thi chay lai file nay mot lan.")


if __name__ == "__main__":
    main()
