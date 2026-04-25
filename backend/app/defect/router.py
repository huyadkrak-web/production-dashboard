"""공장 출하·불량 엑셀 업로드 → 주차별 자동 집계 API."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from .calculator import (
    compute_monthly_defect_from_shipments,
    compute_weekly_defect_from_shipments,
)
from .parser import parse_defect, parse_shipment, parse_work
from .shipment_store import get_shipment_summary, load_shipment, save_shipment
from .storage import (
    load_monthly_auto,
    load_weekly_auto,
    save_monthly_auto,
    save_weekly_auto,
)

router = APIRouter(prefix="/defect-auto", tags=["defect-auto"])


@router.post("/shipment")
async def defect_auto_shipment(
    shipment_file: UploadFile = File(...),
) -> dict:
    """공장 받기 엑셀을 업로드하면 출하 LOT을 ``shipment_lots.json``에 누적 저장합니다."""
    try:
        shipment_bytes = await shipment_file.read()
        df = parse_shipment(shipment_bytes)
        summary = save_shipment(df)
        return {
            "status": "ok",
            "message": "shipment saved",
            "shipment_summary": summary,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/compute")
async def defect_auto_compute(
    defect_file: UploadFile = File(...),
    work_file: UploadFile = File(...),
) -> dict:
    """불량 엑셀을 업로드하면 저장된 출하와 결합해 주·월별 집계 후 JSON에 저장합니다."""
    try:
        defect_bytes = await defect_file.read()
        work_bytes = await work_file.read()
        defect_df = parse_defect(defect_bytes)
        work_df = parse_work(work_bytes)
        shipments = load_shipment()
        weekly = compute_weekly_defect_from_shipments(shipments, defect_df, work_df)
        monthly = compute_monthly_defect_from_shipments(shipments, defect_df, work_df)
        save_weekly_auto(weekly)
        save_monthly_auto(monthly)
        return {"status": "ok", "weekly": weekly, "monthly": monthly}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/weekly")
def defect_auto_weekly() -> dict:
    """저장된 주차별 자동 집계 JSON을 반환합니다."""
    data = load_weekly_auto()
    return {"status": "ok", "weekly": data}


@router.get("/monthly")
def defect_auto_monthly() -> dict:
    """저장된 월별 자동 집계 JSON을 반환합니다."""
    data = load_monthly_auto()
    return {"status": "ok", "monthly": data}


@router.get("/shipment-summary")
def defect_auto_shipment_summary() -> dict:
    """출하 누적 요약(min/max date, lot 개수, move_qty 합계)을 반환합니다."""
    summary = get_shipment_summary()
    return {"status": "ok", "shipment_summary": summary}
