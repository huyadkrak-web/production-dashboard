from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .compute import compute_tables
from .models import ComputeResponse, DefectInputRow, HealthResponse
from .store import get_master, get_plan, save_master, save_plan, get_defects, save_defects
from .weekly_defect import router as weekly_defect_router
from .monthly_defect import router as monthly_defect_router
from .defect.router import router as defect_auto_router


app = FastAPI(title="생산일보 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://production-dashboard-ochre.vercel.app",
        "https://production-dashboard-demo.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(weekly_defect_router)
app.include_router(monthly_defect_router)
app.include_router(defect_auto_router)

MASTER_SAVE_REJECT_MSG = "저장할 기준정보가 없습니다. 먼저 기준정보를 불러와 주세요."
MASTER_SAVE_BLOCK_LOG = "[기준정보저장차단] 기준정보 미로드 또는 빈 데이터"


def _validate_master_save_body(body: object) -> list[dict]:
    """빈·불완전 payload는 저장 거부(기존 DB 삭제 방지)."""
    if not isinstance(body, list):
        print(MASTER_SAVE_BLOCK_LOG)
        raise HTTPException(status_code=400, detail=MASTER_SAVE_REJECT_MSG)
    if len(body) == 0:
        print(MASTER_SAVE_BLOCK_LOG)
        raise HTTPException(status_code=400, detail=MASTER_SAVE_REJECT_MSG)
    for row in body:
        if not isinstance(row, dict):
            print(MASTER_SAVE_BLOCK_LOG)
            raise HTTPException(status_code=400, detail=MASTER_SAVE_REJECT_MSG)
        product = str(row.get("product") or "").strip()
        process_code = str(row.get("process_code") or "").strip()
        if not product or not process_code:
            print(MASTER_SAVE_BLOCK_LOG)
            raise HTTPException(status_code=400, detail=MASTER_SAVE_REJECT_MSG)
    return body


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", message="up", now=datetime.utcnow().isoformat())


@app.get("/master")
def api_get_master() -> list[dict]:
    return get_master()


@app.post("/master")
def api_save_master(body: list[dict]) -> dict:
    _validate_master_save_body(body)
    save_master(body)
    return {"status": "ok", "message": "saved"}


@app.get("/plan/{month}")
def api_get_plan(month: str) -> list[dict]:
    return get_plan(month)


@app.post("/plan/{month}")
def api_save_plan(month: str, body: list[dict]) -> dict:
    save_plan(month, body)
    return {"status": "ok", "message": "saved"}


@app.get("/defects")
def api_get_defects() -> list[dict]:
    return get_defects()


@app.post("/defects")
def api_save_defects(body: list[DefectInputRow]) -> dict:
    save_defects([item.model_dump() for item in body])
    return {"status": "ok", "message": "saved"}


@app.post("/compute", response_model=ComputeResponse)
async def compute(
    base_date: date = Form(...),
    today_file: UploadFile = File(...),
    master_rows_json: str | None = Form(default=None),
    plan_rows_json: str | None = Form(default=None),
) -> ComputeResponse:
    today_bytes = await today_file.read()
    if master_rows_json:
        try:
            parsed_master = json.loads(master_rows_json)
            master_list = parsed_master if isinstance(parsed_master, list) else get_master()
        except Exception:
            master_list = get_master()
    else:
        master_list = get_master()
    month = base_date.strftime("%Y-%m")
    if plan_rows_json:
        try:
            parsed_plan = json.loads(plan_rows_json)
            plan_list = parsed_plan if isinstance(parsed_plan, list) else get_plan(month)
        except Exception:
            plan_list = get_plan(month)
    else:
        plan_list = get_plan(month)
    defect_list = get_defects()
    print(
        "[/compute debug]",
        {
            "base_date": str(base_date),
            "has_master_rows_json": bool(master_rows_json),
            "has_plan_rows_json": bool(plan_rows_json),
            "master_list_count": len(master_list) if isinstance(master_list, list) else 0,
            "plan_list_count": len(plan_list) if isinstance(plan_list, list) else 0,
            "master_list_sample_3": master_list[:3] if isinstance(master_list, list) else [],
            "plan_list_sample_3": plan_list[:3] if isinstance(plan_list, list) else [],
        },
    )
    out = compute_tables(master_list, plan_list, today_bytes, base_date=base_date, defect_list=defect_list)
    print("[/compute] compute_tables 정상 완료", {"base_date": str(base_date)})
    return ComputeResponse(**out)

