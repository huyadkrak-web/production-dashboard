# 생산일보 웹 프로그램 (v1)

엑셀 생산일보를 대신하는 **간단한 대시보드** 버전입니다.

## 구성

- `backend/`: Python FastAPI + pandas(openpyxl)
- `frontend/`: React (Vite) 대시보드

## 실행 방법

### 1) 백엔드

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2) 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속 후 파일 2개 업로드 + 기준일 선택 → 계산 결과 표가 출력됩니다.

## 엑셀 컬럼(기본 가정)

v1은 아래 컬럼명이 있다고 가정하고 집계합니다. 실제 양식이 다르면 `backend/app/settings.py`에서 컬럼명을 바꾸면 됩니다.

- 제품: `제품`
- 공정: `공정`
- 일자: `일자`
- 월계획: `월계획`
- 일계획: `일계획`
- 실적(양품): `실적`
- 조립실적: `조립실적` (없으면 `실적`으로 대체)
- 불량개수: `불량개수`

