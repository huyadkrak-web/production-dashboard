# 수정 계획: 기준정보/월간플랜 백엔드 저장 + 공정순서 display_order 기준

## 목표 요약

- **제품(product) 가변**: 이 프로그램은 **UDP에 한정되지 않으며**, 132FBGA 등 다른 자재/제품에도 적용된다. **product를 고정값으로 두지 않고**, 기준정보와 월간플랜은 반드시 **product 단위로 관리**한다.
- **기준정보·월간플랜**: 프론트에서 매번 보내지 않음. **백엔드에 저장**하고, `/compute` 호출 시 서버가 저장된 데이터를 읽어서 계산.
- **공정순서**: `initial_processes` 등 하드코딩 제거. 기준정보의 **display_order** 만으로 정렬.
- **compute.py 내부 기준키**: **product + process_code** 를 일관되게 사용한다. (단일 제품 가정 없음.)
- **compute.py 내부 컬럼**: 일괄 문자열 치환 금지. **경계에서만**  
  - 작업일보 Excel → 내부 표준 컬럼으로 **rename**  
  - 기준정보 JSON → 내부 표준 컬럼으로 **DataFrame 생성**  
  - 월간플랜 JSON → 내부 표준 컬럼으로 **DataFrame 생성**  
  이후 로직은 **내부 표준 컬럼명만** 사용.

---

## 설계 보정 요약 (product 단위 관리)

1. **기준정보 필드** (유지): product, process_code, process_name, process_group, is_assembly, display_order, is_active.
2. **월간플랜 필드** (유지): month, product, process_code, month_plan, prev_day_plan.
3. **compute.py 내부 기준키**: **product + process_code** 로 통일. (단일 제품 가정 없음.)
4. **프론트 기준정보/월간플랜 화면**: **product 단위**로 입력·조회. 테이블에 product 컬럼 포함, 여러 제품(UDP, 132FBGA 등) 공존 가능. 제품 필터/선택 옵션 권장.
5. **product 고정 금지**: UDP로 고정하지 않으며, 다른 자재/제품에도 적용 가능하도록 설계.

---

## API 구조 (최종)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /master | 저장된 기준정보 전체 조회 |
| POST | /master | 기준정보 전체 저장 (기존 파일 백업 후 저장) |
| GET | /plan/{month} | 해당 월(예: 2025-03) 월간플랜 조회 |
| POST | /plan/{month} | 해당 월 월간플랜 저장 (기존 파일 백업 후 저장) |
| POST | /compute | base_date, today_file, prev_file 만 받음. 저장된 기준정보/월간플랜을 읽어 계산 |
| GET | /defects | 누적불량유형 수기 입력 목록 조회 (query: date 등 선택) |
| POST | /defects | 누적불량유형 수기 입력 목록 저장 (백업 후 저장) |

---

## 데이터 흐름 (변경 후)

```
[기준정보 입력 화면]  → POST /master  (저장)   → 백엔드 파일 저장 (+ 백업)
[월간플랜 입력 화면]  → POST /plan/{month} (저장) → 백엔드 파일 저장 (+ 백업)
[생산일보 계산]       → POST /compute (base_date, today_file, prev_file)
                        → 백엔드가 GET /master, GET /plan/{month}와 동일한 저장소에서 읽어 compute_tables() 호출
```

- **today_file**: 작업일보 시트만 사용 (해당 시트만 있으면 됨).
- **prev_file**: 전일작업일보 시트만 사용.
- 기준정보/월간플랜은 **요청 바디에 포함하지 않음**.

---

## 저장소 및 백업

- **저장 위치**: 예) `backend/data/master.json`, `backend/data/plan_{month}.json` (month 형식 예: `2025-03`).
- **저장 시 백업**:
  - POST /master: 저장 전 기존 `master.json`이 있으면 `data/backup/master_{YYYYMMDD_HHMMSS}.json` 등으로 복사 후 덮어쓰기.
  - POST /plan/{month}: 저장 전 기존 `plan_{month}.json`이 있으면 `data/backup/plan_{month}_{YYYYMMDD_HHMMSS}.json`으로 복사 후 덮어쓰기.

---

## 필드 정의

- **product** 는 고정값(UDP 등)이 아니다. UDP, 132FBGA 등 **여러 제품/자재를 구분하는 차원**이며, 기준정보·월간플랜 모두 **product 단위**로 입력·저장·조회한다.

### 기준정보 (master)

