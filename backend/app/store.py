# -*- coding: utf-8 -*-
"""기준정보/월간플랜/누적불량유형(수기) JSON 저장·로드 및 저장 전 백업."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKUP_DIR = DATA_DIR / "backup"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _backup(path: Path) -> None:
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = path.stem
        backup_path = BACKUP_DIR / f"{stem}_{ts}.json"
        backup_path.write_bytes(path.read_bytes())


def get_master() -> list[dict]:
    _ensure_dirs()
    p = DATA_DIR / "master.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_master(data: list[dict]) -> None:
    _ensure_dirs()
    p = DATA_DIR / "master.json"
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_plan(month: str) -> list[dict]:
    _ensure_dirs()
    p = DATA_DIR / f"plan_{month}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_plan(month: str, data: list[dict]) -> None:
    _ensure_dirs()
    p = DATA_DIR / f"plan_{month}.json"
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_defects() -> list[dict]:
    _ensure_dirs()
    p = DATA_DIR / "defects.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_defects(data: list[dict]) -> None:
    _ensure_dirs()
    p = DATA_DIR / "defects.json"
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_weekly_defect_ppm() -> list[dict]:
    _ensure_dirs()
    p = DATA_DIR / "weekly_defect_ppm.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_weekly_defect_ppm(data: list[dict]) -> None:
    _ensure_dirs()
    p = DATA_DIR / "weekly_defect_ppm.json"
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


MONTHLY_DEFECT_BY_PRODUCT_PATH = DATA_DIR / "monthly_defect_ppm_by_product.json"
MONTHLY_DEFECT_LEGACY_PATH = DATA_DIR / "monthly_defect_ppm.json"
# 출하 기준 월별 조립 불량율(PPM) — 생산일보 계산과 분리된 단일 저장소(주차별 PPM과 동일 패턴)
MONTHLY_DEFECT_SHIPMENT_PATH = DATA_DIR / "monthly_defect_ppm_shipment.json"


def _monthly_product_key(product: str) -> str:
    t = str(product or "").strip()
    return t if t else "default"


def _migrate_monthly_flat_to_by_product_once() -> None:
    """구 단일 배열 monthly_defect_ppm.json → 제품별 dict (마스터 제품마다 동일 스냅샷 복제)."""
    _ensure_dirs()
    if MONTHLY_DEFECT_BY_PRODUCT_PATH.exists() or not MONTHLY_DEFECT_LEGACY_PATH.exists():
        return
    try:
        raw = json.loads(MONTHLY_DEFECT_LEGACY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, list):
        return
    keys: list[str] = []
    for m in get_master():
        p = str(m.get("product") or "").strip()
        if p and p not in keys:
            keys.append(p)
    if not keys:
        keys = ["default"]
    snapshot = json.loads(json.dumps(raw, ensure_ascii=False))
    db = {k: json.loads(json.dumps(snapshot, ensure_ascii=False)) for k in keys}
    _backup(MONTHLY_DEFECT_LEGACY_PATH)
    MONTHLY_DEFECT_BY_PRODUCT_PATH.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    MONTHLY_DEFECT_LEGACY_PATH.unlink(missing_ok=True)


def _read_monthly_by_product() -> dict[str, list]:
    _migrate_monthly_flat_to_by_product_once()
    if not MONTHLY_DEFECT_BY_PRODUCT_PATH.exists():
        return {}
    try:
        data = json.loads(MONTHLY_DEFECT_BY_PRODUCT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list] = {}
    for k, v in data.items():
        sk = str(k).strip() if k is not None else ""
        if not sk:
            continue
        if isinstance(v, list):
            out[sk] = v
    return out


def get_monthly_defect_ppm(product: str) -> list[dict]:
    _ensure_dirs()
    _migrate_monthly_flat_to_by_product_once()
    db = _read_monthly_by_product()
    key = _monthly_product_key(product)
    rows = db.get(key)
    if isinstance(rows, list):
        return rows
    return []


def save_monthly_defect_ppm(product: str, data: list[dict]) -> None:
    _ensure_dirs()
    _migrate_monthly_flat_to_by_product_once()
    key = _monthly_product_key(product)
    db = _read_monthly_by_product()
    db[key] = data
    _backup(MONTHLY_DEFECT_BY_PRODUCT_PATH)
    MONTHLY_DEFECT_BY_PRODUCT_PATH.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _bootstrap_monthly_shipment_from_legacy_by_product() -> list[dict]:
    """제품별 파일만 있고 출하 단일 파일이 없을 때, 읽기 전용으로 후보 한 벌을 반환(저장은 사용자 POST 시)."""
    db = _read_monthly_by_product()
    if not db:
        return []
    if len(db) == 1:
        v = next(iter(db.values()))
        return v if isinstance(v, list) else []
    if "default" in db and isinstance(db["default"], list):
        return db["default"]
    k0 = sorted(db.keys(), key=lambda x: str(x))[0]
    v0 = db.get(k0)
    return v0 if isinstance(v0, list) else []


def get_monthly_defect_ppm_shipment() -> list[dict]:
    """출하 기준 월별 PPM 단일 데이터(배열)."""
    _ensure_dirs()
    p = MONTHLY_DEFECT_SHIPMENT_PATH
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return raw if isinstance(raw, list) else []
    return _bootstrap_monthly_shipment_from_legacy_by_product()


def save_monthly_defect_ppm_shipment(data: list[dict]) -> None:
    _ensure_dirs()
    _backup(MONTHLY_DEFECT_SHIPMENT_PATH)
    MONTHLY_DEFECT_SHIPMENT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
