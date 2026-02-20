#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
브라우저 업데이트 현황 확인기 (Windows / Tkinter)

- 맨 위 BROWSER_CONFIG만 수정하면 됨
- 설치 버전: PowerShell로 exe FileVersion 읽기 (ctypes 없음)
- 최신 버전: 각 브라우저 공개 소스 조회
- 캐시/로그파일 없음, print()만 사용
- 아이콘 없음(텍스트 색상만)
"""

import json
import os
import re
import subprocess
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk
import urllib.request


# =========================================================
# 1) 설정: 여기만 수정하면 됨
# =========================================================

BROWSER_CONFIG = [
    {
        "name": "Chrome",
        "latest_key": "chrome",
        "download_url": "https://www.google.com/chrome/",
        "exe_paths": [
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        ],
    },
    {
        "name": "Edge",
        "latest_key": "edge",
        "download_url": "https://www.microsoft.com/edge",
        "exe_paths": [
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        ],
    },
    {
        "name": "Firefox",
        "latest_key": "firefox",
        "download_url": "https://www.mozilla.org/firefox/new/",
        "exe_paths": [
            r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
        ],
    },
    {
        "name": "Opera",
        "latest_key": "opera",
        "download_url": "https://www.opera.com/download",
        "exe_paths": [
            r"%ProgramFiles%\Opera\opera.exe",
            r"%ProgramFiles%\Opera\launcher.exe",
            r"%ProgramFiles(x86)%\Opera\opera.exe",
            r"%ProgramFiles(x86)%\Opera\launcher.exe",
            r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
        ],
    },
]


# =========================================================
# 2) print() 로그
# =========================================================

def p(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# =========================================================
# 3) 공통: HTTP / 버전 비교
# =========================================================

def fetch_json(url: str, timeout: int = 10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception as e:
        p(f"JSON 실패: {url} / {e}")
        return None


def fetch_text(url: str, timeout: int = 15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        p(f"TEXT 실패: {url} / {e}")
        return None


def compare_versions(v1: str, v2: str) -> int:
    # 1.2.3.4 형태를 숫자 리스트로 만들어서 비교
    def parse(v: str):
        out = []
        for x in v.split("."):
            if x.isdigit():
                out.append(int(x))
        return out

    a = parse(v1)
    b = parse(v2)

    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))

    for x, y in zip(a, b):
        if x > y:
            return 1
        if x < y:
            return -1
    return 0


def determine_status(local, latest) -> str:
    if local is None:
        return "미설치"
    if latest is None:
        return "확인 실패"
    return "업데이트 필요" if compare_versions(local, latest) < 0 else "최신 버전"


# =========================================================
# 4) 설치 버전 읽기 (PowerShell ONLY)
# =========================================================

def get_file_version_powershell(exe_path: str):
    """
    PowerShell로 exe FileVersion 읽기
    - 성공: "123.0.4567.89" 같은 문자열
    - 실패: None
    """
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Item '{exe_path}').VersionInfo.FileVersion",
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        return out or None
    except Exception:
        return None


def get_local_version(exe_paths):
    """
    설치 버전:
    - 환경변수(%ProgramFiles% 등) 확장
    - 실제 존재하는 exe를 찾고
    - PowerShell로 FileVersion 읽기
    """
    for raw in exe_paths:
        exe = os.path.expandvars(raw)
        if not os.path.exists(exe):
            continue

        v = get_file_version_powershell(exe)
        if v:
            return v

    return None


# =========================================================
# 5) 최신 버전 조회 (브라우저별)
# =========================================================

def latest_chrome():
    data = fetch_json("https://versionhistory.googleapis.com/v1/chrome/platforms/win64/channels/stable/versions")
    if not data:
        return None

    versions = data.get("versions") or []
    if not versions:
        return None

    v = versions[0].get("version")
    return v if isinstance(v, str) and v else None


def latest_edge():
    data = fetch_json("https://edgeupdates.microsoft.com/api/products")
    if not data:
        return None

    latest = None
    for product in data:
        if product.get("Product") != "Stable":
            continue

        for rel in product.get("Releases", []):
            if rel.get("Platform") != "Windows":
                continue
            if rel.get("Architecture") not in ("x64", "x86"):
                continue

            v = rel.get("ProductVersion")
            if not (isinstance(v, str) and v):
                continue

            if latest is None or compare_versions(v, latest) > 0:
                latest = v

    return latest


def latest_firefox():
    data = fetch_json("https://product-details.mozilla.org/1.0/firefox_versions.json")
    if not data:
        return None

    v = data.get("LATEST_FIREFOX_VERSION")
    return v if isinstance(v, str) and v else None


def latest_opera():
    html = fetch_text("https://get.geo.opera.com/ftp/pub/opera/desktop/")
    if not html:
        return None

    # 127.0.0000.00/ 형태 추출 후 최댓값 선택
    candidates = re.findall(r"(\d+\.\d+\.\d+\.\d+)/", html)

    latest = None
    for v in candidates:
        if latest is None or compare_versions(v, latest) > 0:
            latest = v

    return latest


LATEST_FETCHERS = {
    "chrome": latest_chrome,
    "edge": latest_edge,
    "firefox": latest_firefox,
    "opera": latest_opera,
}


# =========================================================
# 6) UI
# =========================================================

class BrowserCheckerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("브라우저 업데이트 확인")
        self.root.minsize(720, 280)

        self.by_name = {x["name"]: x for x in BROWSER_CONFIG}

        # 상단 상태
        top = tk.Frame(root)
        top.pack(fill="x", padx=10, pady=(10, 6))

        self.lbl = tk.Label(top, text="준비됨", anchor="w")
        self.lbl.pack(side="left", fill="x", expand=True)

        tk.Button(top, text="새로고침", command=self.refresh).pack(side="right")

        # 테이블
        self.tree = ttk.Treeview(root, columns=("name", "local", "latest", "status"), show="headings", height=8)
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        self.tree.heading("name", text="브라우저")
        self.tree.heading("local", text="내 PC 버전")
        self.tree.heading("latest", text="최신 버전")
        self.tree.heading("status", text="상태")

        self.tree.column("name", width=120, anchor="w")
        self.tree.column("local", width=180, anchor="w")
        self.tree.column("latest", width=180, anchor="w")
        self.tree.column("status", width=120, anchor="w")

        # 색상(아이콘 없음)
        self.tree.tag_configure("ok", foreground="#0f7b0f")
        self.tree.tag_configure("need", foreground="#c1121f")
        self.tree.tag_configure("none", foreground="#6b7280")
        self.tree.tag_configure("fail", foreground="#6b7280")

        # 하단 버튼
        bottom = tk.Frame(root)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        tk.Button(bottom, text="업데이트 페이지 열기", command=self.open_download).pack(side="left")
        tk.Button(bottom, text="선택 행 복사", command=self.copy_selected).pack(side="left", padx=(8, 0))

        self.tree.bind("<Double-1>", lambda e: self.open_download())

        # 초기 행 생성
        for c in BROWSER_CONFIG:
            name = c["name"]
            self.tree.insert("", "end", iid=name, values=(name, "", "", ""), tags=("none",))

        self.refresh()

    def set_status(self, text: str) -> None:
        self.lbl.config(text=text)

    def refresh(self) -> None:
        self.set_status("조회 중…")
        p("새로고침 시작")

        for c in BROWSER_CONFIG:
            name = c["name"]
            self.tree.item(name, values=(name, "...", "...", "조회 중…"), tags=("none",))

        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        for c in BROWSER_CONFIG:
            name = c["name"]
            latest_key = c["latest_key"]

            local = get_local_version(c["exe_paths"])

            fn = LATEST_FETCHERS.get(latest_key)
            latest = fn() if fn else None

            status = determine_status(local, latest)

            if status == "최신 버전":
                tag = "ok"
            elif status == "업데이트 필요":
                tag = "need"
            elif status == "미설치":
                tag = "none"
            else:
                tag = "fail"

            def ui_update(n=name, lv=local, rv=latest, st=status, tg=tag):
                self.tree.item(n, values=(n, lv or "", rv or "", st), tags=(tg,))

            self.root.after(0, ui_update)

        self.root.after(0, lambda: self.set_status("완료"))
        p("새로고침 완료")

    def selected_name(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def open_download(self) -> None:
        name = self.selected_name()
        if not name:
            self.set_status("선택된 브라우저가 없습니다.")
            return

        url = self.by_name.get(name, {}).get("download_url")
        if not url:
            self.set_status("다운로드 URL 정보가 없습니다.")
            return

        webbrowser.open(url)
        self.set_status(f"열기: {name}")

    def copy_selected(self) -> None:
        name = self.selected_name()
        if not name:
            self.set_status("선택된 행이 없습니다.")
            return

        vals = self.tree.item(name, "values")
        text = f"브라우저: {vals[0]}\n내 PC 버전: {vals[1]}\n최신 버전: {vals[2]}\n상태: {vals[3]}"

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.set_status("클립보드 복사 완료")
        except Exception:
            self.set_status("복사 실패")


def main() -> None:
    root = tk.Tk()
    BrowserCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()