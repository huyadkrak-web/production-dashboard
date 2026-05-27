"""공장 받기(parse_shipment) 데이터 누적 저장 (Supabase)."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

import pandas as pd

from ..db import (
    supabase_delete_all,
    supabase_delete_where,
    supabase_get,
    supabase_insert,
    supabase_patch_by_filters,
)
from ..excluded_sample_lots import filter_shipment_dict_rows
from .calculator import get_week_label

logger = logging.getLogger(__name__)

_SHIPMENT_COLS = ["move_date", "week", "lot_id", "product", "move_qty"]

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _df_to_shipment_records(df: pd.DataFrame) -> list[dict]:
    dfc = df.copy()
    dfc["move_date"] = pd.to_datetime(dfc["move_date"], errors="coerce")
    dfc = dfc[dfc["move_date"].notna()].copy()
    dfc["week"] = dfc["move_date"].apply(get_week_label)
    dfc["move_date"] = dfc["move_date"].dt.strftime("%Y-%m-%d")
    out = dfc[["move_date", "week", "lot_id", "product", "move_qty"]].copy()
    out["move_qty"] = pd.to_numeric(out["move_qty"], errors="coerce").fillna(0).astype(int)
    out["lot_id"] = out["lot_id"].astype(str)
    out["product"] = out["product"].map(lambda x: "" if pd.isna(x) else str(x))
    return out.to_dict(orient="records")


def _shipment_identity_tuple(row: dict) -> tuple[str, str, str, int]:
    """(이동일자, LOT, 제품, 수량) — 동일 출하 재업로드 판별용."""
    n = _to_shipment_row(row) if row else {}
    if not n:
        return ("", "", "", 0)
    md = str(n.get("move_date", "")).strip()[:10]
    lid = str(n.get("lot_id", "")).strip()
    prod = str(n.get("product", "")).strip()
    qty = int(pd.to_numeric(n.get("move_qty"), errors="coerce") or 0)
    return (md, lid, prod, qty)


def _to_shipment_row(row: dict) -> dict:
    move_date = pd.to_datetime(row.get("move_date"), errors="coerce")
    if pd.isna(move_date):
        return {}
    lot_id = "" if pd.isna(row.get("lot_id")) else str(row.get("lot_id")).strip()
    product = "" if pd.isna(row.get("product")) else str(row.get("product")).strip()
    qty = pd.to_numeric(row.get("move_qty"), errors="coerce")
    move_qty = float(qty) if pd.notna(qty) else 0.0
    if float(move_qty).is_integer():
        move_qty = int(move_qty)
    move_date_str = move_date.strftime("%Y-%m-%d")
    week = row.get("week")
    week_str = str(week).strip() if week is not None else ""
    if not week_str:
        week_str = get_week_label(move_date)
    return {
        "move_date": move_date_str,
        "week": week_str,
        "lot_id": lot_id,
        "product": product,
        "move_qty": move_qty,
    }


def _build_shipment_summary(records: list[dict]) -> dict | None:
    if not records:
        return None
    sdf = pd.DataFrame(records)
    if sdf.empty:
        return None

    move_dates = pd.to_datetime(sdf.get("move_date"), errors="coerce")
    move_dates = move_dates[move_dates.notna()]
    if move_dates.empty:
        min_date = ""
        max_date = ""
    else:
        min_date = move_dates.min().strftime("%Y-%m-%d")
        max_date = move_dates.max().strftime("%Y-%m-%d")

    # 출하 "Lot N건"은 엑셀 데이터 행 수(동일 LOT 다중 행 유지)와 맞춤
    lot_count = int(len(sdf))
    total_qty = int(pd.to_numeric(sdf.get("move_qty"), errors="coerce").fillna(0).sum())
    return {
        "min_date": min_date,
        "max_date": max_date,
        "lot_count": lot_count,
        "total_qty": total_qty,
    }


def _empty_shipment_summary_dict() -> dict[str, Any]:
    return {"min_date": "", "max_date": "", "lot_count": 0, "total_qty": 0}


def _shipment_save_result(
    *,
    duplicate_skipped: bool,
    inserted_rows: int,
    skipped_rows: int,
    inserted_qty: int,
    skipped_qty: int,
    shipment_summary: dict[str, Any],
) -> dict[str, Any]:
    summary = {**shipment_summary, "duplicate_skipped": duplicate_skipped}
    return {
        "duplicate_skipped": duplicate_skipped,
        "inserted_rows": inserted_rows,
        "skipped_rows": skipped_rows,
        "inserted_qty": inserted_qty,
        "skipped_qty": skipped_qty,
        "shipment_summary": summary,
    }


def save_shipment(df: pd.DataFrame) -> dict[str, Any]:
    """``parse_shipment`` 결과를 Supabase ``shipment``에 누적 저장(행 단위 중복 스킵).

    동일 행 기준: (move_date, lot_id, product, move_qty).
    업로드 파일의 모든 행이 이미 DB에 있으면 insert 없이 ``duplicate_skipped=True``.
    일부만 신규면 신규 행만 insert(기존 행 delete 없음).
    """
    new_rows = _df_to_shipment_records(df)
    new_rows = filter_shipment_dict_rows(new_rows, context="save_shipment")

    existing = load_shipment()
    base_summary = _build_shipment_summary(existing) or _empty_shipment_summary_dict()

    if not new_rows:
        return _shipment_save_result(
            duplicate_skipped=False,
            inserted_rows=0,
            skipped_rows=0,
            inserted_qty=0,
            skipped_qty=0,
            shipment_summary=base_summary,
        )

    exist_counter: Counter[tuple[str, str, str, int]] = Counter()
    for r in existing:
        t = _shipment_identity_tuple(r)
        if t[0] and t[1]:
            exist_counter[t] += 1

    exist_avail = exist_counter.copy()
    to_insert: list[dict] = []
    skipped_rows = 0
    skipped_qty = 0

    for r in new_rows:
        t = _shipment_identity_tuple(r)
        if not t[0] or not t[1]:
            continue
        qty = int(t[3])
        if exist_avail.get(t, 0) > 0:
            exist_avail[t] -= 1
            skipped_rows += 1
            skipped_qty += qty
        else:
            to_insert.append(r)

    inserted_rows = len(to_insert)
    inserted_qty = int(
        sum(int(pd.to_numeric(r.get("move_qty"), errors="coerce") or 0) for r in to_insert)
    )
    duplicate_skipped = inserted_rows == 0 and skipped_rows > 0

    if duplicate_skipped:
        print(
            "[shipment] skipped duplicate upload (identical rows already in DB) "
            f"skipped_rows={skipped_rows} skipped_qty={skipped_qty}"
        )
        return _shipment_save_result(
            duplicate_skipped=True,
            inserted_rows=0,
            skipped_rows=skipped_rows,
            inserted_qty=0,
            skipped_qty=skipped_qty,
            shipment_summary=base_summary,
        )

    if to_insert:
        supabase_insert("shipment", to_insert)
        records = load_shipment()
        final_summary = _build_shipment_summary(records) or _empty_shipment_summary_dict()
        print(
            "[shipment] saved partial/insert "
            f"inserted_rows={inserted_rows} inserted_qty={inserted_qty} "
            f"skipped_rows={skipped_rows} skipped_qty={skipped_qty}"
        )
    else:
        final_summary = base_summary

    return _shipment_save_result(
        duplicate_skipped=False,
        inserted_rows=inserted_rows,
        skipped_rows=skipped_rows,
        inserted_qty=inserted_qty,
        skipped_qty=skipped_qty,
        shipment_summary=final_summary,
    )


def load_shipment() -> list[dict]:
    """저장된 출하 LOT 레코드를 Supabase에서 조회합니다."""
    raw = supabase_get("shipment")
    if not isinstance(raw, list):
        return []
    rows: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        normalized = _to_shipment_row(r)
        if not normalized:
            continue
        rows.append(normalized)
    data = filter_shipment_dict_rows(rows, context="load_shipment")
    print("[shipment] loaded")
    return data


def get_shipment_summary() -> dict | None:
    """저장된 출하 누적 요약(min/max date, lot 개수, move_qty 합계)을 반환합니다."""
    return _build_shipment_summary(load_shipment())


def _normalize_shipment_iso_date(d: str) -> str:
    s = str(d).strip()[:10]
    if not _DATE_KEY.match(s):
        raise ValueError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {d!r}")
    return s


def _rollup_shipment_rows_qty(records: list[dict], iso_date: str) -> tuple[int, int]:
    d = _normalize_shipment_iso_date(iso_date)
    n = 0
    q = 0
    for r in records:
        if not isinstance(r, dict):
            continue
        md = str(r.get("move_date", "")).strip()[:10]
        if md == d:
            n += 1
            q += int(pd.to_numeric(r.get("move_qty"), errors="coerce") or 0)
    return n, q


def fix_shipment_move_dates_bulk(
    from_date: str,
    to_date: str,
    *,
    expected_moved_rows: int | None = None,
    expected_moved_total_qty: int | None = None,
) -> dict[str, Any]:
    """``move_date``가 ``from_date``인 출하 행만 ``to_date``로 PATCH(주차 라벨 동시 갱신). 전체 삭제 없음."""
    from_d = _normalize_shipment_iso_date(from_date)
    to_d = _normalize_shipment_iso_date(to_date)
    if from_d == to_d:
        raise ValueError("from_date와 to_date가 같습니다.")

    def _uk(x: str) -> str:
        return x.replace("-", "_")

    fk, tk = _uk(from_d), _uk(to_d)

    before_all = load_shipment()
    b_fr, b_fq = _rollup_shipment_rows_qty(before_all, from_d)
    b_tr, b_tq = _rollup_shipment_rows_qty(before_all, to_d)

    if b_fr == 0:
        a_fr, a_fq = b_fr, b_fq
        a_tr, a_tq = b_tr, b_tq
        payload = {
            "from_date": from_d,
            "to_date": to_d,
            f"before_{fk}_rows": b_fr,
            f"before_{fk}_qty": b_fq,
            f"before_{tk}_rows": b_tr,
            f"before_{tk}_qty": b_tq,
            "moved_rows": 0,
            "moved_qty": 0,
            f"after_{fk}_rows": a_fr,
            f"after_{fk}_qty": a_fq,
            f"after_{tk}_rows": a_tr,
            f"after_{tk}_qty": a_tq,
        }
        logger.info("[shipment_date_fix] %s", json.dumps(payload, ensure_ascii=False))
        print("[shipment_date_fix]", json.dumps(payload, ensure_ascii=False))
        return {"message": "from_date에 해당하는 행이 없습니다.", **payload}

    if expected_moved_rows is not None and int(expected_moved_rows) != b_fr:
        raise ValueError(
            f"expected_moved_rows={expected_moved_rows!r} 이지만 from_date({from_d}) 행 수는 {b_fr}입니다."
        )
    if expected_moved_total_qty is not None and int(expected_moved_total_qty) != b_fq:
        raise ValueError(
            f"expected_moved_total_qty={expected_moved_total_qty!r} 이지만 from_date({from_d}) 이동수량 합은 {b_fq}입니다."
        )

    week_new = get_week_label(pd.Timestamp(to_d))
    supabase_patch_by_filters(
        "shipment",
        {"move_date": from_d},
        {"move_date": to_d, "week": week_new},
    )

    after_all = load_shipment()
    a_fr, a_fq = _rollup_shipment_rows_qty(after_all, from_d)
    a_tr, a_tq = _rollup_shipment_rows_qty(after_all, to_d)

    moved_rows = b_fr
    moved_qty = b_fq
    payload = {
        "from_date": from_d,
        "to_date": to_d,
        f"before_{fk}_rows": b_fr,
        f"before_{fk}_qty": b_fq,
        f"before_{tk}_rows": b_tr,
        f"before_{tk}_qty": b_tq,
        "moved_rows": moved_rows,
        "moved_qty": moved_qty,
        f"after_{fk}_rows": a_fr,
        f"after_{fk}_qty": a_fq,
        f"after_{tk}_rows": a_tr,
        f"after_{tk}_qty": a_tq,
    }
    logger.info("[shipment_date_fix] %s", json.dumps(payload, ensure_ascii=False))
    print("[shipment_date_fix]", json.dumps(payload, ensure_ascii=False))
    summary = get_shipment_summary()
    return {"message": "shipment move_date patched", "shipment_summary": summary, **payload}


def get_shipment_move_date_rollups() -> list[dict[str, int | str]]:
    """이동일자별 출하 행 수·수량 합계(날짜 오름차순). ``move_date``(엑셀 이동일자) 기준·업로드 순과 무관."""
    records = load_shipment()
    if not records:
        return []
    acc: dict[str, list[int]] = {}
    for r in records:
        raw = r.get("move_date")
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.isna(ts):
            continue
        d = ts.strftime("%Y-%m-%d")
        q = int(pd.to_numeric(r.get("move_qty"), errors="coerce") or 0)
        if d not in acc:
            acc[d] = [0, 0]
        acc[d][0] += 1
        acc[d][1] += q
    out: list[dict[str, int | str]] = []
    for d in sorted(acc.keys()):
        rc, tq = acc[d]
        out.append({"date": d, "row_count": rc, "total_qty": tq})
    return out


def delete_shipment_by_move_date(move_date: str) -> dict[str, Any]:
    """``move_date``가 정확히 일치하는 출하 행만 부분 삭제(다른 날짜는 절대 건드리지 않음).

    전체 초기화(:func:`clear_shipment`)와 분리된 안전 경로로, 잘못 업로드된 단일 일자의
    출하만 회수할 때 사용합니다. PATCH(:func:`fix_shipment_move_dates_bulk`)는 날짜 보정이고
    이 함수는 삭제만 수행합니다.

    - 삭제 전후 일치 행 수·이동수량 합계를 비교해 실제 삭제분(``deleted_rows``, ``deleted_total_qty``)을 산출.
    - ``[shipment_delete_by_move_date]`` 로그로 추적.
    """
    d = _normalize_shipment_iso_date(move_date)

    before_all = load_shipment()
    b_rows, b_qty = _rollup_shipment_rows_qty(before_all, d)

    if b_rows == 0:
        before_summary = _build_shipment_summary(before_all) or _empty_shipment_summary_dict()
        payload = {
            "move_date": d,
            "deleted_rows": 0,
            "deleted_total_qty": 0,
            "before_rows": 0,
            "before_qty": 0,
            "after_rows": 0,
            "after_qty": 0,
        }
        logger.info(
            "[shipment_delete_by_move_date] %s",
            json.dumps(payload, ensure_ascii=False),
        )
        print("[shipment_delete_by_move_date]", json.dumps(payload, ensure_ascii=False))
        return {
            "message": "해당 move_date에 일치하는 행이 없습니다.",
            "shipment_summary": before_summary,
            **payload,
        }

    supabase_delete_where("shipment", "move_date", d)

    after_all = load_shipment()
    a_rows, a_qty = _rollup_shipment_rows_qty(after_all, d)
    deleted_rows = b_rows - a_rows
    deleted_total_qty = b_qty - a_qty

    payload = {
        "move_date": d,
        "deleted_rows": int(deleted_rows),
        "deleted_total_qty": int(deleted_total_qty),
        "before_rows": int(b_rows),
        "before_qty": int(b_qty),
        "after_rows": int(a_rows),
        "after_qty": int(a_qty),
    }
    logger.info(
        "[shipment_delete_by_move_date] %s",
        json.dumps(payload, ensure_ascii=False),
    )
    print("[shipment_delete_by_move_date]", json.dumps(payload, ensure_ascii=False))

    after_summary = _build_shipment_summary(after_all) or _empty_shipment_summary_dict()
    return {
        "message": "shipment rows deleted by move_date",
        "shipment_summary": after_summary,
        **payload,
    }


def clear_shipment() -> None:
    """Supabase ``shipment`` 테이블 데이터를 전체 삭제합니다."""
    supabase_delete_all("shipment")
    print("[shipment] cleared")
