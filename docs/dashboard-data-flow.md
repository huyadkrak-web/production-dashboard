# 대시보드 데이터 흐름 추적 보고서

생산일보 / 공정불량 자동화에서 **엑셀 파일별로 어떤 시트·셀·컬럼**을 시스템이 읽는지 정리한 문서.
실제 코드(`backend/app/**`, `frontend/src/**`)에 있는 함수·상수만 근거로 작성.

> 행·열 인덱스 표기 — Python(pandas): **0-based** / Excel: **1-based**
> 예) `raw.iloc[3, 3]` = Excel **D4** (행4, 열D)

---

## 0. 한눈에 보는 업로드 → 사용처 매핑

| 업로드 파일 | 사용 화면/계산 | 백엔드 진입 | 핵심 함수 |
|------------|----------------|-------------|-----------|
| 작업일보 엑셀 | 생산일보 계산(생산진척현황·조립공정불량) / 공정불량 자동(LOT 매칭 보조) | `POST /compute` , `POST /defect-auto/compute` | `compute.read_excel_any_sheets` → `_load_work` , `parser.parse_work` |
| 코드별 불량현황 엑셀 | 공정불량 자동(주차/월/LOT PPM) | `POST /defect-auto/compute` | `parser.parse_defect` |
| 출하파일 (공장 받기.xlsx) | 공정불량 자동(주차/월/LOT의 AO/PPM 분모) | `POST /defect-auto/shipment` | `parser.parse_shipment` → `shipment_store.save_shipment` |
| 월간플랜 엑셀 | 생산일보 월계획/기준일계획 + 월 목표 배너 | (프론트 파싱) → `POST /compute`의 `plan_rows_json` | `App.tsx.buildPlanRowsFromMonthlyWorksheet` , `scanMonthlyPlanSheetRow11ForMonthGoals` |
| 기준정보(master) | 생산일보 공정 매핑·조립공정 플래그·표시순서 | `GET/POST /master` (Supabase) | `store.get_master` , `store.save_master` |

---

## 1. 작업일보 엑셀

### 1-A. `POST /compute` (생산일보 계산)

==================================================
[작업일보 엑셀 — 생산일보 계산용]
==================================================

**사용 시트**
- `작업일보` (`settings.sheet_work_today = "작업일보"`)
- 시트가 없으면 `compute_tables`에서 `ValueError("시트 '작업일보'를 찾을 수 없습니다.")`

**헤더 행 자동 탐지**
- `compute._detect_work_sheet_header_row(xls, sheet)` :
  상단 **80행**(`_WORK_HEADER_SCAN_ROWS`)을 `header=None`으로 읽고,
  한 행에 **앵커 컬럼이 모두** 있으면 그 행을 헤더로 잡음.
- 앵커 컬럼 (`_work_sheet_anchor_columns`):
  - `공정ID`
  - `공정`
  - `작업종료일자`
  - `생산수량`
  - `Reject`
- 못 찾으면 1행을 헤더로 사용 + 경고 추가.

**읽는 컬럼명 (settings.py 기본값)**
| 엑셀 헤더 | 내부 표준명 | 용도 |
|-----------|-------------|------|
| `작업종료일자` (`work_col_date`) | `work_date` | 월 필터(기준월 1일~기준일), 전일(=기준일) 분리 |
| `제품군` (`work_col_product`) | `product` | 집계 키 — 비어 있으면 `품목명` → `품목ID` 순으로 보강 (`_resolve_work_product_source_column`) |
| `공정ID` (`work_col_process_code`) | `process_code` | 집계 키 |
| `공정` (`work_col_process_name`) | `process_name` | 라벨 |
| `생산수량` (`work_col_good_qty`) | `good_qty` | 생산진척 누적·전일 실적 / 조립 누적·전일 |
| `Reject` (`work_col_defect_qty`) | `defect_qty` | 조립 누적 불량 / 전일 불량 |
| `Reject 유형` (`work_col_defect_type`) | `defect_type` | 누적 불량유형 문자열 |

**불량 발생일 컬럼 (선택, `_find_defect_occurrence_column`)**
- 헤더 정규화(공백·줄바꿈 제거, 대문자) 후 다음 키 우선순위로 탐색:
  - `불량일자` → `불량발생일` → `발생일자` → `발생일` → `REJECT일자` → `REJECT발생일` → `Reject일자`
