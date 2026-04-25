"""주차별 공정불량 JSON 저장/로드."""

from __future__ import annotations

import json
from pathlib import Path

_WEEKLY_AUTO_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "weekly_defect_auto.json"
)

_MONTHLY_AUTO_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "monthly_defect_auto.json"
)


def save_weekly_auto(data: list[dict]) -> None:
    """``compute_weekly_defect`` 결과를 ``weekly_defect_auto.json``에 저장합니다."""
    path = _WEEKLY_AUTO_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[storage] saved weekly_auto.json")


def load_weekly_auto() -> list[dict]:
    """저장된 주차별 불량 JSON을 읽습니다. 파일이 없으면 빈 리스트를 반환합니다."""
    path = _WEEKLY_AUTO_PATH
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    print("[storage] loaded weekly_auto.json")
    return data


def save_monthly_auto(data: list[dict]) -> None:
    """월별 자동 집계 결과를 ``monthly_defect_auto.json``에 저장합니다."""
    path = _MONTHLY_AUTO_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[storage] saved monthly_auto.json")


def load_monthly_auto() -> list[dict]:
    """저장된 월별 자동 집계 JSON을 읽습니다. 파일이 없으면 빈 리스트를 반환합니다."""
    path = _MONTHLY_AUTO_PATH
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    print("[storage] loaded monthly_auto.json")
    return data