| 필드 | 타입 | 비고 |
|------|------|------|
| product | string | 제품/자재 구분 (UDP, 132FBGA 등). 반드시 관리. |
| process_code | string | |
| process_name | string | |
| process_group | string | |
| is_assembly | string | Y/N 등 |
| display_order | number | 정렬에 사용 |
| is_active | boolean 또는 string | 사용 여부, 미사용 행은 compute에서 제외 가능 |

### 월간플랜 (plan)

| 필드 | 타입 | 비고 |
|------|------|------|
| month | string | 예: "2025-03" (GET/POST 경로와 동일한 형식) |
| product | string | 제품/자재 구분. product 단위 관리. |
| process_code | string | |
| month_plan | number | |
| prev_day_plan | number | |

---

## 조립 공정 불량 계산 기준 (A 방식 확정)

- **조립실적 누적**: 작업일보 Excel (조립 공정의 생산수량 누적).
- **전일 조립 실적**: 전일작업일보 Excel (조립 공정의 생산수량 전일).
- **전일불량개수**: Excel Reject (전일작업일보).
- **전일불량율(PPM)**: Excel Reject / 전일 조립 실적.
- **누적불량개수**: Excel Reject 누적 (작업일보 기준일까지).
- **누적불량율(PPM)**: Excel Reject 누적 / 조립실적 누적.
- **누적불량유형**: 사용자가 매일 수기 입력하는 **참고용** 데이터. 전일불량개수·누적불량개수 계산의 기준값이 **아님**. 별도 저장/조회 후, compute 결과의 조립 공정 불량 표에 **참고용 문자열로만** 붙여서 표시.

즉, defect input(수기 입력)의 defect_name / qty 는 PPM·개수 계산에 사용하지 않고, **누적불량유형** 표시용 문자열만 만드는 데 사용한다.

---

## Defect Input (누적불량유형 수기 입력) — 추가 구조

- **역할**: 조립 공정별 “누적불량유형” 표시용 문자열의 원천. 계산 로직에는 미반영.
- **필드**: date, product, process_code, defect_name, qty.
- **저장**: 백엔드 저장소 (예: `data/defects.json` 또는 날짜별 `data/defects_{date}.json`). 저장 시 백업 권장.
- **compute.py**: 저장된 defect input을 (기준일·구간에 맞게) 읽어, (product, process_code)별로 “defect_name : qty” 형태 문자열을 만든 뒤, **조립 공정 불량** 결과의 `defect_cumulative_types`(누적불량유형)에 **참고용**으로만 붙인다. 전일/누적 불량개수·PPM은 **Excel Reject**만 사용.

### Defect Input 필드 정의

| 필드 | 타입 | 비고 |
|------|------|------|
| date | string | YYYY-MM-DD |
| product | string | 제품 |
| process_code | string | 공정코드 (조립 공정) |
| defect_name | string | 불량 유형명 (수기 입력) |
| qty | number | 수량 (참고용, 계산에 미사용) |

### API 추가 (defect)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /defects | 전체 또는 query로 기간/제품 필터 조회 |
| POST | /defects | defect 입력 목록 저장 (기존 백업 후 저장) |

(또는 GET/POST `/defects?date=YYYY-MM-DD` 등으로 날짜 단위 저장·조회.)

---

## compute.py 내부 표준 컬럼 (통일 규칙)

**일괄 치환하지 않고**, 다음만 적용한다.

1. **작업일보 Excel**  
   - `settings.work_col_*` 로 읽은 뒤, **한 번만** 내부 표준 컬럼명으로 rename.  
   - 내부 표준명 예: `product`, `process_code`, `process_name`, `work_date`, `good_qty`, `defect_qty`, `defect_type`.

2. **기준정보 (저장소 JSON → DataFrame)**  
   - API/저장 필드와 동일한 이름으로 DataFrame 생성:  
     `product`, `process_code`, `process_name`, `process_group`, `is_assembly`, `display_order`, `is_active`.  
   - `is_active` 가 False/비활성인 행은 계산에서 제외(필터).

3. **월간플랜 (저장소 JSON → DataFrame)**  
   - API/저장 필드와 동일한 이름으로 DataFrame 생성:  
     `month`, `product`, `process_code`, `month_plan`, `prev_day_plan`.

4. **compute.py 내부 로직**  
   - 위 세 소스에서 만든 DataFrame은 모두 **내부 표준 컬럼명**만 사용.  
   - **내부 기준키는 반드시 product + process_code** 로 통일. (UDP 등 단일 제품 가정 없음.)  
   - 기준/플랜/작업일보 조인·인덱스: 모두 `(product, process_code)`.  
   - 정렬: `display_order` 만 사용 (`initial_processes` 제거).

