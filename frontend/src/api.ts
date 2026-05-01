export type ComputeMeta = {
  base_date: string;
  prev_date: string;
  warnings: string[];
  detected_sheets_today: string[];
  detected_sheets_prev: string[];
  month_label?: string | null;
  month_plan_total?: number | null;
  summary_title?: string | null;
};

export type ProductionProgressRow = {
  product: string;
  process_group: string;
  process_name: string;
  month_plan: number;
  prev_day_plan: number;
  cumulative_actual: number;
  progress_day: number;
  progress_month: number;
  prev_day_actual: number;
  remark: string;
};

export type AssemblyDefectRow = {
  product: string;
  process_group: string;
  process_name: string;
  assembly_cumulative: number;
  assembly_prev_day: number;
  defect_prev_day_count: number;
  defect_prev_day_ppm: number;
  defect_cumulative_count: number;
  defect_cumulative_ppm: number;
  defect_cumulative_types: string;
};

export type ComputeResponse = {
  meta: ComputeMeta;
  생산진척현황: ProductionProgressRow[];
  조립공정불량: AssemblyDefectRow[];
};

export type MasterRow = {
  product: string;
  process_code: string;
  process_name: string;
  process_group: string;
  is_assembly: string;
  display_order: number;
  is_active: boolean;
};

export type PlanRow = {
  month: string;
  product: string;
  process_code: string;
  month_plan: number;
  prev_day_plan: number;
};

export type AccumulatedDefectSummaryRow = {
  date: string;
  product: string;
  process_group: string; // "Front" | "Back End"
  defect_summary: string; // multi-line string
};

/** 주차별 저장: 불량 건수(출하 ao_qty 대비 ppm은 클라이언트에서 계산) */
export type WeeklyDefectPpmDefectItem = {
  name: string;
  count: number;
};

export type WeeklyDefectPpmRow = {
  week: string;
  /** 출하(또는 검사) 대상 수량 — 분모 */
  ao_qty: number;
  /** 불량 총 건수(보통 defects[].count 합) */
  defect_total: number;
  defects: WeeklyDefectPpmDefectItem[];
};

/** 월별 출하 PPM — `label` + `defects[].value`(PPM) + `total_ppm`. 레거시 `ppm`만 있으면 불러올 때 `total_ppm`으로만 승격 */
export type MonthlyDefectPpmDefectItem = {
  name: string;
  value: number;
};

export type MonthlyDefectPpmRow = {
  label: string;
  defects: MonthlyDefectPpmDefectItem[];
  total_ppm: number;
};

/** 로컬 개발 전용. 배포 시 `VITE_API_BASE_URL`로 실제 백엔드 주소를 지정하세요. */
const API_BASE_FALLBACK = "http://localhost:8000";

function resolveApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (typeof raw === "string" && raw.trim() !== "") {
    return raw.trim().replace(/\/+$/u, "");
  }
  return API_BASE_FALLBACK;
}

export const API_BASE = resolveApiBaseUrl();

export async function getMaster(): Promise<MasterRow[]> {
  const res = await fetch(`${API_BASE}/master`);
  if (!res.ok) throw new Error(`GET /master failed: ${res.status}`);
  return res.json();
}

