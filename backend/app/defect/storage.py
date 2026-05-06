"""주차별/월별 공정불량 자동 집계 저장/로드 (Supabase summary+detail)."""

from __future__ import annotations

import json
from typing import Any

from ..db import supabase_delete_all, supabase_delete_where, supabase_get, supabase_insert


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


def _row_has_zero_defect_payload(row: dict) -> bool:
    """불량 합·품목별 건수가 모두 0이면 True (저장 시 기존값 보존 판단용)."""
    if not isinstance(row, dict):
        return True
    if _as_num(row.get("defect_total")) != 0:
        return False
    defects = row.get("defects")
    if not isinstance(defects, list) or len(defects) == 0:
        return True
    return all(_as_num(d.get("count")) == 0 for d in defects if isinstance(d, dict))


def _should_preserve_row_due_to_zero_incoming_ao(
    incoming: dict,
    previous: dict | None,
) -> bool:
    """이번 계산 ao_qty가 0인데 기존에 AO가 있으면 행 전체 덮어쓰기 금지."""
    if previous is None or not isinstance(previous, dict):
        return False
    if _as_num(incoming.get("ao_qty")) != 0:
        return False
    return _as_num(previous.get("ao_qty")) > 0


def _week_sort_key_storage(w: str) -> tuple[int, str]:
    w = _as_str(w).strip().upper()
    if w.startswith("WW") and len(w) > 2 and w[2:].isdigit():
        return (int(w[2:]), w)
    return (9999, w)


def _month_sort_key_storage(m: str) -> tuple[int, int]:
    s = _as_str(m).strip()
    parts = s.split(".", 1)
    if len(parts) != 2:
        return (99, 99)
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return (99, 99)


def merge_weekly_auto_payload(
    incoming: list[dict],
    existing: list[dict],
) -> tuple[list[dict], list[str]]:
    """이번 계산이 불량 0·종류 0인 주차는 기존 저장에 불량이 있으면 덮어쓰지 않음."""
    existing_by = {
        _as_str(r.get("week")): r
        for r in existing
        if isinstance(r, dict) and _as_str(r.get("week"))
    }
    incoming_by = {
        _as_str(r.get("week")): r
        for r in incoming
        if isinstance(r, dict) and _as_str(r.get("week"))
    }
    preserved: list[str] = []
    result = dict(existing_by)

    for wk, row in incoming_by.items():
        prev = existing_by.get(wk)
        if _row_has_zero_defect_payload(row):
            if prev is not None and not _row_has_zero_defect_payload(prev):
                preserved.append(wk)
                continue
        if _should_preserve_row_due_to_zero_incoming_ao(row, prev):
            preserved.append(wk)
            continue
        result[wk] = row

    merged = sorted(result.values(), key=lambda r: _week_sort_key_storage(_as_str(r.get("week"))))
    return merged, preserved


def merge_monthly_auto_payload(
    incoming: list[dict],
    existing: list[dict],
) -> tuple[list[dict], list[str]]:
    existing_by = {
        _as_str(r.get("month") or r.get("label")): r
        for r in existing
        if isinstance(r, dict) and _as_str(r.get("month") or r.get("label"))
    }
    incoming_by = {
        _as_str(r.get("month") or r.get("label")): r
        for r in incoming
        if isinstance(r, dict) and _as_str(r.get("month") or r.get("label"))
    }
    preserved: list[str] = []
    result = dict(existing_by)

    for mk, row in incoming_by.items():
        prev = existing_by.get(mk)
        if _row_has_zero_defect_payload(row):
            if prev is not None and not _row_has_zero_defect_payload(prev):
                preserved.append(mk)
                continue
        if _should_preserve_row_due_to_zero_incoming_ao(row, prev):
            preserved.append(mk)
            continue
        result[mk] = row

    merged = sorted(
        result.values(),
        key=lambda r: _month_sort_key_storage(_as_str(r.get("month") or r.get("label"))),
    )
    return merged, preserved


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


def save_weekly_auto(data: list[dict]) -> list[dict]:
    """주차별 자동 집계를 summary/detail 테이블에 저장합니다. 불량 0만으로 기존 비우기 방지 병합 후 반환."""
    existing = load_weekly_auto()
    merged, preserved_weeks = merge_weekly_auto_payload(data, existing)
    overwrite_weeks = sorted(
        {_as_str(r.get("week")) for r in data if isinstance(r, dict) and _as_str(r.get("week"))}
        - set(preserved_weeks)
    )
    print(
        "[defect_auto][save_weekly] overwrite_candidate_weeks "
        + json.dumps(overwrite_weeks, ensure_ascii=False),
    )
    if preserved_weeks:
        print(
            "[defect_auto][save_weekly][WARNING] preserved_weeks_skipped_empty_compute_overwrite "
            + json.dumps(sorted(preserved_weeks), ensure_ascii=False),
        )

    summary_rows = _weekly_summary_rows(merged)
    detail_rows = _weekly_detail_rows(merged)
    supabase_delete_all("weekly_defect_detail")
    supabase_delete_all("weekly_defect")
    if summary_rows:
        supabase_insert("weekly_defect", summary_rows)
    if detail_rows:
        supabase_insert("weekly_defect_detail", detail_rows)
    print("[storage] saved weekly_defect")
    return merged


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


def save_monthly_auto(data: list[dict]) -> list[dict]:
    """월별 자동 집계를 summary/detail 테이블에 저장합니다. 불량 0만으로 기존 비우기 방지 병합 후 반환."""
    existing = load_monthly_auto()
    merged, preserved_months = merge_monthly_auto_payload(data, existing)
    overwrite_months = sorted(
        {
            _as_str(r.get("month") or r.get("label"))
            for r in data
            if isinstance(r, dict) and _as_str(r.get("month") or r.get("label"))
        }
        - set(preserved_months)
    )
    print(
        "[defect_auto][save_monthly] overwrite_candidate_months "
        + json.dumps(overwrite_months, ensure_ascii=False),
    )
    if preserved_months:
        print(
            "[defect_auto][save_monthly][WARNING] preserved_months_skipped_empty_compute_overwrite "
            + json.dumps(sorted(preserved_months), ensure_ascii=False),
        )

    summary_rows = _monthly_summary_rows(merged)
    detail_rows = _monthly_detail_rows(merged)
    supabase_delete_all("monthly_defect_detail")
    supabase_delete_all("monthly_defect")
    if summary_rows:
        supabase_insert("monthly_defect", summary_rows)
    if detail_rows:
        supabase_insert("monthly_defect_detail", detail_rows)
    print("[storage] saved monthly_defect")
    return merged


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


def clear_weekly_defect_auto_storage() -> None:
    """주차별 공정불량 자동 집계(요약·상세)를 Supabase에서 전부 삭제합니다."""
    supabase_delete_all("weekly_defect_detail")
    supabase_delete_all("weekly_defect")
    print("[storage] cleared weekly_defect")


def clear_monthly_defect_auto_storage() -> None:
    """월별 공정불량 자동 집계(요약·상세)를 Supabase에서 전부 삭제합니다."""
    supabase_delete_all("monthly_defect_detail")
    supabase_delete_all("monthly_defect")
    print("[storage] cleared monthly_defect")