- 발견 시 누적 불량유형 행의 월 필터(기준월 1일~base_date)에 사용. 없으면 `work_date`로 fallback.

**사용 목적**
- `생산진척현황` 행 (`good_cum`, `good_prev`, `month_plan` 조인)
- `조립공정불량` 행 (`asm_good_cum/prev`, `asm_def_cum/prev`, `defect_cumulative_ppm`)
- `defect_cumulative_types` 텍스트(`Reject 유형:수량` 묶음)

**관련 함수**
- `backend/app/compute.py`
  - `read_excel_any_sheets`
  - `_detect_work_sheet_header_row`
  - `_read_work_sheet_dataframe`
  - `_resolve_work_product_source_column`
  - `_load_work`
  - `_find_defect_occurrence_column`
  - `compute_tables`
- `backend/app/excluded_sample_lots.filter_compute_work_dataframe` (필터)

**관련 파일**
- `backend/app/compute.py`
- `backend/app/settings.py`
- `backend/app/excluded_sample_lots.py`
- `frontend/src/App.tsx` (업로드 `data-testid="work-report-file"` → state `todayFile` → `/compute` form `today_file`)

---

### 1-B. `POST /defect-auto/compute` (공정불량 자동)

==================================================
[작업일보 엑셀 — 공정불량 자동 LOT 매칭용]
==================================================

**사용 시트**
- 별도 시트 지정 없음. `pd.read_excel(io.BytesIO(...), header=None, engine="openpyxl")`로 **첫 시트**만 읽음.

**헤더 행 자동 탐지 (`parser.parse_work`)**
- 한 행에 LOT/공정/투입수량 헤더가 동시에 있는 첫 행을 헤더로 결정.
- 후보 헤더(정규화 키):
  - LOT 열: `LOTID`, `LOT`, `LOTNO`, `LOT번호` 중 하나
  - 공정 코드 열 우선순위(낮을수록 우선):
    - rank 0: `공정ID` / `PROCESSID`
    - rank 1: `공정코드` / `PROCESSCODE` / `OP코드` / `OPCODE`
    - rank 2: `공정` / `PROCESS`
  - 투입수량 열: `투입수량`, `투입`, `INPUTQTY`, `INPUT`
  - 메타(D/A 1차 투입 보조): `공정명`, `공정이름`, `작업공정`, `작업공정명`, `단계`, `단계명`, `STEP`, `STAGE`, `공정단계`

**출력 컬럼**
- `lot_id` (정규화), `process_id`, `input_qty`, `process_meta`

**사용 목적**
- LOT별 PPM 분모(AO) 계산 시 D/A 1차 투입 합 산출 (`calculator._work_da_input_qty_sum`)
- 주차/월 AO fallback (`_apply_shipment_plus_defect_ao_fallback`)

**관련 함수**
- `backend/app/defect/parser.py` : `parse_work`
- `backend/app/defect/calculator.py` : `_work_da_input_qty_sum`, `_ao_sum_raw_work_da_only`, `compute_weekly_defect_from_shipments`, `compute_monthly_defect_from_shipments`

**관련 파일**
- `backend/app/defect/parser.py`
- `backend/app/defect/calculator.py`
- `backend/app/defect/router.py`

---

## 2. 코드별 불량현황 엑셀

==================================================
[코드별 불량현황 엑셀]
==================================================

**사용 시트**
- 시트명 무관. `pd.read_excel(io.BytesIO(...), header=None, engine="openpyxl")`로 **첫 시트**.

**헤더 행 자동 탐지 (`parser._find_defect_header_row`)**
- 한 행에 `불량수량` + `불량명` 이 동시에 있고, 추가로 다음 중 하나가 같은 행에 있으면 헤더 행으로 선택:
  - `부모LOTID` 또는 `LOTID`
  - 그 외 셀 중 정규화 키에 `LOT` 포함

**필수 컬럼 (정규화 매칭)**
| 정규화 키 | 내부명 | 비고 |
|-----------|--------|------|
| `불량수량` | `defect_qty` | `pd.to_numeric ... fillna(0)` |
| `불량명` | `defect_name` | 정규화 → `_DEFECT_NAME_CANONICAL` 매핑(예: `chip crack` → `Chip Crack`) |