---

## 파일별 수정 계획

| 파일 | 수정 요약 |
|------|-----------|
| **backend/app/settings.py** | `initial_processes`, `process_list()` 제거. |
| **backend/app/store.py** (신규) | 기준정보/월간플랜 JSON 파일 읽기·쓰기, 저장 전 백업 로직. |
| **backend/app/compute.py** | (1) 기준/플랜을 Excel이 아닌 **DataFrame 인자**로 받음. (2) 작업일보 Excel 로드 후 **내부 표준 컬럼으로 rename**하는 단계 추가. (3) 기준/플랜은 호출부에서 저장소 로드 결과(이미 내부 표준 컬럼 DataFrame)를 넘김. (4) 정렬은 display_order 만 사용. (5) **기존 settings.master_col_* / plan_col_* / work_col_*** 는 **경계(로드/rename)에서만** 사용하고, 그 안쪽은 내부 표준명만 사용. |
| **backend/app/models.py** | MasterRow(is_active 포함), PlanRow(month, prev_day_plan), 저장/조회 응답 모델. |
| **backend/app/main.py** | GET/POST /master, GET/POST /plan/{month}, POST /compute(base_date, today_file, prev_file). compute 호출 전 store에서 master/plan 로드 후 compute_tables에 전달. |
| **frontend/src/api.ts** | GET/POST master, GET/POST plan/{month}, computeIlbo는 baseDate, todayFile, prevFile 만. MasterRow/PlanRow 타입에 is_active, plan에는 month, prev_day_plan 반영. |
| **frontend/src/App.tsx** | 기준정보/월간플랜 화면을 **product 단위**로 입력·조회. GET /master, GET /plan/{month} 로드 후 product 컬럼 포함 테이블로 표시, product 필터/선택 가능. 저장 시 POST /master, POST /plan/{month}. 계산 시 computeIlbo(baseDate, todayFile, prevFile) 만 호출. **누적불량유형(defect input)** 화면: 날짜·제품·공정별 수기 입력, GET/POST /defects. |
| **backend/app/store.py** | defect 입력용 get_defects() / save_defects() 추가 (저장 전 백업). |
| **backend/app/models.py** | DefectInputRow(date, product, process_code, defect_name, qty) 추가. |
| **backend/app/main.py** | GET /defects, POST /defects 추가. compute 호출 시 get_defects() 로드 후 compute_tables에 전달. |
| **backend/app/compute.py** | 조립 공정 불량 행의 defect_cumulative_types 에만 defect input 기반 문자열 참고용 병합. 전일/누적 불량개수·PPM은 Excel Reject 전용 유지. |

---

## 1. backend/app/settings.py — diff 초안

```diff
--- a/backend/app/settings.py
+++ b/backend/app/settings.py
@@ -42,14 +42,6 @@ class Settings(BaseSettings):
     plan_col_month_name: str = "월명"  # 예: "3월"
     plan_col_month_target: str = "월계획합계"  # 상단 요약 14,000ea 등

-    # 초기 공정 목록 (표 정렬용)
-    initial_processes: str = (
-        "Controller D/A|D/A|W/B 1 (NAND+Cont)|Mold|Laser Marking|PKG Singulation"
-    )
-
     # Front / Back End 그룹명 기본값
     front_group_name: str = "Front"
     backend_group_name: str = "Back End"
-
-    def process_list(self) -> list[str]:
-        return [p.strip() for p in self.initial_processes.split("|") if p.strip()]
```

---

## 2. backend/app/store.py — 신규 (초안)

- 역할: 기준정보/월간플랜 JSON 파일 경로 관리, 읽기, 쓰기, **저장 전 백업**.
- 기준정보: `data/master.json`, 백업 `data/backup/master_{timestamp}.json`.
- 월간플랜: `data/plan_{month}.json`, 백업 `data/backup/plan_{month}_{timestamp}.json`.
- `get_master() -> list[dict]`, `save_master(data: list[dict]) -> None` (저장 전 백업),
- `get_plan(month: str) -> list[dict]`, `save_plan(month: str, data: list[dict]) -> None` (저장 전 백업).

