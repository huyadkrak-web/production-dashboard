"""주차별/월별 공정불량 자동 집계 저장/로드 (Supabase summary+detail)."""

from __future__ import annotations

from typing import Any

from ..db import supabase_delete_where, supabase_get, supabase_insert


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_num(value: Any) -> int | float:
    if value is None or value == "":
        return 0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    if f.is_integer():
        return int(f)
    return f


def _weekly_summary_rows(data: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        week = _as_str(row.get("week"))
        if not week:
            continue
        out.append(
            {
                "week": week,
                "ao_qty": _as_num(row.get("ao_qty")),
                "defect_total": _as_num(row.get("defect_total")),
                "total_ppm": _as_num(row.get("total_ppm")),
            }
        )
    return out


def _weekly_detail_rows(data: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        week = _as_str(row.get("week"))
        if not week:
            continue
        defects = row.get("defects")
        if not isinstance(defects, list):
            continue
        for d in defects:
            if not isinstance(d, dict):
                continue
            out.append(
                {
                    "week": week,
                    "defect_name": _as_str(d.get("name")),
                    "count": _as_num(d.get("count")),
                }
            )
    return out


def _monthly_summary_rows(data: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        month = _as_str(row.get("month") or row.get("label"))
        if not month:
            continue
        out.append(
            {
                "month": month,
                "ao_qty": _as_num(row.get("ao_qty")),
                "defect_total": _as_num(row.get("defect_total")),
                "total_ppm": _as_num(row.get("total_ppm")),
            }
        )
    return out


def _monthly_detail_rows(data: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        month = _as_str(row.get("month") or row.get("label"))
        if not month:
            continue
        defects = row.get("defects")
        if not isinstance(defects, list):
            continue
        for d in defects:
            if not isinstance(d, dict):
                continue
            out.append(
                {
                    "month": month,
                    "defect_name": _as_str(d.get("name")),
                    "count": _as_num(d.get("count")),
                }
            )
    return out


def _inflate_weekly_rows(summary_rows: list[dict], detail_rows: list[dict]) -> list[dict]:
    detail_by_week: dict[str, list[dict]] = {}
    for d in detail_rows:
        if not isinstance(d, dict):
            continue
        week = _as_str(d.get("week"))
        if not week:
            continue
        detail_by_week.setdefault(week, []).append(d)

    out: list[dict] = []
    for s in summary_rows:
        if not isinstance(s, dict):
            continue
        week = _as_str(s.get("week"))
        if not week:
            continue
        details = detail_by_week.get(week, [])
        defects = [
            {"name": _as_str(i.get("defect_name")), "count": _as_num(i.get("count"))}
            for i in details
        ]
        out.append(
            {
                "week": week,
                "ao_qty": _as_num(s.get("ao_qty")),
                "defect_total": _as_num(s.get("defect_total")),
                "total_ppm": _as_num(s.get("total_ppm")),
                "defects": defects,
            }
        )
    out.sort(key=lambda x: _as_str(x.get("week")))
    return out


def _inflate_monthly_rows(summary_rows: list[dict], detail_rows: list[dict]) -> list[dict]:
    detail_by_month: dict[str, list[dict]] = {}
    for d in detail_rows:
        if not isinstance(d, dict):
            continue
        month = _as_str(d.get("month"))
        if not month:
            continue
        detail_by_month.setdefault(month, []).append(d)

    out: list[dict] = []
    for s in summary_rows:
        if not isinstance(s, dict):
            continue
        month = _as_str(s.get("month"))
        if not month:
            continue
        details = detail_by_month.get(month, [])
        defects = [
            {"name": _as_str(i.get("defect_name")), "count": _as_num(i.get("count"))}
            for i in details
        ]
        out.append(
            {
                "month": month,
                "ao_qty": _as_num(s.get("ao_qty")),
                "defect_total": _as_num(s.get("defect_total")),
                "total_ppm": _as_num(s.get("total_ppm")),
                "defects": defects,
            }
        )
    out.sort(key=lambda x: _as_str(x.get("month")))
    return out


def save_weekly_auto(data: list[dict]) -> None:
    """주차별 자동 집계를 summary/detail 테이블에 저장합니다."""
    summary_rows = _weekly_summary_rows(data)
    detail_rows = _weekly_detail_rows(data)
    week_keys = sorted({_as_str(r.get("week")) for r in summary_rows if _as_str(r.get("week"))})
    for week in week_keys:
        supabase_delete_where("weekly_defect", "week", week)
        supabase_delete_where("weekly_defect_detail", "week", week)
    if summary_rows:
        supabase_insert("weekly_defect", summary_rows)
    if detail_rows:
        supabase_insert("weekly_defect_detail", detail_rows)
    print("[storage] saved weekly_defect")


def load_weekly_auto() -> list[dict]:
    """summary/detail 테이블에서 주차별 자동 집계를 읽어 복원합니다."""
    summary = supabase_get("weekly_defect")
    detail = supabase_get("weekly_defect_detail")
    if not isinstance(summary, list):
        return []
    if not isinstance(detail, list):
        detail = []
    data = _inflate_weekly_rows(summary, detail)
    print("[storage] loaded weekly_defect")
    return data


def save_monthly_auto(data: list[dict]) -> None:
    """월별 자동 집계를 summary/detail 테이블에 저장합니다."""
    summary_rows = _monthly_summary_rows(data)
    detail_rows = _monthly_detail_rows(data)
    month_keys = sorted({_as_str(r.get("month")) for r in summary_rows if _as_str(r.get("month"))})
    for month in month_keys:
        supabase_delete_where("monthly_defect", "month", month)
        supabase_delete_where("monthly_defect_detail", "month", month)
    if summary_rows:
        supabase_insert("monthly_defect", summary_rows)
    if detail_rows:
        supabase_insert("monthly_defect_detail", detail_rows)
    print("[storage] saved monthly_defect")


def load_monthly_auto() -> list[dict]:
    """summary/detail 테이블에서 월별 자동 집계를 읽어 복원합니다."""
    summary = supabase_get("monthly_defect")
    detail = supabase_get("monthly_defect_detail")
    if not isinstance(summary, list):
        return []
    if not isinstance(detail, list):
        detail = []
    data = _inflate_monthly_rows(summary, detail)
    print("[storage] loaded monthly_defect")
    return data