**LOT 컬럼 선택 (`parser.parse_defect`)**
- 헤더에 `LOT` 포함된 열들을 후보로 모음 (`_lot_candidate_columns`).
- 출하 `lot_id` 집합이 제공되면, 각 후보 열과 **교집합 수**가 가장 큰 열을 선택(동률 시 이름 오름차순).
- 교집합 0이거나 출하 LOT 미제공 시 `부모LOTID` 열을 우선, 없으면 후보 첫 열.
- 선택 결과는 `df.attrs["defect_lot_parse_report"]`에 저장(로그 `[parse_defect][lot_column_selected]`).

**부가 컬럼 (선택, 없으면 NaT/"")**
- 발생일자: `발생일자` → `발생일` → `불량발생일` 순으로 첫 매칭 → `occurrence_date`
- 공정: `공정ID` → `공정` → `process_id`

**사용 목적**
- 주차/월/LOT 공정불량 자동 집계(분자) — `defect_qty` 합산 → PPM
- 누적불량유형(프론트 수동 보조 파서) — `frontend/src/cumulativeDefectTypesFromExcels.ts` 참조

**관련 함수**
- `backend/app/defect/parser.py` : `parse_defect`, `_find_defect_header_row`, `_lot_candidate_columns`, `_column_by_norm`, `print_defect_shipment_lot_match_report`
- `backend/app/defect/calculator.py` : `_normalize_defect_name`, `_prepare_defect_df`, `compute_*_from_shipments`

**관련 파일**
- `backend/app/defect/parser.py`
- `backend/app/defect/calculator.py`
- `frontend/src/cumulativeDefectTypesFromExcels.ts` (별도 프론트 파서)
- 프론트 업로드: `data-testid="defect-report-file"` → `codeDefectFile` → `/defect-auto/compute` form `defect_file`

---

## 3. 출하파일 (공장 받기.xlsx)

==================================================
[출하 엑셀]
==================================================

**사용 시트 (`parser._select_shipment_sheet_name`)**
- 우선순위 1: **`공장 받기@2`** (`_SHIPMENT_SHEET_PREFERRED`)
- 우선순위 2: 시트가 2개 이상이면 두 번째 시트
- 우선순위 3: 첫 시트

**상단 조회기간 셀 (`_parse_shipment_query_dates_d4_e4`)**
- `raw.iloc[3, 3]` = **D4** = `query_start_date`
- `raw.iloc[3, 4]` = **E4** = `query_end_date`
- 규칙:
  - D4·E4 둘 다 날짜 → 행 공통 `move_date` = **E4** (`move_date_source="E4_query_end_date"`)
  - E4만 비거나 무효 → **D4**로 fallback (`move_date_source="D4_fallback"`)
  - 둘 다 무효 → `pd.NaT` → 데이터 행은 `move_date_missing`으로 제외
- `공장 받기@2` 시트일 때 행별 이동일자 열은 **사용하지 않음** (`parse_shipment`에서 `date_col = None`으로 덮어씀)
- 로그: `[shipment_date_range_parse]` (sheet, query_start_date, query_end_date, selected_move_date, move_date_source)

**헤더 자동 탐지 (`_find_shipment_header_and_columns`)**
- 상단 **55행** (`_SHIPMENT_HEADER_SCAN_ROWS`) 스캔.
- 한 행에서 다음 열을 찾으면 그 행을 헤더로 채택:
  - LOT 열 (`_matches_lot_header_cell`): 정규화 키가 `LOTID`/`LOT` 등을 포함하고 길이 ≤ 24
  - 수량 열 우선: `총수량` 최우선 → `…총…수량…(이동 제외)` → `이동수량`
  - 제품 열 (`_matches_product_header`): `제품ID`/`품목ID`/`품목명`/`PRODUCTID` 등
  - (참고) 이동일자 열 (`_matches_move_date_header`): `이동일자` — `공장 받기@2`에서는 무시
- 헤더 못 찾으면 레거시 **고정 인덱스** fallback:
  - `data_start = 6`(=Excel 7행)
  - LOT 열 = 인덱스 2 (Excel **C**)
  - 제품 열 = 인덱스 4 (Excel **E**)
  - 총수량 열 = 인덱스 8 (Excel **I**)
  - `layout_mode = "legacy_fixed_CEI"`