```python
# backend/app/store.py (신규) — 구조만
# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKUP_DIR = DATA_DIR / "backup"

def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def _backup(path: Path) -> None:
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = path.stem  # "master" or "plan_2025-03"
        backup_path = BACKUP_DIR / f"{stem}_{ts}.json"
        backup_path.write_bytes(path.read_bytes())

def get_master() -> list[dict]:
    _ensure_dirs()
    p = DATA_DIR / "master.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))

def save_master(data: list[dict]) -> None:
    _ensure_dirs()
    p = DATA_DIR / "master.json"
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_plan(month: str) -> list[dict]:
    _ensure_dirs()
    p = DATA_DIR / f"plan_{month}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))

def save_plan(month: str, data: list[dict]) -> None:
    _ensure_dirs()
    p = DATA_DIR / f"plan_{month}.json"
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

---

## 3. backend/app/compute.py — diff 초안 요약

### 3-1. 내부 표준 컬럼명 상수 (파일 상단 또는 설정 근처)

- 작업일보용: Excel 컬럼(settings) → 내부명 매핑 한 곳에서 정의.  
  예: `WORK_RENAME = { settings.work_col_product: "product", settings.work_col_process_code: "process_code", ... }`  
  또는 `work_date`, `good_qty`, `defect_qty`, `defect_type` 등.
- 기준/플랜은 이미 저장소가 내부 표준 필드명(product, process_code, …)을 쓰므로, DataFrame 생성 시 해당 이름으로 컬럼 지정.

### 3-2. 작업일보: Excel → 내부 표준 rename

- `_load_work()` 반환 전에 `df = df.rename(columns=WORK_RENAME)` 적용.  
  필요한 컬럼만 남기고 rename (없는 컬럼은 _ensure_columns 등으로 처리한 뒤 rename).
- 이후 compute 전체에서는 `product`, `process_code`, `work_date`, `good_qty`, `defect_qty`, `defect_type` 등 **내부 표준명만** 사용.

### 3-3. 기준정보: JSON(저장소) → 내부 표준 DataFrame

- `compute_tables(master_df: pd.DataFrame, plan_df: pd.DataFrame, today_file_bytes, prev_file_bytes, base_date)` 형태로 받거나,  
  `master_list: list[dict]`, `plan_list: list[dict]`를 받아서 compute 내부에서 한 번만 DataFrame 생성.
- 기준: `pd.DataFrame(master_list)` 후 컬럼 검증(product, process_code, process_name, process_group, is_assembly, display_order, is_active).  
  `is_active` 가 False인 행 제거. 컬럼명은 그대로 내부 표준.
- **기존 _load_master 제거**하고, “저장소에서 읽은 list[dict] → DataFrame” 변환만 사용.

### 3-4. 월간플랜: JSON(저장소) → 내부 표준 DataFrame

- `pd.DataFrame(plan_list)` 후 컬럼: month, product, process_code, month_plan, prev_day_plan.  
  기존 _load_plan의 month_total, month_label 은 plan_list에서 첫 행 등에서 추출하거나, 별도 필드로 저장소에 넣을 수 있음(선택).
- **기존 _load_plan 제거**하고, “저장소에서 읽은 list[dict] → DataFrame + month_total/month_label 계산”만 사용.

### 3-5. compute_tables 시그니처 변경

```diff
 def compute_tables(
-    today_file_bytes: bytes,
+    master_list: list[dict[str, Any]],  # 저장소에서 로드한 기준정보
+    plan_list: list[dict[str, Any]],    # 저장소에서 로드한 해당 월 플랜
+    today_file_bytes: bytes,
     prev_file_bytes: bytes,
     base_date: date,
 ) -> dict[str, Any]:
```

- 상단에서:
  - `df_master` = 기준정보 list → 내부 표준 컬럼 DataFrame 생성, is_active 필터.
  - `df_plan`, `month_total`, `month_label` = 월간플랜 list → 내부 표준 컬럼 DataFrame 생성 및 요약값 계산.
  - today/prev 시트만 읽고, `_load_work` 후 **rename** 적용한 작업일보 DataFrame 사용.
- 인덱스/조인/정렬 등은 모두 **내부 표준 컬럼명**만 사용하며, **기준키는 항상 (product, process_code)**.

### 3-6. 정렬: display_order 만 사용

```diff
-    process_order = {p: i for i, p in enumerate(settings.process_list())}
     def _sort_key_idx(idx: Any) -> tuple[...]:
         ...
-        po = process_order.get(name, 9999)
         disp_order = _to_scalar_display(display_order.loc[idx] ...)
-        return (po, disp_order, group, name)
+        return (disp_order, group, name)
```

- `display_order` 는 이미 내부 표준 컬럼명으로 존재하는 DataFrame에서 참조.

---

## 4. backend/app/models.py — diff 초안

```diff
--- a/backend/app/models.py
+++ b/backend/app/models.py
@@ -48,6 +48,28 @@ class ComputeResponse(BaseModel):
     조립공정불량: list[AssemblyDefectRow]


