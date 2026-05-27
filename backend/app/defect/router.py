"""공장 출하·불량 엑셀 업로드 → 주차별 자동 집계 API."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .calculator import (
    compute_lot_defect_ppm_from_shipments,
    compute_monthly_defect_from_shipments,
    compute_weekly_defect_from_shipments,
)
from .parser import _clean_lot, parse_defect, parse_shipment, parse_work, print_defect_shipment_lot_match_report
from .shipment_store import (
    clear_shipment,
    delete_shipment_by_move_date,
    fix_shipment_move_dates_bulk,
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
_latest_lot_warning: str = ""


class ShipmentFixMoveDateBody(BaseModel):
    """저장된 출하의 ``move_date``를 일괄 보정할 때 사용합니다(전체 삭제 없음)."""

    from_date: str = Field(..., description="YYYY-MM-DD")
    to_date: str = Field(..., description="YYYY-MM-DD")
    expected_moved_rows: int | None = Field(
        default=None,
        description="from_date에 있는 행 수와 일치해야 PATCH 진행(검증 생략 시 null)",
    )
    expected_moved_total_qty: int | None = Field(
        default=None,
        description="from_date 이동수량 합과 일치해야 PATCH 진행(검증 생략 시 null)",
    )


class ShipmentDeleteByMoveDateBody(BaseModel):
    """선택한 이동일자(``move_date``)의 출하 행만 부분 삭제 — 다른 날짜는 보존."""

    move_date: str = Field(..., description="YYYY-MM-DD — 이 날짜와 정확히 일치하는 행만 삭제")


@router.post("/reset")
def defect_auto_reset() -> dict:
    """출하(Supabase)와 주·월 자동 집계·메모리 LOT PPM을 모두 비웁니다. 이후 출하→compute 순으로 다시 올리세요."""
    clear_shipment()
    clear_weekly_defect_auto_storage()
    clear_monthly_defect_auto_storage()
    global _latest_lot_defects, _latest_lot_warning
    _latest_lot_defects = []
    _latest_lot_warning = ""
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
        save_result = save_shipment(df)
        parse_report = df.attrs.get("shipment_parse_report")
        dup = bool(save_result.get("duplicate_skipped"))
        inserted = int(save_result.get("inserted_rows") or 0)
        if dup:
            msg = "shipment duplicate skipped"
        elif inserted > 0:
            msg = "shipment saved"
        else:
            msg = "shipment saved"
        return {
            "status": "ok",
            "message": msg,
            "duplicate_skipped": dup,
            "inserted_rows": int(save_result.get("inserted_rows") or 0),
            "skipped_rows": int(save_result.get("skipped_rows") or 0),
            "inserted_qty": int(save_result.get("inserted_qty") or 0),
            "skipped_qty": int(save_result.get("skipped_qty") or 0),
            "shipment_summary": save_result.get("shipment_summary"),
            "shipment_parse_report": parse_report,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/shipment-fix-move-date")
def defect_auto_shipment_fix_move_date(body: ShipmentFixMoveDateBody) -> dict:
    """저장된 출하 중 ``from_date``인 행만 ``to_date``로 PATCH(전체 삭제·재업로드 없음)."""
    try:
        result = fix_shipment_move_dates_bulk(
            body.from_date,
            body.to_date,
            expected_moved_rows=body.expected_moved_rows,
            expected_moved_total_qty=body.expected_moved_total_qty,
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/shipment-delete-move-date")
def defect_auto_shipment_delete_move_date(body: ShipmentDeleteByMoveDateBody) -> dict:
    """선택한 이동일자(``move_date``)의 출하 행만 안전하게 부분 삭제(다른 날짜는 보존).

    전체 초기화(``/defect-auto/reset``)와 분리된 경로이며, 잘못 올라간 단일 일자의
    출하만 회수할 때 사용합니다.
    """
    try:
        result = delete_shipment_by_move_date(body.move_date)
        return {"status": "ok", **result}
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
        shipments = load_shipment()
        shipment_lot_ids = frozenset(
            x
            for s in shipments
            if isinstance(s, dict)
            for x in (_clean_lot(s.get("lot_id")),)
            if x
        )
        defect_df = parse_defect(defect_bytes, shipment_lot_ids=shipment_lot_ids)
        work_df = parse_work(work_bytes)
        print_defect_shipment_lot_match_report(defect_df, shipments)
        shipment_lots = sorted(
            {
                _clean_lot(s.get("lot_id"))
                for s in shipments
                if isinstance(s, dict) and _clean_lot(s.get("lot_id"))
            }
        )
        defect_lots = sorted(
            {
                _clean_lot(x)
                for x in defect_df.get("lot_id", [])
                if _clean_lot(x)
            }
        )
        matched_lot_set = set(shipment_lots) & set(defect_lots)
        matched_defect_rows_total = 0
        if "lot_id" in defect_df.columns:
            matched_defect_rows_total = int(
                defect_df["lot_id"].astype(str).isin(matched_lot_set).sum()
            )
        print(f"[defect_input_compare] shipment_lot_count={len(shipment_lots)}")
        print(f"[defect_input_compare] defect_lot_count={len(defect_lots)}")
        print(f"[defect_input_compare] matched_defect_rows_total={matched_defect_rows_total}")
        print(f"[defect_input_compare] shipment_lot_sample={shipment_lots[:10]}")
        print(f"[defect_input_compare] defect_lot_sample={defect_lots[:10]}")
        def _df_columns(df):
            return [str(c) for c in df.columns.tolist()]

        def _df_row_count(df):
            return int(len(df))

        def _sample_lot_ids(df):
            if "lot_id" not in df.columns:
                return []
            return df["lot_id"].astype(str).head(10).tolist()

        def _sample_defect_qty(df):
            if "defect_qty" not in df.columns:
                return []
            qty = __import__("pandas").to_numeric(df["defect_qty"], errors="coerce").fillna(0)
            return qty.head(10).tolist()

        # 호출부 검증: weekly/monthly/lot에 동일한 파싱 결과(복사본)를 전달
        defect_df_weekly = defect_df.copy(deep=True)
        defect_df_monthly = defect_df.copy(deep=True)
        defect_df_lot = defect_df.copy(deep=True)

        print(
            f"[defect_input_compare] target=weekly rows={_df_row_count(defect_df_weekly)} "
            f"columns={_df_columns(defect_df_weekly)}"
        )
        print(
            f"[defect_input_compare] target=monthly rows={_df_row_count(defect_df_monthly)} "
            f"columns={_df_columns(defect_df_monthly)}"
        )
        print(
            f"[defect_input_compare] target=lot rows={_df_row_count(defect_df_lot)} "
            f"columns={_df_columns(defect_df_lot)}"
        )
        print(
            f"[defect_input_compare] target=lot sample_lot_ids={_sample_lot_ids(defect_df_lot)}"
        )
        print(
            f"[defect_input_compare] target=lot sample_defect_qty={_sample_defect_qty(defect_df_lot)}"
        )

        print("[defect_input_compare] compute_call_order=weekly->monthly->lot")
        weekly = compute_weekly_defect_from_shipments(shipments, defect_df_weekly, work_df)
        monthly = compute_monthly_defect_from_shipments(shipments, defect_df_monthly, work_df)
        global _latest_lot_defects, _latest_lot_warning
        lot_candidate = compute_lot_defect_ppm_from_shipments(shipments, defect_df_lot)
        nonzero_lot_count = 0
        for row in lot_candidate:
            if not isinstance(row, dict):
                continue
            dt = row.get("defect_total", 0)
            try:
                if float(dt) > 0:
                    nonzero_lot_count += 1
            except (TypeError, ValueError):
                pass

        stale_lot_aggregate = matched_defect_rows_total == 0 or nonzero_lot_count == 0
        keep_previous_lot_defects = stale_lot_aggregate
        saved_candidate_rows = 0 if keep_previous_lot_defects else len(lot_candidate)

        lot_warning = ""
        if stale_lot_aggregate:
            lot_warning = "현재 불량파일의 LOT와 출하 LOT가 일치하지 않아 LOT별 불량률은 0으로 표시됩니다."
            print(f"[defect_input_compare] lot_warning={lot_warning}")
            print(
                "[defect_input_compare] keep_previous_lot_defects=true "
                f"previous_rows={len(_latest_lot_defects)} candidate_rows_skipped={len(lot_candidate)} "
                f"matched_defect_rows_total={matched_defect_rows_total} nonzero_lot_count={nonzero_lot_count}"
            )
            print(
                f"[defect_input_compare] saved_candidate_rows=0 stale_lot_aggregate={stale_lot_aggregate}"
            )
            # 교집합 0 또는 LOT별 집계가 전부 0이면 0짜리 후보를 메모리/UI에 반영하지 않음
        else:
            _latest_lot_defects = lot_candidate
            print(
                "[defect_input_compare] keep_previous_lot_defects=false "
                f"saved_candidate_rows={saved_candidate_rows} "
                f"matched_defect_rows_total={matched_defect_rows_total} nonzero_lot_count={nonzero_lot_count}"
            )
        _latest_lot_warning = lot_warning
        weekly_merged = save_weekly_auto(weekly)
        monthly_merged = save_monthly_auto(monthly)
        return {
            "status": "ok",
            "weekly": weekly_merged,
            "monthly": monthly_merged,
            "lot_warning": _latest_lot_warning,
            "lot_aggregate_debug": {
                "matched_defect_rows_total": matched_defect_rows_total,
                "nonzero_lot_count": nonzero_lot_count,
                "keep_previous_lot_defects": keep_previous_lot_defects,
                "saved_candidate_rows": saved_candidate_rows,
                "candidate_rows_evaluated": len(lot_candidate),
                "preserved_previous_rows": len(_latest_lot_defects),
            },
        }
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
    return {
        "status": "ok",
        "lot_defects": _latest_lot_defects,
        "warning": _latest_lot_warning,
    }