**행 단위 추출 (`parse_shipment`)**
- LOT: `_lot_from_row_series` (LOT 열에서 시작, 빈 셀이면 오른쪽 최대 5칸 보조)
  - `LOTID`/`부모LOTID` 등 헤더 토큰·합계 행은 제외 (`_is_reserved_lot_value`, `_is_summary_label`)
- 제품: `prod_col` 셀 문자열
- 이동수량(`move_qty`): `qty_col` 셀 → `pd.to_numeric` → `int(round(...))`
- `move_date`: 위 D4/E4 규칙으로 결정된 `global_move_date` 사용
- 출력 DataFrame: `lot_id, product, move_qty, move_date`
- 부가: `df.attrs["shipment_parse_report"]`에 선택 시트·열 인덱스·query_start/end·excluded_rows 저장.

**저장 (`shipment_store.save_shipment`) — Supabase `shipment` 테이블**
- 저장 컬럼: `move_date`(YYYY-MM-DD 문자열), `week`(`get_week_label` 결과 `WWnn`), `lot_id`, `product`, `move_qty`
- 행 단위 중복 스킵 키: `(move_date, lot_id, product, move_qty)` (`_shipment_identity_tuple`)
  - 새 행 전부가 DB에 이미 있으면 insert 없이 `duplicate_skipped=True`
  - 일부 신규만 있으면 신규 행만 insert (기존 행 delete 없음)
- 응답: `duplicate_skipped`, `inserted_rows`, `skipped_rows`, `inserted_qty`, `skipped_qty`, `shipment_summary`

**일자별 rollup (`get_shipment_move_date_rollups`)**
- 저장된 `move_date`(YYYY-MM-DD) 기준으로 행 수·`move_qty` 합산 → 드롭다운 옵션
- 화면: `DefectAutoUploadPanel.tsx` `data-testid="shipment-move-date-select"`

**보정 (`fix_shipment_move_dates_bulk` , `POST /defect-auto/shipment-fix-move-date`)**
- `move_date == from_date` 행만 `to_date`로 PATCH(주차 라벨도 동시 갱신). 기대 행 수/수량 검증 가능.

**사용 목적**
- `move_date` → 주차(`get_week_label`)·월(`get_month_label`) 라벨
- 주차별/월별 AO(분모) 합산 — `_ao_qty_shipment_rows` 등
- LOT별 PPM의 LOT 키 확정 — `compute_lot_defect_ppm_from_shipments`
- 출하 누적 카드 표시 — `get_shipment_summary`
- `shipment-move-dates` 드롭다운

**관련 함수**
- `backend/app/defect/parser.py` : `parse_shipment`, `_select_shipment_sheet_name`, `_parse_shipment_query_dates_d4_e4`, `_find_shipment_header_and_columns`, `_lot_from_row_series`
- `backend/app/defect/shipment_store.py` : `save_shipment`, `load_shipment`, `get_shipment_summary`, `get_shipment_move_date_rollups`, `fix_shipment_move_dates_bulk`, `_df_to_shipment_records`, `_shipment_identity_tuple`
- `backend/app/defect/calculator.py` : `_ao_qty_shipment_rows`, `compute_weekly_defect_from_shipments`, `compute_monthly_defect_from_shipments`, `compute_lot_defect_ppm_from_shipments`
- `backend/app/db.py` : `supabase_insert`, `supabase_get`, `supabase_patch_by_filters`

**관련 파일**
- `backend/app/defect/parser.py`
- `backend/app/defect/shipment_store.py`
- `backend/app/defect/router.py`
- `backend/app/db.py`
- `frontend/src/components/DefectAutoUploadPanel.tsx`
- `frontend/src/api.ts` (`uploadDefectShipment`, `getDefectAutoShipmentSummary`, `getDefectAutoShipmentMoveDates`)

---

## 4. 월간플랜 엑셀

==================================================
[월간플랜 엑셀 — 프론트에서만 파싱]
==================================================

**파싱 위치**
- 모두 **프론트** `frontend/src/App.tsx` (SheetJS `XLSX.read`)
- 백엔드는 파싱 결과를 `POST /compute`의 `plan_rows_json`으로만 수신.

**시트 (`onUploadPlanDefectExcel`)**
- **첫 시트**(`wb.SheetNames[0]`)만 사용. 두 번째 시트가 있어도 무시.

### 4-A. 월계획/기준일계획 (`buildPlanRowsFromMonthlyWorksheet`)