+class MasterRow(BaseModel):
+    product: str = ""
+    process_code: str = ""
+    process_name: str = ""
+    process_group: str = ""
+    is_assembly: str = "N"
+    display_order: float = 0.0
+    is_active: bool = True
+
+
+class PlanRow(BaseModel):
+    month: str = ""   # "2025-03"
+    product: str = ""
+    process_code: str = ""
+    month_plan: float = 0.0
+    prev_day_plan: float = 0.0
+
+
 class HealthResponse(BaseModel):
     status: Literal["ok"]
     message: str
```

---

## 5. backend/app/main.py — diff 초안

- GET /master: store.get_master() 반환.
- POST /master: body를 list[MasterRow] 등으로 검증 후 store.save_master(...).
- GET /plan/{month}: store.get_plan(month) 반환.
- POST /plan/{month}: body를 list[PlanRow] 등으로 검증 후 store.save_plan(month, ...).
- POST /compute: Form(base_date), File(today_file), File(prev_file) 만 받음. base_date에서 월(YYYY-MM) 추출 후 master = store.get_master(), plan = store.get_plan(month). compute_tables(master, plan, today_bytes, prev_bytes, base_date) 호출 후 ComputeResponse 반환.

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -7,6 +7,7 @@ from fastapi.middleware.cors import CORSMiddleware
 from .compute import compute_tables
 from .models import ComputeResponse, HealthResponse
+from .store import get_master, get_plan
@@ -24,6 +25,28 @@ app.add_middleware(
 @app.get("/health", response_model=HealthResponse)
 def health() -> HealthResponse:
     return HealthResponse(status="ok", message="up", now=datetime.utcnow().isoformat())
+
+
+@app.get("/master")
+def api_get_master() -> list[dict]:
+    return get_master()
+
+
+@app.post("/master")
+def api_save_master(body: list[dict]) -> dict:
+    from .store import save_master
+    save_master(body)
+    return {"status": "ok", "message": "saved"}
+
+
+@app.get("/plan/{month}")
+def api_get_plan(month: str) -> list[dict]:
+    return get_plan(month)
+
+
+@app.post("/plan/{month}")
+def api_save_plan(month: str, body: list[dict]) -> dict:
+    from .store import save_plan
+    save_plan(month, body)
+    return {"status": "ok", "message": "saved"}
 
 
 @app.post("/compute", response_model=ComputeResponse)
 async def compute(
     base_date: date = Form(...),
-    today_file: UploadFile = File(...),
-    prev_file: UploadFile = File(...),
-) -> ComputeResponse:
-    today_bytes = await today_file.read()
-    prev_bytes = await prev_file.read()
-    out = compute_tables(today_bytes, prev_bytes, base_date=base_date)
+    today_file: UploadFile = File(...),
+    prev_file: UploadFile = File(...),
+) -> ComputeResponse:
+    today_bytes = await today_file.read()
+    prev_bytes = await prev_file.read()
+    master_list = get_master()
+    month = base_date.strftime("%Y-%m")
+    plan_list = get_plan(month)
+    out = compute_tables(master_list, plan_list, today_bytes, prev_bytes, base_date=base_date)
     return ComputeResponse(**out)
```

---

## 6. frontend/src/api.ts — diff 초안

- MasterRow에 is_active 추가. PlanRow에 month, prev_day_plan 사용 (prev_plan 아님).
- getMaster(), postMaster(), getPlan(month), postPlan(month), computeIlbo는 baseDate, todayFile, prevFile 만.

