# 3Camp_260311.xlsx vs settings.py 컬럼 비교

## 실제 컬럼 목록을 얻는 방법

다음 중 하나를 실행하세요.

1. **프로젝트 루트에 파일 복사 후**
   - `backend/excel_path.txt` 첫 줄을  
     `c:\Users\USER\Desktop\생산일보프로그램\3Camp_260311.xlsx` 로 설정
   - 터미널에서 `chcp 65001` 후  
     `cd backend` → `python analyze_excel.py` 실행
   - 결과가 `backend/analyze_result.txt`에 저장됨

2. **파일 경로를 인자로 전달**
   - `python backend/analyze_excel.py "C:\Users\USER\Desktop\생산\3Camp_260311.xlsx"`

3. **아래 "실제 컬럼 (직접 입력)" 섹션에**  
   Excel에서 각 시트의 첫 행(헤더)을 복사해 붙여넣기

---

## 1. 기준 시트

### settings.py가 기대하는 컬럼

| 설정 키 | 기본값(컬럼명) |
|--------|----------------|
| master_col_product | 제품 |
| master_col_process_code | 공정코드 |
| master_col_process_name | 공정명 |
| master_col_process_group | 공정대분류 |
| master_col_is_assembly | 조립공정 |
| master_col_order | 표시순서 |

### 실제 컬럼 (직접 입력)

```
(analyze_result.txt의 "--- Sheet: '기준' ---" 아래 목록을 여기 붙여넣기)
```

### 차이 및 수정안

- 실제 컬럼명이 위와 다르면 `backend/app/settings.py`에서 해당 설정만 바꾸면 됨.
- 예: 제품이 "Product"이면  
  `master_col_product: str = "Product"`

---

## 2. 물량 투입 Plan 시트

### settings.py가 기대하는 컬럼

| 설정 키 | 기본값(컬럼명) |
|--------|----------------|
| plan_col_product | 제품 |
| plan_col_process_code | 공정코드 |
| plan_col_month_plan | 3월 계획 |
| plan_col_prev_plan | 전일 기준 계획 |
| plan_col_month_name | 월명 |
| plan_col_month_target | 월계획합계 |

### 실제 컬럼 (직접 입력)

```
(붙여넣기)
```

### 차이 및 수정안

- 월별 계획 컬럼이 "3월 계획"이 아니라 "4월 계획" 등이면  
  `plan_col_month_plan` 값을 해당 월 컬럼명으로 변경.
- 월명/월계획합계 컬럼이 없으면 그대로 두어도 됨(코드에서 없으면 대체 처리).

---

## 3. 작업일보 시트

### settings.py가 기대하는 컬럼

| 설정 키 | 기본값(컬럼명) |
|--------|----------------|
| work_col_date | 작업종료일자 |
| work_col_product | 품목명 |
| work_col_process_code | 공정ID |
| work_col_process_name | 공정 |
| work_col_good_qty | 생산수량 |
| work_col_defect_qty | Reject |
| work_col_defect_type | Reject 유형 |

### 실제 컬럼 (직접 입력)

```
(붙여넣기)
```

### 차이 및 수정안

- 날짜 컬럼이 "작업일자", "일자" 등이면  
  `work_col_date: str = "작업일자"` 등으로 변경.
- 품목이 "품목", "제품"이면  
  `work_col_product` 변경.
- 공정이 "공정코드", "공정명"만 있고 "공정ID"/"공정"이 없으면  
  실제 있는 컬럼명에 맞춰 `work_col_process_code`, `work_col_process_name` 수정.

---

## 4. 전일작업일보 시트

- **작업일보와 동일한 컬럼 구조**를 가정함.  
  작업일보와 동일한 설정(work_col_*) 사용.
- 실제로 전일작업일보만 컬럼명이 다르면, 코드에서 시트별 매핑을 나누는 수정이 필요(현재는 동일 매핑).

---

## settings.py 수정안 템플릿 (실제 컬럼 확인 후 적용)

실제 컬럼을 확인한 뒤, 다른 부분만 아래처럼 바꾸세요.

```python
# === 기준 시트 ===
master_col_product: str = "제품"           # 실제 컬럼명으로
master_col_process_code: str = "공정코드"
master_col_process_name: str = "공정명"
master_col_process_group: str = "공정대분류"
master_col_is_assembly: str = "조립공정"
master_col_order: str = "표시순서"

# === 작업일보/전일작업일보 ===
work_col_date: str = "작업종료일자"        # 실제: 작업일자 등
work_col_product: str = "품목명"          # 실제: 품목 등
work_col_process_code: str = "공정ID"     # 실제 컬럼명으로
work_col_process_name: str = "공정"
work_col_good_qty: str = "생산수량"
work_col_defect_qty: str = "Reject"
work_col_defect_type: str = "Reject 유형"

# === 물량 투입 Plan ===
plan_col_product: str = "제품"
plan_col_process_code: str = "공정코드"
plan_col_month_plan: str = "3월 계획"     # 실제 월별 컬럼명으로
plan_col_prev_plan: str = "전일 기준 계획"
plan_col_month_name: str = "월명"
plan_col_month_target: str = "월계획합계"
```

실제 `analyze_result.txt` 또는 직접 입력한 컬럼 목록을 알려주시면, 위 템플릿에 맞춰 **구체적인 settings.py 수정안( diff 형태)**으로 정리해 드리겠습니다.
