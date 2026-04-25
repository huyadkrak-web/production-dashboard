"""공장 받기(parse_shipment) 데이터 누적 JSON 저장."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .calculator import get_week_label

_SHIPMENT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "shipment_lots.json"
)

_SHIPMENT_COLS = ["move_date", "week", "lot_id", "product", "move_qty"]


def _read_shipment_file() -> list[dict]:
    if not _SHIPMENT_PATH.is_file():
        return []
    with _SHIPMENT_PATH.open(encoding="utf-8") as f:
        return json.load(f)


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

    lot_count = int(
        sdf.get("lot_id", pd.Series(dtype=object))
        .map(lambda x: str(x).strip() if pd.notna(x) else "")
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )
    total_qty = int(pd.to_numeric(sdf.get("move_qty"), errors="coerce").fillna(0).sum())
    return {
        "min_date": min_date,
        "max_date": max_date,
        "lot_count": lot_count,
        "total_qty": total_qty,
    }


def save_shipment(df: pd.DataFrame) -> dict | None:
    """``parse_shipment`` 결과를 주 단위 필드와 함께 ``shipment_lots.json``에 누적 저장합니다."""
    new_rows = _df_to_shipment_records(df)
    existing = _read_shipment_file()

    merged = pd.concat(
        [
            pd.DataFrame(existing, columns=_SHIPMENT_COLS)
            if existing
            else pd.DataFrame(columns=_SHIPMENT_COLS),
            pd.DataFrame(new_rows, columns=_SHIPMENT_COLS)
            if new_rows
            else pd.DataFrame(columns=_SHIPMENT_COLS),
        ],
        ignore_index=True,
    )
    if merged.empty:
        records: list[dict] = []
    else:
        merged = merged.drop_duplicates(
            subset=["move_date", "lot_id", "product"],
            keep="last",
        )
        records = merged.to_dict(orient="records")

    _SHIPMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _SHIPMENT_PATH.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print("[shipment] saved")
    return _build_shipment_summary(records)


def load_shipment() -> list[dict]:
    """저장된 출하 LOT JSON을 반환합니다. 파일이 없으면 빈 리스트입니다."""
    if not _SHIPMENT_PATH.is_file():
        return []
    with _SHIPMENT_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    print("[shipment] loaded")
    return data


def get_shipment_summary() -> dict | None:
    """저장된 출하 누적 요약(min/max date, lot 개수, move_qty 합계)을 반환합니다."""
    return _build_shipment_summary(load_shipment())


def clear_shipment() -> None:
    """출하 LOT JSON 파일을 삭제합니다."""
    if _SHIPMENT_PATH.is_file():
        _SHIPMENT_PATH.unlink()
    print("[shipment] cleared")