export async function postMaster(rows: MasterRow[]): Promise<void> {
  const res = await fetch(`${API_BASE}/master`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(`POST /master failed: ${res.status}`);
}

export async function getPlan(month: string): Promise<PlanRow[]> {
  const res = await fetch(`${API_BASE}/plan/${encodeURIComponent(month)}`);
  if (!res.ok) throw new Error(`GET /plan failed: ${res.status}`);
  return res.json();
}

export async function postPlan(month: string, rows: PlanRow[]): Promise<void> {
  const res = await fetch(`${API_BASE}/plan/${encodeURIComponent(month)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(`POST /plan failed: ${res.status}`);
}

export async function getDefects(): Promise<AccumulatedDefectSummaryRow[]> {
  const res = await fetch(`${API_BASE}/defects`);
  if (!res.ok) throw new Error(`GET /defects failed: ${res.status}`);
  return res.json();
}

export async function postDefects(rows: AccumulatedDefectSummaryRow[]): Promise<void> {
  const res = await fetch(`${API_BASE}/defects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(`POST /defects failed: ${res.status}`);
}

export async function getWeeklyDefectPpm(): Promise<WeeklyDefectPpmRow[]> {
  const res = await fetch(`${API_BASE}/weekly-defect-ppm`);
  if (!res.ok) throw new Error(`GET /weekly-defect-ppm failed: ${res.status}`);
  return res.json();
}

export async function postWeeklyDefectPpm(rows: WeeklyDefectPpmRow[]): Promise<void> {
  const res = await fetch(`${API_BASE}/weekly-defect-ppm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(`POST /weekly-defect-ppm failed: ${res.status}`);
}

export async function getMonthlyDefectPpm(): Promise<MonthlyDefectPpmRow[]> {
  const res = await fetch(`${API_BASE}/monthly-defect-ppm`);
  if (!res.ok) throw new Error(`GET /monthly-defect-ppm failed: ${res.status}`);
  return res.json();
}

export async function postMonthlyDefectPpm(rows: MonthlyDefectPpmRow[]): Promise<void> {
  const res = await fetch(`${API_BASE}/monthly-defect-ppm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(`POST /monthly-defect-ppm failed: ${res.status}`);
}

/** POST /defect-auto/shipment — 공장 받기(출하) 엑셀 누적 저장 */
export async function uploadDefectShipment(file: File): Promise<{
  status: string;
  message: string;
  shipment_summary: DefectAutoShipmentSummary | null;
  /** 서버 출하 파싱 진단(시트명·제외 행 등). 없을 수 있음 */
  shipment_parse_report?: unknown;
}> {
  const fd = new FormData();
  fd.append("shipment_file", file);
  const res = await fetch(`${API_BASE}/defect-auto/shipment`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<{
    status: string;
    message: string;
    shipment_summary: DefectAutoShipmentSummary | null;
    shipment_parse_report?: unknown;
  }>;
}

export type DefectAutoComputeResponse = {
  status: string;
  weekly: unknown[];
  monthly: unknown[];
};

export type DefectAutoShipmentSummary = {
  min_date: string;
  max_date: string;
  lot_count: number;
  total_qty: number;
  /** 동일 출하(이동일자·LOT·제품·수량 조합)가 이미 DB에 있어 저장을 건너뜀 */
  duplicate_skipped?: boolean;
};

export type DefectAutoLotDefectItem = {
  name: string;
  count: number;
  ppm: number;
};

export type DefectAutoLotDefectRow = {
  lot_id: string;
  move_date: string;
  move_qty: number;
  defect_total: number;
  total_ppm: number;
  defects: DefectAutoLotDefectItem[];
};

/** POST /defect-auto/compute — 코드별 불량현황+작업일보 업로드 후 주·월 자동 집계·저장 */
export async function computeDefectAuto(
  defectFile: File,
  workFile: File,
): Promise<DefectAutoComputeResponse> {
  const fd = new FormData();
  fd.append("defect_file", defectFile);
  fd.append("work_file", workFile);
  const res = await fetch(`${API_BASE}/defect-auto/compute`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<DefectAutoComputeResponse>;
}

/** POST /defect-auto/reset — 출하·주·월 자동 집계·LOT PPM(서버 메모리) 일괄 초기화 */
export async function postDefectAutoReset(): Promise<{
  status: string;
  message: string;
  shipment_summary: DefectAutoShipmentSummary | null;
}> {
  const res = await fetch(`${API_BASE}/defect-auto/reset`, { method: "POST" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<{
    status: string;
    message: string;
    shipment_summary: DefectAutoShipmentSummary | null;
  }>;
}

/** GET /defect-auto/weekly — 저장된 주차별 자동 집계 */
export async function getDefectAutoWeekly(): Promise<{
  status: string;
  weekly: unknown[];
}> {
  const res = await fetch(`${API_BASE}/defect-auto/weekly`);
  if (!res.ok) throw new Error(`GET /defect-auto/weekly failed: ${res.status}`);
  return res.json() as Promise<{ status: string; weekly: unknown[] }>;
}

/** GET /defect-auto/monthly — 저장된 월별 자동 집계 */
export async function getDefectAutoMonthly(): Promise<{
  status: string;
  monthly: unknown[];
}> {
  const res = await fetch(`${API_BASE}/defect-auto/monthly`);
  if (!res.ok) throw new Error(`GET /defect-auto/monthly failed: ${res.status}`);
  return res.json() as Promise<{ status: string; monthly: unknown[] }>;
}

/** GET /defect-auto/shipment-summary — 저장된 출하 누적 요약 */
export async function getDefectAutoShipmentSummary(): Promise<{
  status: string;
  shipment_summary: DefectAutoShipmentSummary | null;
}> {
  const res = await fetch(`${API_BASE}/defect-auto/shipment-summary`);
  if (!res.ok) throw new Error(`GET /defect-auto/shipment-summary failed: ${res.status}`);
  return res.json() as Promise<{
    status: string;
    shipment_summary: DefectAutoShipmentSummary | null;
  }>;
}

export type DefectAutoShipmentMoveDateRow = {
  date: string;
  row_count: number;
  total_qty: number;
};

/** GET /defect-auto/shipment-move-dates — 저장된 출하의 이동일자별 건수·수량(최신일 먼저) */
export async function getDefectAutoShipmentMoveDates(): Promise<{
  status: string;
  move_dates: DefectAutoShipmentMoveDateRow[];
}> {
  const res = await fetch(`${API_BASE}/defect-auto/shipment-move-dates`);
  if (!res.ok) throw new Error(`GET /defect-auto/shipment-move-dates failed: ${res.status}`);
  return res.json() as Promise<{
    status: string;
    move_dates: DefectAutoShipmentMoveDateRow[];
  }>;
}

/** GET /defect-auto/lot-defects — 최근 자동계산 기준 LOT별 불량율(PPM) */
export async function getDefectAutoLotDefects(): Promise<{
  status: string;
  lot_defects: DefectAutoLotDefectRow[];
}> {
  const res = await fetch(`${API_BASE}/defect-auto/lot-defects`);
  if (!res.ok) throw new Error(`GET /defect-auto/lot-defects failed: ${res.status}`);
  return res.json() as Promise<{
    status: string;
    lot_defects: DefectAutoLotDefectRow[];
  }>;
}

export async function computeIlbo(params: {
  baseDate: string;
  todayFile: File;
  masterRows?: MasterRow[];
  planRows?: PlanRow[];
}): Promise<ComputeResponse> {
  const computeUrl = `${API_BASE}/compute`;
  console.log("[API] compute API URL:", computeUrl);

  const fd = new FormData();
  fd.append("base_date", params.baseDate);
  fd.append("today_file", params.todayFile);
  if (params.masterRows) {
    fd.append("master_rows_json", JSON.stringify(params.masterRows));
  }
  if (params.planRows) {
    fd.append("plan_rows_json", JSON.stringify(params.planRows));
  }

  const res = await fetch(computeUrl, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`서버 오류 (${res.status}): ${text || res.statusText}`);
  }
  return (await res.json()) as ComputeResponse;
}