```diff
--- a/frontend/src/api.ts
+++ b/frontend/src/api.ts
@@ -38,6 +38,35 @@ export type ComputeResponse = {
   조립공정불량: AssemblyDefectRow[];
 };
 
+export type MasterRow = {
+  product: string;
+  process_code: string;
+  process_name: string;
+  process_group: string;
+  is_assembly: string;
+  display_order: number;
+  is_active: boolean;
+};
+
+export type PlanRow = {
+  month: string;
+  product: string;
+  process_code: string;
+  month_plan: number;
+  prev_day_plan: number;
+};
+
 export const API_BASE = "http://localhost:8000";
+
+export async function getMaster(): Promise<MasterRow[]> {
+  const res = await fetch(`${API_BASE}/master`);
+  if (!res.ok) throw new Error(`GET /master failed: ${res.status}`);
+  return res.json();
+}
+
+export async function postMaster(rows: MasterRow[]): Promise<void> {
+  const res = await fetch(`${API_BASE}/master`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rows) });
+  if (!res.ok) throw new Error(`POST /master failed: ${res.status}`);
+}
+
+export async function getPlan(month: string): Promise<PlanRow[]> {
+  const res = await fetch(`${API_BASE}/plan/${encodeURIComponent(month)}`);
+  if (!res.ok) throw new Error(`GET /plan failed: ${res.status}`);
+  return res.json();
+}
+
+export async function postPlan(month: string, rows: PlanRow[]): Promise<void> {
+  const res = await fetch(`${API_BASE}/plan/${encodeURIComponent(month)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rows) });
+  if (!res.ok) throw new Error(`POST /plan failed: ${res.status}`);
+}
 
 export async function computeIlbo(params: {
   baseDate: string;
-  master: MasterRow[];
-  plan: PlanRow[];
   todayFile: File;
   prevFile: File;
 }): Promise<ComputeResponse> {
   const fd = new FormData();
   fd.append("base_date", params.baseDate);
-  fd.append("master", JSON.stringify(params.master));
-  fd.append("plan", JSON.stringify(params.plan));
   fd.append("today_file", params.todayFile);
   fd.append("prev_file", params.prevFile);
   ...
```

---

## 7. frontend/src/App.tsx — 수정 요약 및 diff 초안 (product 단위 관리)

- **제품(product) 가정 금지**: UDP 등 특정 제품으로 고정하지 않는다. 기준정보·월간플랜 화면은 **product 단위**로 입력·조회되도록 설계한다.
- **기준정보 화면**  
  - GET /master 로 전체 기준정보 로드. 각 행에 **product** 컬럼이 반드시 포함되며, UDP / 132FBGA 등 여러 제품이 한 테이블에 공존할 수 있다.  
  - **product 필터/선택**: 드롭다운 또는 필터로 제품별 조회 가능 (선택 사항).  
  - 테이블에서 product, process_code, process_name, process_group, is_assembly, display_order, is_active 편집. 행 추가 시 **product 입력 필드** 포함.  
  - 저장 시 POST /master(masterRows) — product가 포함된 전체 목록 저장.
- **월간플랜 화면**  
  - 월 선택(예: 2025-03) 후 GET /plan/{month} 로 해당 월 플랜 로드. 각 행에 **month**, **product**, process_code, month_plan, prev_day_plan 표시.  
  - **product 단위 조회**: 제품 필터 또는 제품별 그룹 표시 가능.  
  - 행 추가/편집 시 **product** 입력 필드 포함.  
  - 저장 시 POST /plan/{month}(planRows) — product가 포함된 해당 월 전체 목록 저장.
- **생산일보 계산**: `computeIlbo({ baseDate, todayFile, prevFile })` 만 호출. master/plan 인자 제거.
- canSubmit: todayFile, prevFile, baseDate, !loading 만 필요 (master/plan 길이 조건 제거).

```diff
--- a/frontend/src/App.tsx
+++ b/frontend/src/App.tsx
@@ -4,6 +4,7 @@ import {
   API_BASE,
   AssemblyDefectRow,
   ComputeResponse,
+  getMaster,
+  getPlan,
+  postMaster,
+  postPlan,
   MasterRow,
   PlanRow,
   ProductionProgressRow,
   computeIlbo,
 } from "./api";
@@ -28,8 +29,10 @@ export default function App() {
   const [todayFile, setTodayFile] = useState<File | null>(null);
   const [prevFile, setPrevFile] = useState<File | null>(null);
+  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
+  const [planRows, setPlanRows] = useState<PlanRow[]>([]);
+  const [planMonth, setPlanMonth] = useState<string>(""); // "2025-03"
   ...
-  const canSubmit = Boolean(todayFile && prevFile && baseDate && !loading);
+  const canSubmit = Boolean(todayFile && prevFile && baseDate && !loading);
@@ -72,7 +75,7 @@ export default function App() {
     try {
-      const res = await computeIlbo({ baseDate, master: masterRows, plan: planRows, todayFile, prevFile });
+      const res = await computeIlbo({ baseDate, todayFile, prevFile });
       setData(res);
     } catch (err) {
```

- 기준정보 카드: "불러오기" → getMaster() 후 setMasterRows. 테이블 컬럼에 **product** 포함, 제품별 필터 옵션. "저장" → postMaster(masterRows). is_active 포함 편집.
- 월간플랜 카드: 월 선택(또는 baseDate 기반 month) → getPlan(month) 후 setPlanRows. 테이블 컬럼에 **month**, **product**, process_code, month_plan, prev_day_plan. "저장" → postPlan(planMonth, planRows). product 단위로 행 추가/편집 가능하도록 설계.

---

## 8. 적용 순서 제안

1. **backend/app/settings.py** — initial_processes / process_list 제거.
2. **backend/app/store.py** — 신규 추가 (읽기/쓰기/백업).
3. **backend/app/models.py** — MasterRow(is_active), PlanRow(month, prev_day_plan) 추가.
4. **backend/app/compute.py** — 내부 표준 컬럼 rename/생성 경계 정리, master/plan을 list 인자로 받아 DataFrame 생성, 정렬은 display_order 만 사용.
5. **backend/app/main.py** — GET/POST /master, GET/POST /plan/{month}, POST /compute에서 저장소 로드 후 compute_tables 호출.
6. **frontend/src/api.ts** — getMaster, postMaster, getPlan, postPlan 추가, computeIlbo에서 master/plan 제거, 타입에 is_active, prev_day_plan 반영.
7. **frontend/src/App.tsx** — 기준정보/월간플랜 로드·저장 UI, 계산 시 computeIlbo(baseDate, todayFile, prevFile) 만 호출.  
8. **조립 공정 불량 A방식 + Defect Input** (추가): store/models/main에 defect 저장·조회, compute에 defect_list 전달 후 누적불량유형 참고용만 반영, 프론트에 수기 입력 화면 추가. (기존 1~7 적용 후 진행.)

위는 모두 **수정된 설계와 diff 초안**이며, 실제 코드는 자동 수정하지 않음.

---

## 9. 조립 공정 불량 A방식 + Defect Input (추가 설계 및 diff 초안)

### 9-1. 계산 기준 정리 (A 방식 확정)

| 항목 | 계산 기준 |
|------|-----------|
| 조립실적 누적 | 작업일보 Excel (조립 공정 생산수량 누적) |
| 전일 조립 실적 | 전일작업일보 Excel |
| 전일불량개수 | Excel Reject (전일) |
| 전일불량율(PPM) | Excel Reject / 전일 조립 실적 |
| 누적불량개수 | Excel Reject 누적 |
| 누적불량율(PPM) | Excel Reject 누적 / 조립실적 누적 |
| 누적불량유형 | **수기 입력(defect input) 참고용** — 개수/PPM 계산에 사용하지 않음 |

### 9-2. Defect Input 저장 형식

- 단일 파일 예: `data/defects.json` — `list[DefectInputRow]`.
- 또는 날짜별: `data/defects_{YYYY-MM-DD}.json` (선택).  
  조회 시 기간(date_from, date_to) 또는 기준일 이전 전체를 읽어 (product, process_code)별로 `"defect_name : qty"` 줄 합쳐서 문자열로 만든 뒤, compute 결과의 `defect_cumulative_types`에만 참고용으로 붙인다.

### 9-3. backend/app/store.py — defect 추가 diff 초안

```diff
+# defect 수기 입력 (누적불량유형 참고용)
+DEFECTS_FILE = DATA_DIR / "defects.json"
+
+def get_defects() -> list[dict]:
+    _ensure_dirs()
+    if not DEFECTS_FILE.exists():
+        return []
+    return json.loads(DEFECTS_FILE.read_text(encoding="utf-8"))
+
+def save_defects(data: list[dict]) -> None:
+    _ensure_dirs()
+    _backup(DEFECTS_FILE)
+    DEFECTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

### 9-4. backend/app/models.py — DefectInputRow diff 초안

```diff
+class DefectInputRow(BaseModel):
+    date: str = ""       # YYYY-MM-DD
+    product: str = ""
+    process_code: str = ""
+    defect_name: str = ""
+    qty: float = 0.0
```

### 9-5. backend/app/main.py — GET/POST /defects 및 compute에 defect 전달 diff 초안

```diff
+from .store import get_master, get_plan, save_master, save_plan, get_defects, save_defects
...
+@app.get("/defects")
+def api_get_defects() -> list[dict]:
+    return get_defects()
+
+@app.post("/defects")
+def api_save_defects(body: list[dict]) -> dict:
+    save_defects(body)
+    return {"status": "ok", "message": "saved"}
...
-    master_list = get_master()
+    master_list = get_master()
     month = base_date.strftime("%Y-%m")
     plan_list = get_plan(month)
-    out = compute_tables(master_list, plan_list, today_bytes, prev_bytes, base_date=base_date)
+    defect_list = get_defects()
+    out = compute_tables(master_list, plan_list, today_bytes, prev_bytes, base_date=base_date, defect_list=defect_list)
```

### 9-6. backend/app/compute.py — defect_list 인자 및 누적불량유형 참고용 반영 diff 초안

- **시그니처**: `compute_tables(..., defect_list: list[dict] | None = None)`.
- **로직**:
  - 전일/누적 불량개수·PPM: **기존과 동일** — Excel Reject만 사용. 변경 없음.
  - 조립 공정 불량 행을 만들 때, `defect_list`가 있으면 (product, process_code) + date ≤ base_date 인 항목을 모아 `"defect_name : qty"` 형태 여러 줄 문자열로 만든 뒤, 해당 (product, process_code)의 **defect_cumulative_types** 필드에 **참고용**으로만 설정. (이미 Excel 기반으로 만든 def_types가 있으면, 참고용 문자열을 그 뒤에 이어 붙이거나, 설계에 따라 “수기 입력” 블록으로만 쓸 수 있음.)
- **diff 요약**:
  - `compute_tables` 인자에 `defect_list: list[dict] | None = None` 추가.
  - 조립 공정 불량 asm_rows 생성 루프 안에서, (product, process_code)에 해당하는 defect_list 항목을 필터해 문자열로 포맷한 뒤 `defect_cumulative_types`에 반영. (전일/누적 개수·PPM 계산 코드는 그대로 두고, 표시용 필드만 보강.)

```diff
 def compute_tables(
     master_list: list[dict[str, Any]],
     plan_list: list[dict[str, Any]],
     today_file_bytes: bytes,
     prev_file_bytes: bytes,
     base_date: date,
+    defect_list: list[dict[str, Any]] | None = None,
 ) -> dict[str, Any]:
...
+    # (product, process_code)별 수기 입력 누적불량유형 문자열 (참고용만, 개수/PPM 계산에는 미사용)
+    defect_manual_str: dict[tuple[str, str], list[str]] = {}
+    if defect_list:
+        for d in defect_list:
+            d_date = str(d.get("date") or "").strip()
+            if not d_date or d_date > str(base_date):
+                continue
+            key = (str(d.get("product", "")).strip(), str(d.get("process_code", "")).strip())
+            name = str(d.get("defect_name", "")).strip()
+            if not name:
+                continue
+            qty = int(_safe_float(d.get("qty", 0)))
+            if key not in defect_manual_str:
+                defect_manual_str[key] = []
+            defect_manual_str[key].append(f"{name} : {qty}")
+    # 각 key별 리스트를 "\n".join() 해서 한 문자열로 보관
+    defect_manual_joined = {k: "\n".join(v) for k, v in defect_manual_str.items()}
+    # asm_rows 생성 시 defect_cumulative_types = Excel 기반 def_types + (참고용 수기 입력 문자열)
+    # types = str(def_types.loc[idx]) if idx in def_types.index else ""
+    # manual = defect_manual_joined.get((prod, code), "").strip()
+    # defect_cumulative_types: manual ? (types + "\n[수기]\n" + manual if types else "[수기]\n" + manual) : types
```

### 9-7. frontend api.ts — defect API diff 초안

```diff
+export type DefectInputRow = {
+  date: string;
+  product: string;
+  process_code: string;
+  defect_name: string;
+  qty: number;
+};
+
+export async function getDefects(): Promise<DefectInputRow[]> {
+  const res = await fetch(`${API_BASE}/defects`);
+  if (!res.ok) throw new Error(`GET /defects failed: ${res.status}`);
+  return res.json();
+}
+
+export async function postDefects(rows: DefectInputRow[]): Promise<void> {
+  const res = await fetch(`${API_BASE}/defects`, {
+    method: "POST",
+    headers: { "Content-Type": "application/json" },
+    body: JSON.stringify(rows),
+  });
+  if (!res.ok) throw new Error(`POST /defects failed: ${res.status}`);
+}
```

### 9-8. frontend App.tsx — 누적불량유형(수기 입력) 화면 diff 초안

- **섹션**: “누적불량유형 (수기 입력)” 카드 추가.
- **동작**: 불러오기 → getDefects() → 테이블 표시 (date, product, process_code, defect_name, qty). 행 추가/삭제/편집, 저장 → postDefects(rows).
- **안내 문구**: “참고용이며, 전일/누적 불량개수·PPM 계산에는 사용되지 않습니다.”