**고정 위치**
- A열 (`processCodeColIdx = 0`) = 공정코드
- C열~ (`dateStartColIdx = 2`) = 날짜 헤더 + 일별 수량
- 데이터 시작 행: `max(dateHeaderRowIdx + 1, 2)` (= Excel 3행 이상)

**날짜 헤더 행 자동 탐지 (`pickMonthlyPlanDateHeaderRow`)**
- 상위 5행(`maxTryR = min(4, range.e.r)`) 중에서 C열~에 날짜 셀이 가장 많은 행을 헤더로 채택.
- 점수: `(기준일 열 매칭 시 1,000,000 가산) + 날짜 셀 개수`, 동점이면 Excel 2행(`tryR = 1`)에 가까운 행.

**수량 셀 (`readPlanWorksheetQuantityCell`)**
- SheetJS의 `cell.v`(원시값)과 `cell.w`(표시값)를 둘 다 봄. v가 4.8·w가 4,800 같이 ×1000/×100/×10000/×1000000으로 일치하면 w(표시값)를 채택.
- 모든 수량 합계는 **×1000** (`monthlyPlanSheetUnitScale = 1000`) 으로 state에 반영.

**집계**
- `month_plan` = (기준월 1일~말일) 같은 행의 모든 날짜 열 수량 합
- `prev_day_plan` = (기준월 1일~base_date) 누적 합
- 공정코드 검증: `isLikelyProcessCode` (3자 이상, 영문+숫자 포함, 합계 행 키워드 제외)

### 4-B. 월 목표 배너 (`scanMonthlyPlanSheetRow11ForMonthGoals`)

- 고정 위치: **엑셀 11행(0-based `r = 10`)** = `MONTHLY_PLAN_GOAL_SHEET_ROW_IDX`
- 11행의 모든 셀 스캔 → 셀 텍스트에서 `N월` (1~12) 패턴 추출 → 월 번호별로 정규화 문자열 저장(첫 출현 우선).
- 표시: `formatSelectedMonthPlanGoalBanner(planMonthKey, goals)` →
  - "N월 목표 〈본문〉" 형태(접미 "완료", "시작"은 표시용으로 제거)

### 4-C. 백엔드 입력 (`_plan_from_api`)

- 프론트가 `POST /compute`로 보내는 `plan_rows_json` 행:
  - `month`, `product`, `process_code`, `month_plan`, `prev_day_plan`
- 백엔드는 `product+process_code` 키로 max 집계 → `compute_tables`에서 `생산진척현황.month_plan`/`prev_day_plan`로 조인.
- `month_total = sum(month_plan)`은 상단 요약 `summary_title`("1. 생산진척현황 : N월 생산계획(GOC) : X,XXXea")에 사용.

**사용 목적**
- 생산진척현황 표의 `월 계획`, `기준일 계획`
- 상단 요약 `summary_title`의 `생산계획(GOC)`
- 카드 우측 월 목표 배너 (예: "5월 목표 95,000 시작")

**관련 함수**
- `frontend/src/App.tsx`
  - `onUploadPlanDefectExcel`
  - `buildPlanRowsFromMonthlyWorksheet`
  - `pickMonthlyPlanDateHeaderRow`, `buildDateColumnsForHeaderRow`
  - `readPlanWorksheetQuantityCell`, `excelCellToNumber`
  - `scanMonthlyPlanSheetRow11ForMonthGoals`, `formatSelectedMonthPlanGoalBanner`
  - `isLikelyProcessCode`
- `backend/app/compute.py` : `_plan_from_api`, `compute_tables`

**관련 파일**
- `frontend/src/App.tsx`
- `backend/app/compute.py`
- `backend/app/store.py` (`get_plan`/`save_plan` — 월별 저장)
- 프론트 업로드: `data-testid="monthly-plan-file"` , 월 선택: `data-testid="monthly-plan-month-input"`

---

## 5. 기준정보(master)

==================================================
[기준정보 — 엑셀 아님, Supabase `master` 테이블]
==================================================

**소스**
- 엑셀 업로드 아님. 화면 표(기준정보 카드)에서 직접 편집 + Supabase 저장.
- API:
  - `GET /master` → `store.get_master()` → `supabase_get("master")`
  - `POST /master` → `store.save_master()` → `supabase_delete_all("master")` 후 `supabase_insert`
