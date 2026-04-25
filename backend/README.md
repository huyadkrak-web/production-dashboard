# 생산일보 백엔드 (로컬 실행)

## 구조

- **엔트리**: `app/main.py` — FastAPI `app` 객체, `/compute` 등 라우트 정의
- **계산 로직**: `app/compute.py` — `compute_tables(...)` (엑셀 바이트 + 기준/플랜/수기 불량)
- **데이터(JSON)**: `backend/data/` — `master.json`, `plan_YYYY-MM.json`, `defects.json` 등 (`app/store.py` 기준)

## Python 환경

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 실행 (localhost:8000)

프로젝트 루트가 **`backend`** 인 상태에서 모듈 경로 `app.main:app` 로 실행합니다.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 브라우저 문서: http://127.0.0.1:8000/docs  
- 헬스: `GET http://127.0.0.1:8000/health`

## `/compute` 요청 형식

- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **필드**:
  - `base_date`: 날짜 (예: `2026-03-18`)
  - `today_file`: 작업일보 엑셀 1개 (시트명 등은 `app/settings.py` 기준). 누적/전일 집계 모두 이 파일에서 수행합니다.

엑셀에는 `settings.py`에 맞는 시트/컬럼이 있어야 합니다 (예: `작업일보` 시트).

### curl 예시 (파일 경로만 본인 환경에 맞게 수정)

```powershell
curl.exe -X POST "http://127.0.0.1:8000/compute" `
  -F "base_date=2026-03-18" `
  -F "today_file=@C:\path\to\today.xlsx"
```

성공 시 JSON으로 `meta`, `생산진척현황`, `조립공정불량` 이 반환됩니다.

## 환경변수 (선택)

`app/settings.py`는 **`SAENGSAN_` 접두사**로 시트명·컬럼명을 덮어쓸 수 있습니다.  
미설정 시 코드에 있는 기본값(한글 시트/컬럼명)을 사용합니다.

예: `SAENGSAN_SHEET_WORK_TODAY=작업일보`

## CORS

기본으로 `localhost:5173` 등 Vite 개발 서버 Origin만 허용합니다.  
프론트를 다른 포트에서 띄우면 `app/main.py`의 `allow_origins`에 추가하세요.
