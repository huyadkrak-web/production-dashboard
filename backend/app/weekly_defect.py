# -*- coding: utf-8 -*-
"""주차별 불량 PPM API."""
from __future__ import annotations

from fastapi import APIRouter

from .store import get_weekly_defect_ppm, save_weekly_defect_ppm

router = APIRouter(prefix="/weekly-defect-ppm", tags=["weekly-defect-ppm"])


@router.get("")
def api_get_weekly_defect_ppm() -> list[dict]:
    return get_weekly_defect_ppm()


@router.post("")
def api_save_weekly_defect_ppm(body: list[dict]) -> dict:
    save_weekly_defect_ppm(body)
    return {"status": "ok", "message": "saved"}