- 저장 가드: 빈 payload·`product` 또는 `process_code` 누락 행 포함 시 거부 (`_validate_master_save_body` , 로그 `[기준정보저장차단]`)

**컬럼(저장 키)**
| 키 | 변환 | 용도 |
|----|------|------|
| `product` | trim | 집계 키 |
| `process_code` | trim | 집계 키 |
| `process_name` | trim | 표 라벨 |
| `process_group` | trim | 정렬(Front→Back End→기타), 행 그룹 |
| `is_assembly` | `_as_is_assembly` (`Y`/`N`) | 조립공정 필터(`Y/YES/1`) |
| `display_order` | `_as_display_order` (int) | 정렬 1순위 |
| `is_active` | `_as_is_active` (bool) | `True`만 사용 |

**사용 목적**
- `compute._master_from_api` → `(product, process_code)` 키 인덱스 생성, 정렬, 조립공정 필터
- 월간플랜 파싱 시 그룹 정렬(`processGroupSortRank`)
- 생산진척현황/조립공정불량 행 구성의 **기준 뼈대**

**관련 함수**
- `backend/app/main.py` : `api_get_master`, `api_save_master`, `_validate_master_save_body`
- `backend/app/store.py` : `get_master`, `save_master`, `_normalize_master_row_for_save`
- `backend/app/compute.py` : `_master_from_api`
- `frontend/src/App.tsx` : `loadMaster`, `saveMaster`, `buildMasterSavePayload`, `addMasterRow`, `removeMasterRow`

**관련 파일**
- `backend/app/store.py`
- `backend/app/main.py`
- `backend/app/compute.py`
- `frontend/src/App.tsx` (`data-testid`: `load-master-button`, `save-master-button`, `add-master-row-button`)

---

## 6. 프론트 차트가 사용하는 API 응답

| 화면 | API | 응답 필드 | 사용 컴포넌트 |
|------|-----|-----------|---------------|
| 생산진척현황 표·요약 | `POST /compute` | `meta.summary_title`, `meta.month_label`, `meta.month_plan_total`, `생산진척현황[]` | `App.tsx` 결과 카드 |
| 조립 공정 불량 표 | `POST /compute` | `조립공정불량[]` (`assembly_cumulative`, `defect_cumulative_count`, `defect_cumulative_ppm`, `defect_cumulative_types`) | `App.tsx` |
| 주차별 불량 PPM | `POST /defect-auto/compute` → `weekly[]` (+ `GET /defect-auto/weekly`) | `week`, `ao_qty`, `defect_total`, `total_ppm`, `defects[]` | `WeeklyDefectPPM.tsx` (`defectAutoMergeWeekly`) |
| 월별 조립 불량율 | `POST /defect-auto/compute` → `monthly[]` (+ `GET /defect-auto/monthly`) | `month`, `ao_qty`, `defect_total`, `total_ppm`, `defects[]` | `MonthlyDefectPPM.tsx` (`defectAutoMergeMonthly`) |
| LOT별 조립 불량률 | `GET /defect-auto/lot-defects` (자동계산 후 토큰으로 reload) | `lot_id`, `move_date`, `move_qty`, `defect_total`, `total_ppm`, `defects[]` | `LotDefectPpm.tsx` |
| 출하 누적 / 이동일자 dropdown | `GET /defect-auto/shipment-summary` , `GET /defect-auto/shipment-move-dates` | `shipment_summary{min_date,max_date,lot_count,total_qty}`, `move_dates[{date,row_count,total_qty}]` | `DefectAutoUploadPanel.tsx` |

### LOT별 그래프 표시 규칙 (`LotDefectPpm.tsx`)
- API 원본 rows는 그대로 state에 보관.
- 차트는 `lotRowsForChartDisplay(rows)` :
  1. `lot_id` == `LOTID` 행 제외
  2. `move_date` (YYYY-MM-DD `Date.parse`) **오름차순**, 동일 날짜는 API 응답 순서 유지
  3. 뒤에서 **`LOT_CHART_VISIBLE_LIMIT = 50`** 개만 사용
- 로그: `[lot_chart_visible_limit] {total_rows, visible_rows, limit, dropped_rows}`
- 헤더 옆 안내 문구: **"최근 50 LOT 기준"** (`LOT_CHART_VISIBLE_HINT_LABEL`)

