# 브라우저 업데이트 확인 프로그램 (Windows)

Windows PC에 설치된 주요 브라우저(Chrome / Edge / Firefox / Opera)의  
**설치된 버전과 최신 버전을 비교**하여  
업데이트 필요 여부를 한눈에 확인할 수 있는 Tkinter 기반 GUI 프로그램입니다.

---

## 주요 특징

- **설정은 한 곳에서 관리**
  - `BROWSER_CONFIG`만 수정하면 브라우저 추가/변경 가능
- **내 PC 버전 조회**
  - PowerShell을 이용해 exe 파일의 `FileVersion`을 직접 조회
- **최신 버전 조회**
  - 각 브라우저의 공식 공개 API / 페이지 사용
- **PyInstaller EXE 배포 가능**

---

## 전체 동작 흐름 요약

설정 로드  
→ GUI 초기화  
→ 로컬 설치 버전 조회  
→ 최신 버전 조회  
→ 버전 비교  
→ 상태 표시  

---

## 브라우저 설정 로드

프로그램 시작 시 `BROWSER_CONFIG`를 가장 먼저 읽습니다.

각 브라우저마다 다음 정보를 정의합니다:

- `name` : 화면 표시 이름
- `exe_paths` : 설치 exe 경로 후보
- `latest_key` : 최신 버전 조회 함수 키
- `download_url` : 업데이트 페이지 URL

**※ 브라우저 추가/수정은 이 영역만 변경하면 됩니다.**

---

## 로컬 설치 버전 조회 (내 PC)

- `exe_paths`에 정의된 경로를 순서대로 확인
- `%ProgramFiles%`, `%LOCALAPPDATA%` 등 환경변수 실제 경로로 확장
- exe 파일이 존재하면 PowerShell 실행:

```
(Get-Item 'chrome.exe').VersionInfo.FileVersion
```

- 성공 시 버전 문자열 반환 (예: `122.0.6261.70`)
- 전부 실패하면 **미설치**

⚠️ PowerShell 방식만 사용하여,  
PowerShell 실행이 제한된 환경에서는 버전 확인이 실패할 수 있습니다.

---

## 최신 버전 조회 (인터넷)

브라우저별 공식 공개 정보를 사용합니다.

| 브라우저 | 최신 버전 조회 방식 |
|--------|------------------|
| Chrome | Google VersionHistory API |
| Edge | Microsoft Edge Update API |
| Firefox | Mozilla product-details JSON |
| Opera | Opera FTP 디렉토리 HTML 파싱 |

---

## 버전 비교 및 상태 결정

| 조건 | 표시 상태 |
|----|---------|
| 로컬 버전 없음 | 미설치 |
| 최신 버전 조회 실패 | 확인 실패 |
| 로컬 < 최신 | 업데이트 필요 |
| 로컬 ≥ 최신 | 최신 버전 |

---

## exe 빌드 (PyInstaller)

콘솔 포함(EXE 실행 시 로그 확인):

```
pyinstaller --onefile browser_version_checker.py
```

콘솔 숨김(EXE만 실행):

```
pyinstaller --onefile --noconsole browser_version_checker.py
```