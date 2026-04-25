# -*- coding: utf-8 -*-
"""월별 조립 불량율(PPM) API — 출하 기준 단일 저장(주차별 PPM과 동일, 생산일보 계산과 분리)."""
from __future__ import annotations

from fastapi import APIRouter

from .store import get_monthly_defect_ppm_shipment, save_monthly_defect_ppm_shipment

router = APIRouter(prefix="/monthly-defect-ppm", tags=["monthly-defect-ppm"])


@router.get("")
def api_get_monthly_defect_ppm() -> list[dict]:
    return get_monthly_defect_ppm_shipment()


@router.post("")
def api_save_monthly_defect_ppm(body: list[dict]) -> dict:
    save_monthly_defect_ppm_shipment(body)
    return {"status": "ok", "message": "saved"}
