from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAENGSAN_", extra="ignore")

    # === 공통 시트명 ===
    sheet_daily: str = "일보"
    sheet_work_today: str = "작업일보"
    sheet_work_prev: str = "전일작업일보"
    sheet_master: str = "기준"
    sheet_plan: str = "물량 투입 Plan"

    # === 기준 시트 컬럼 (공정 설정 테이블) ===
    # 예: 제품, 공정코드, 공정명, 공정대분류(Front/Back End), 조립공정 여부, 표출 순서
    master_col_product: str = "제품"
    master_col_process_code: str = "공정코드"
    master_col_process_name: str = "공정명"
    master_col_process_group: str = "공정대분류"
    master_col_is_assembly: str = "조립공정"
    master_col_order: str = "표시순서"

    # === 작업일보 / 전일작업일보 컬럼 ===
    # 원천데이터 컬럼 매핑 (작업일보/전일작업일보 헤더 동일)
    work_col_date: str = "작업종료일자"
    work_col_product: str = "제품군"
    work_col_process_code: str = "공정ID"
    work_col_process_name: str = "공정"
    work_col_good_qty: str = "생산수량"
    work_col_defect_qty: str = "Reject"
    # 불량유형 컬럼명은 파일에 따라 다를 수 있어, 없으면 빈 문자열로 처리
    work_col_defect_type: str = "Reject 유형"

    # === 물량 투입 Plan 시트 컬럼 ===
    # 3월 계획 / 전일 기준 계획을 이미 계산한 컬럼이 있다고 가정
    plan_col_product: str = "제품"
    plan_col_process_code: str = "공정코드"
    plan_col_month_plan: str = "3월 계획"
    plan_col_prev_plan: str = "전일 기준 계획"
    plan_col_month_name: str = "월명"  # 예: "3월"
    plan_col_month_target: str = "월계획합계"  # 상단 요약 14,000ea 등

    # Front / Back End 그룹명 기본값
    front_group_name: str = "Front"
    backend_group_name: str = "Back End"


settings = Settings()

