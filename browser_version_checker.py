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
import urllib.error
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
    """전체 버전 비교 (내부 정렬용)"""
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


def get_major(v: str) -> int:
    """버전 문자열에서 메이저(첫 번째 숫자)만 추출. 예: '145.0.7632.118' → 145"""
    try:
        return int(v.split(".")[0])
    except Exception:
        return -1


def determine_status(local, latest) -> str:
    """메이저 버전(맨 앞 숫자)만 비교해서 최신 여부 판단.
    예: local=145.x.x, latest=145.x.x → 최신 버전
        local=144.x.x, latest=145.x.x → 업데이트 필요
    """
    if local is None:
        return "미설치"
    if latest is None:
        return "확인 실패"
    lm = get_major(local)
    rm = get_major(latest)
    if lm < rm:
        return "업데이트 필요"
    return "최신 버전"


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
        safe_path = exe_path.replace("'", "''")  # PowerShell 작은따옴표 이스케이프
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-Item '{safe_path}').VersionInfo.FileVersion",
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

def _chrome_version_from_releases_api(channel: str):
    """
    Chrome releases API에서 특정 채널의 최신 버전을 가져옴.

    versions API 대신 releases API를 사용하는 이유:
    - versions API(versionhistory)는 단계적 롤아웃 중인 버전도 즉시 목록에 추가됨
    - releases API는 실제 배포 완료(fraction=1.0) 기준으로 버전을 제공하므로 더 정확함

    예: 146이 일부 사용자에게만 배포 중일 때 versions API에는 146이 첫 번째로 표시되지만,
        releases API에서 fraction=1.0 기준으로 필터하면 145가 최신으로 반환됨.
    """
    url = (
        f"https://versionhistory.googleapis.com/v1/chrome/platforms/win64"
        f"/channels/{channel}/versions/all/releases"
        f"?orderBy=startTime%20desc&filter=endtime=none"
    )
    data = fetch_json(url)
    if not data:
        return None

    releases = data.get("releases") or []

    # fraction이 1.0인 것(완전 배포 완료)만 추려서 가장 높은 버전 반환
    # 없으면 fraction 무관하게 가장 높은 버전 반환
    best_full = None
    best_any = None

    for rel in releases:
        v = rel.get("version")
        if not (isinstance(v, str) and v):
            continue
        fraction = rel.get("fraction", 0)

        if best_any is None or compare_versions(v, best_any) > 0:
            best_any = v
        if fraction >= 1.0:
            if best_full is None or compare_versions(v, best_full) > 0:
                best_full = v

    result = best_full if best_full else best_any
    p(f"Chrome {channel}: best_full={best_full}, best_any={best_any} → {result}")
    return result


def latest_chrome():
    return _chrome_version_from_releases_api("stable")


def latest_chrome_beta():
    return _chrome_version_from_releases_api("beta")


def _edge_versions():
    """Edge API를 한 번만 호출해서 stable, beta 버전을 동시에 반환."""
    data = fetch_json("https://edgeupdates.microsoft.com/api/products")
    stable = None
    beta = None
    if not data:
        return stable, beta

    for product in data:
        kind = product.get("Product")
        if kind not in ("Stable", "Beta"):
            continue

        for rel in product.get("Releases", []):
            if rel.get("Platform") != "Windows":
                continue
            if rel.get("Architecture") not in ("x64", "x86"):
                continue
            v = rel.get("ProductVersion")
            if not (isinstance(v, str) and v):
                continue

            if kind == "Stable":
                if stable is None or compare_versions(v, stable) > 0:
                    stable = v
            else:
                if beta is None or compare_versions(v, beta) > 0:
                    beta = v

    return stable, beta


# 캐시: _work()에서 브라우저별 스레드가 동시에 호출해도 한 번만 요청
_edge_cache = {}
_edge_lock  = threading.Lock()

def _get_edge_versions():
    with _edge_lock:
        if not _edge_cache:
            s, b = _edge_versions()
            _edge_cache["stable"] = s
            _edge_cache["beta"]   = b
    return _edge_cache["stable"], _edge_cache["beta"]


def latest_edge():
    return _get_edge_versions()[0]


def latest_edge_beta():
    return _get_edge_versions()[1]


def _firefox_versions():
    """Firefox API를 한 번만 호출해서 stable, beta 버전을 동시에 반환."""
    data = fetch_json("https://product-details.mozilla.org/1.0/firefox_versions.json")
    if not data:
        return None, None
    stable = data.get("LATEST_FIREFOX_VERSION")
    beta   = data.get("LATEST_FIREFOX_DEVEL_VERSION") or data.get("FIREFOX_DEVEDITION")
    stable = stable if isinstance(stable, str) and stable else None
    beta   = beta   if isinstance(beta,   str) and beta   else None
    return stable, beta


_firefox_cache = {}
_firefox_lock  = threading.Lock()

def _get_firefox_versions():
    with _firefox_lock:
        if not _firefox_cache:
            s, b = _firefox_versions()
            _firefox_cache["stable"] = s
            _firefox_cache["beta"]   = b
    return _firefox_cache["stable"], _firefox_cache["beta"]


def latest_firefox():
    return _get_firefox_versions()[0]


def latest_firefox_beta():
    return _get_firefox_versions()[1]


