"""공장 출하·불량 엑셀 업로드 → 주차별 자동 집계 API."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from .calculator import (
    compute_lot_defect_ppm_from_shipments,
    compute_monthly_defect_from_shipments,
    compute_weekly_defect_from_shipments,
)
from .parser import parse_defect, parse_shipment, parse_work
from .shipment_store import (
    clear_shipment,
    get_shipment_move_date_rollups,
    get_shipment_summary,
    load_shipment,
    save_shipment,
)
from .storage import (
    clear_monthly_defect_auto_storage,
    clear_weekly_defect_auto_storage,
    load_monthly_auto,
    load_weekly_auto,
    save_monthly_auto,
    save_weekly_auto,
)

router = APIRouter(prefix="/defect-auto", tags=["defect-auto"])
_latest_lot_defects: list[dict] = []


@router.post("/reset")
def defect_auto_reset() -> dict:
    """출하(Supabase)와 주·월 자동 집계·메모리 LOT PPM을 모두 비웁니다. 이후 출하→compute 순으로 다시 올리세요."""
    clear_shipment()
    clear_weekly_defect_auto_storage()
    clear_monthly_defect_auto_storage()
    global _latest_lot_defects
    _latest_lot_defects = []
    summary = get_shipment_summary()
    return {
        "status": "ok",
        "message": "출하·주차별·월별 자동 집계·LOT별 PPM(서버 메모리)을 초기화했습니다.",
        "shipment_summary": summary,
    }


@router.post("/shipment")
async def defect_auto_shipment(
    shipment_file: UploadFile = File(...),
) -> dict:
    """공장 받기 엑셀을 업로드하면 출하 LOT을 ``shipment_lots.json``에 누적 저장합니다."""
    try:
        shipment_bytes = await shipment_file.read()
        df = parse_shipment(shipment_bytes)
        summary = save_shipment(df)
        parse_report = df.attrs.get("shipment_parse_report")
        dup = isinstance(summary, dict) and summary.get("duplicate_skipped") is True
        return {
            "status": "ok",
            "message": "shipment duplicate skipped" if dup else "shipment saved",
            "shipment_summary": summary,
            "shipment_parse_report": parse_report,
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
        global _latest_lot_defects
        _latest_lot_defects = compute_lot_defect_ppm_from_shipments(shipments, defect_df)
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


@router.get("/shipment-move-dates")
def defect_auto_shipment_move_dates() -> dict:
    """저장된 출하의 이동일자별 행 수·수량(중복 업로드·누락 확인용)."""
    rollups = get_shipment_move_date_rollups()
    return {"status": "ok", "move_dates": rollups}


@router.get("/lot-defects")
def defect_auto_lot_defects() -> dict:
    """최근 자동계산 기준 LOT별 조립 불량율(PPM) 집계를 반환합니다."""
    return {"status": "ok", "lot_defects": _latest_lot_defects}