---

## 7. 키 키워드·정규화 규칙 요약

| 항목 | 규칙 | 위치 |
|------|------|------|
| 헤더 키 정규화 | `str(x).strip().replace(" ","").replace("\n","").replace("\u3000","").upper()` | `parser._norm` , `compute._norm_hdr_key` |
| LOT 정규화 | 과학표기·`.0` 접미 제거, 정수 LOT 통일 | `parser._clean_lot` |
| 불량명 정규화 | trim + lower + canonical 매핑(`chip crack→Chip Crack`, `pkg broken→PKG Broken`, `단자 scratch→단자 Scratch`, `부풀음`) | `calculator._normalize_defect_name`, `_DEFECT_NAME_CANONICAL` |
| 주차 라벨 | ISO 주차 → `WWnn` | `calculator.get_week_label` |
| 월 라벨 | `YY.M` (예: 2026-04-25 → `26.4`) | `calculator.get_month_label` |
| 시트 우선순위 (출하) | `공장 받기@2` → 두 번째 시트 → 첫 시트 | `parser._select_shipment_sheet_name` |
| 시트 우선순위 (작업일보) | `작업일보` 고정 (생산일보), 첫 시트 (공정불량 자동의 `parse_work`) | `compute_tables` / `parser.parse_work` |
| 월간플랜 시트 우선순위 | 무조건 첫 시트 | `App.tsx.onUploadPlanDefectExcel` |

---

## 8. 운영 체크리스트(파일 구조 변경 대응)

| 변경 가능성 | 영향 위치 | 점검 함수/상수 |
|-------------|-----------|----------------|
| 출하 시트명 `공장 받기@2` 변경 | 시트 선택 우선순위 | `parser._SHIPMENT_SHEET_PREFERRED` |
| 출하 D4/E4 위치 변경 | `query_start/end_date`, `move_date` | `parser._parse_shipment_query_dates_d4_e4` |
| 출하 헤더(`총수량`/`이동수량`/LOT) 명 변경 | 자동 탐지 매칭 | `_matches_total_qty_header`, `_matches_lot_header_cell` |
| 작업일보 헤더 컬럼명 변경 | 헤더 탐지 + 내부 매핑 | `settings.work_col_*`, `_work_sheet_anchor_columns` |
| 작업일보 `Reject 유형` 컬럼 명 변경 | 누적불량유형 텍스트 비어짐 | `settings.work_col_defect_type` (없으면 경고만, 빈 문자열) |
| 코드별 불량현황 `발생일자` 명 변경 | 주차/월 필터링 | `parser.parse_defect`의 후보 키 `발생일자/발생일/불량발생일` |
| 월간플랜 11행 위치 변경 | 월 목표 배너 | `MONTHLY_PLAN_GOAL_SHEET_ROW_IDX` |
| 월간플랜 A열·C열~ 구조 변경 | 월계획/기준일계획 | `processCodeColIdx`, `dateStartColIdx` (`App.tsx`) |
| 월간플랜 수량 단위 변경 | 최종 값 스케일 | `monthlyPlanSheetUnitScale = 1000` (`App.tsx`) |

---

## 9. RPA용 안정 셀렉터 (`data-testid`)

| 화면 요소 | data-testid |
|-----------|-------------|
| 기준일 input | `report-date-input` |
| 기준정보 불러오기/저장/행 추가 | `load-master-button` / `save-master-button` / `add-master-row-button` |
| 월 input / 월간플랜 파일 | `monthly-plan-month-input` / `monthly-plan-file` |
| 작업일보 파일 | `work-report-file` |
| 코드별 불량현황 파일 | `defect-report-file` |
| 생산일보 계산 버튼 | `run-production-report-button` |
| 출하파일 / 이동일자 select | `shipment-file` / `shipment-move-date-select` |
| 출하 업로드 / 공정불량 자동 계산 / 초기화 | `upload-shipment-button` / `run-defect-auto-button` / `reset-defect-auto-button` |
| 현재 제품 select | `current-product-select` |
| 엑셀/PDF 다운로드 | `download-excel-button` / `download-pdf-button` |

---

*본 문서는 코드 변경 없이, 위에 명시된 파일·함수·상수 기준으로만 작성되었습니다. 추후 파서/시트 규칙이 바뀌면 동일 함수명으로 재추적하면 됩니다.*
