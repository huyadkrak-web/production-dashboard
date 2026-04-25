from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class ComputeMeta(BaseModel):
    base_date: date
    prev_date: date
    warnings: list[str] = Field(default_factory=list)
    detected_sheets_today: list[str] = Field(default_factory=list)
    detected_sheets_prev: list[str] = Field(default_factory=list)
    # 일보 상단 요약 텍스트용
    month_label: str | None = None  # 예: "3월"
    month_plan_total: float | None = None  # 예: 14000
    summary_title: str | None = None  # "1. 생산진척현황 : 3월 생산계획(GOC) : 14,000ea"


class ProductionProgressRow(BaseModel):
    product: str
    process_group: str
    process_name: str
    month_plan: float
    prev_day_plan: float
    cumulative_actual: float
    progress_day: float
    progress_month: float
    prev_day_actual: float
    remark: str


class AssemblyDefectRow(BaseModel):
    product: str
    process_group: str
    process_name: str
    assembly_cumulative: float
    assembly_prev_day: float
    defect_prev_day_count: float
    defect_prev_day_ppm: float
    defect_cumulative_count: float
    defect_cumulative_ppm: float
    defect_cumulative_types: str


class ComputeResponse(BaseModel):
    meta: ComputeMeta
    생산진척현황: list[ProductionProgressRow]
    조립공정불량: list[AssemblyDefectRow]


class MasterRow(BaseModel):
    product: str = ""
    process_code: str = ""
    process_name: str = ""
    process_group: str = ""
    is_assembly: str = "N"
    display_order: float = 0.0
    is_active: bool = True


class PlanRow(BaseModel):
    month: str = ""
    product: str = ""
    process_code: str = ""
    month_plan: float = 0.0
    prev_day_plan: float = 0.0


class DefectInputRow(BaseModel):
    date: str = ""  # YYYY-MM-DD
    product: str = ""
    process_group: str = ""  # "Front" | "Back End"
    defect_summary: str = ""  # multi-line string


class HealthResponse(BaseModel):
    status: Literal["ok"]
    message: str
    now: Any | None = None