def _opera_latest_from_ftp(ftp_url: str):
    """
    오페라 FTP 인덱스 페이지에서 버전 디렉터리 목록을 파싱해 최신 버전 반환.
    채널별 FTP 경로:
      Stable   : https://get.geo.opera.com/ftp/pub/opera/desktop/
      Beta     : https://get.geo.opera.com/ftp/pub/opera-beta/
      Developer: https://get.geo.opera.com/ftp/pub/opera-developer/
    """
    html = fetch_text(ftp_url)
    if not html:
        return None
    candidates = re.findall(r"(\d+\.\d+\.\d+\.\d+)/", html)
    latest = None
    for v in candidates:
        if latest is None or compare_versions(v, latest) > 0:
            latest = v
    p(f"Opera FTP [{ftp_url}] → {latest}")
    return latest


def latest_opera():
    return _opera_latest_from_ftp("https://get.geo.opera.com/ftp/pub/opera/desktop/")


def latest_opera_beta():
    # Beta와 Developer 중 더 높은 버전 반환
    beta = _opera_latest_from_ftp("https://get.geo.opera.com/ftp/pub/opera-beta/")
    dev  = _opera_latest_from_ftp("https://get.geo.opera.com/ftp/pub/opera-developer/")
    if beta and dev:
        return beta if compare_versions(beta, dev) >= 0 else dev
    return beta or dev


LATEST_FETCHERS = {
    "chrome":  (latest_chrome,       latest_chrome_beta),
    "edge":    (latest_edge,         latest_edge_beta),
    "firefox": (latest_firefox,      latest_firefox_beta),
    "opera":   (latest_opera,        latest_opera_beta),
}


# =========================================================
# 6) UI
# =========================================================

COLUMNS = ("name", "local", "latest", "status", "beta")
COL_HEADERS = {
    "name":   "브라우저",
    "local":  "내 PC 버전",
    "latest": "최신 버전 (Stable)",
    "status": "상태",
    "beta":   "베타 버전",
}
COL_WIDTHS = {
    "name":   110,
    "local":  160,
    "latest": 160,
    "status": 110,
    "beta":   160,
}


class BrowserCheckerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("브라우저 업데이트 확인")
        self.root.minsize(800, 280)

        self.by_name = {x["name"]: x for x in BROWSER_CONFIG}

        # 상단 상태
        top = tk.Frame(root)
        top.pack(fill="x", padx=10, pady=(10, 6))

        self.lbl = tk.Label(top, text="준비됨", anchor="w")
        self.lbl.pack(side="left", fill="x", expand=True)

        tk.Button(top, text="새로고침", command=self.refresh).pack(side="right")

        # 테이블
        self.tree = ttk.Treeview(
            root, columns=COLUMNS, show="headings", height=8
        )
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        for col in COLUMNS:
            self.tree.heading(col, text=COL_HEADERS[col])
            anchor = "w" if col != "status" else "center"
            self.tree.column(col, width=COL_WIDTHS[col], anchor=anchor)

        # 색상 태그
        self.tree.tag_configure("ok",   foreground="#0f7b0f")
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
            self.tree.insert("", "end", iid=name,
                             values=(name, "", "", "", ""), tags=("none",))

        self.refresh()

    def set_status(self, text: str) -> None:
        self.lbl.config(text=text)

    def refresh(self) -> None:
        self.set_status("조회 중…")
        p("새로고침 시작")

        # 새로고침마다 Edge/Firefox 캐시 초기화 (최신 데이터 재조회)
        _edge_cache.clear()
        _firefox_cache.clear()

        for c in BROWSER_CONFIG:
            name = c["name"]
            self.tree.item(name,
                           values=(name, "...", "...", "조회 중…", "..."),
                           tags=("none",))

        threading.Thread(target=self._work, daemon=True).start()

    def _fetch_one(self, c: dict, results: dict, done_event: threading.Event, remaining: list) -> None:
        """브라우저 1개 조회 후 results에 저장, 모두 끝나면 done_event 세팅."""
        name       = c["name"]
        latest_key = c["latest_key"]

        local = get_local_version(c["exe_paths"])

        fetchers = LATEST_FETCHERS.get(latest_key, (None, None))
        fn_stable, fn_beta = fetchers

        latest = fn_stable() if fn_stable else None
        beta   = fn_beta()   if fn_beta   else None

        status = determine_status(local, latest)
        tag = {"최신 버전": "ok", "업데이트 필요": "need",
               "미설치": "none"}.get(status, "fail")

        results[name] = (local, latest, status, tag, beta)

        # UI 즉시 반영 (조회 완료 순서대로)
        def ui_update(n=name, lv=local, rv=latest, st=status, tg=tag, bv=beta):
            self.tree.item(n,
                           values=(n, lv or "", rv or "", st, bv or ""),
                           tags=(tg,))
        self.root.after(0, ui_update)

        with threading.Lock():
            remaining.remove(name)
            if not remaining:
                done_event.set()

    def _work(self) -> None:
        results   = {}
        remaining = [c["name"] for c in BROWSER_CONFIG]
        done      = threading.Event()

        threads = []
        for c in BROWSER_CONFIG:
            t = threading.Thread(
                target=self._fetch_one,
                args=(c, results, done, remaining),
                daemon=True,
            )
            threads.append(t)
            t.start()

        done.wait()
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
        text = (
            f"브라우저: {vals[0]}\n"
            f"내 PC 버전: {vals[1]}\n"
            f"최신 버전 (Stable): {vals[2]}\n"
            f"상태: {vals[3]}\n"
            f"베타 버전: {vals[4]}"
        )

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
