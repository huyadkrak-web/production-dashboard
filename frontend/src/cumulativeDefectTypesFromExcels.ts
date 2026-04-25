/**
 * 입력 카드의 작업일보 + 코드별 불량현황 엑셀만으로 누적불량유형(defectRows) 자동 생성.
 * 출하·공정불량 PPM 계산과 무관. 백엔드 defect/parser·calculator 규칙을 최대한 맞춤.
 */
import type { AccumulatedDefectSummaryRow, AssemblyDefectRow, MasterRow } from "./api";
import * as XLSX from "xlsx";

/** settings.py 기본값과 동일 (프론트 전용 파서) */
const WORK_COL_DATE = "작업종료일자";
const WORK_COL_PRODUCT = "제품군";
const WORK_COL_PROCESS_CODE = "공정ID";
const WORK_COL_PROCESS_NAME = "공정";
const WORK_COL_GOOD = "생산수량";
const WORK_COL_REJECT = "Reject";

const SHEET_WORK_TODAY = "작업일보";

const DEFECT_NAME_CANONICAL: Record<string, string> = {
  "chip crack": "Chip Crack",
  "pkg broken": "PKG Broken",
  "단자 scratch": "단자 Scratch",
  부풀음: "부풀음",
};

function normCell(v: unknown): string {
  return String(v ?? "")
    .trim()
    .replace(/\s+/gu, "")
    .toUpperCase();
}

function cleanLot(v: unknown): string {
  if (v == null || v === "") return "";
  let s = String(v).trim();
  if (s.endsWith(".0")) s = s.slice(0, -2);
  return s;
}

function normalizeDefectKey(name: unknown): string {
  if (name == null || String(name).trim() === "") return "기타";
  return String(name).trim().toLowerCase();
}

function displayDefectName(rawTrimmed: string, lowerKey: string): string {
  if (lowerKey === "기타") return "기타";
  const c = DEFECT_NAME_CANONICAL[lowerKey];
  if (c) return c;
  return rawTrimmed || lowerKey;
}

function toMatrix(ws: XLSX.WorkSheet): unknown[][] {
  return XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: "" }) as unknown[][];
}

function findWorkHeaderRow(matrix: unknown[][]): number | null {
  const anchors = new Set(
    [
      normCell(WORK_COL_PROCESS_CODE),
      normCell(WORK_COL_PROCESS_NAME),
      normCell(WORK_COL_DATE),
      normCell(WORK_COL_GOOD),
      normCell(WORK_COL_REJECT),
    ].filter(Boolean),
  );
  const max = Math.min(80, matrix.length);
  for (let i = 0; i < max; i++) {
    const row = matrix[i];
    if (!Array.isArray(row)) continue;
    const cells = new Set<string>();
    for (const v of row) {
      const s = String(v ?? "").trim();
      if (s && s.toLowerCase() !== "nan") cells.add(s);
    }
    let ok = true;
    for (const a of anchors) {
      let hit = false;
      for (const c of cells) {
        if (normCell(c) === a) {
          hit = true;
          break;
        }
      }
      if (!hit) {
        ok = false;
        break;
      }
    }
    if (ok) return i;
  }
  return null;
}

function headerCellIndex(headerRow: unknown[], predicate: (label: string) => boolean): number {
  if (!Array.isArray(headerRow)) return -1;
  for (let j = 0; j < headerRow.length; j++) {
    const label = String(headerRow[j] ?? "").trim();
    if (label && predicate(label)) return j;
  }
  return -1;
}

function isLotHeaderLabel(label: string): boolean {
  const n = normCell(label);
  return n === "LOTID" || n === "LOT" || n === "LOTNO" || n === "LOT번호";
}

function readWorkRows(matrix: unknown[][], headerRowIdx: number): WorkParsedRow[] {
  const headerRow = matrix[headerRowIdx] as unknown[];
  const idx = (name: string) =>
    headerCellIndex(headerRow, (lab) => normCell(lab) === normCell(name));

  const lotIdx = headerCellIndex(headerRow, isLotHeaderLabel);
  const procIdx = idx(WORK_COL_PROCESS_CODE);
  const prodMainIdx = idx(WORK_COL_PRODUCT);
  const prodAlt1 = headerCellIndex(headerRow, (lab) => normCell(lab) === normCell("품목명"));
  const prodAlt2 = headerCellIndex(headerRow, (lab) => normCell(lab) === normCell("품목ID"));

  if (lotIdx < 0 || procIdx < 0) {
    throw new Error("작업일보에서 Lot ID 또는 공정ID 열을 찾지 못했습니다.");
  }

  const out: WorkParsedRow[] = [];
  for (let r = headerRowIdx + 1; r < matrix.length; r++) {
    const row = matrix[r];
    if (!Array.isArray(row)) continue;
    const lot_id = cleanLot(row[lotIdx]);
    const process_code = String(row[procIdx] ?? "")
      .trim()
      .toUpperCase();
    if (!lot_id || !process_code) continue;

    let product = "";
    if (prodMainIdx >= 0) product = String(row[prodMainIdx] ?? "").trim();
    if (!product && prodAlt1 >= 0) product = String(row[prodAlt1] ?? "").trim();
    if (!product && prodAlt2 >= 0) product = String(row[prodAlt2] ?? "").trim();

    out.push({ lot_id, process_code, product });
  }
  return out;
}

type WorkParsedRow = { lot_id: string; process_code: string; product: string };

function resolveProductColumn(workRows: WorkParsedRow[]): void {
  const byLot = new Map<string, string>();
  for (const w of workRows) {
    if (w.product && !byLot.has(w.lot_id)) byLot.set(w.lot_id, w.product);
  }
  for (const w of workRows) {
    if (!w.product) w.product = byLot.get(w.lot_id) ?? "";
  }
}

function findDefectHeaderRow(matrix: unknown[][]): number | null {
  for (let i = 0; i < matrix.length; i++) {
    const row = matrix[i];
    if (!Array.isArray(row)) continue;
    for (const v of row) {
      if (v != null && normCell(v) === "부모LOTID") return i;
    }
  }
  return null;
}

type DefectParsedRow = {
  lot_id: string;
  process_code: string;
  defect_qty: number;
  defect_name_raw: string;
  item_product: string;
};

function readDefectRows(matrix: unknown[][], headerRowIdx: number): DefectParsedRow[] {
  const headerRow = matrix[headerRowIdx] as unknown[];
  const labels = headerRow.map((c) => String(c ?? "").trim());

  const col = (predicate: (lab: string) => boolean): number => {
    for (let j = 0; j < labels.length; j++) {
      if (predicate(labels[j])) return j;
    }
    return -1;
  };

  const lotCol = col((lab) => normCell(lab) === "부모LOTID");
  const qtyCol = col((lab) => lab === "불량수량");
  const nameCol = col((lab) => lab === "불량명");
  const procCol = col((lab) => normCell(lab) === normCell("공정ID"));
  const itemNameCol = col((lab) => lab === "품목명");
  const itemIdCol = col((lab) => lab === "품목ID");

  if (lotCol < 0 || qtyCol < 0 || nameCol < 0) {
    throw new Error("코드별 불량현황에서 부모 LOTID·불량수량·불량명 열을 찾지 못했습니다.");
  }

  const out: DefectParsedRow[] = [];
  for (let r = headerRowIdx + 1; r < matrix.length; r++) {
    const row = matrix[r];
    if (!Array.isArray(row)) continue;
    const lot_id = cleanLot(row[lotCol]);
    const process_code = procCol >= 0 ? String(row[procCol] ?? "").trim().toUpperCase() : "";
    const qtyRaw = row[qtyCol];
    const defect_qty = Number(qtyRaw);
    if (!Number.isFinite(defect_qty) || defect_qty <= 0) continue;
    const defect_name_raw = String(row[nameCol] ?? "").trim();
    let item_product = "";
    if (itemNameCol >= 0) item_product = String(row[itemNameCol] ?? "").trim();
    if (!item_product && itemIdCol >= 0) item_product = String(row[itemIdCol] ?? "").trim();

    if (!lot_id) continue;

    out.push({
      lot_id,
      process_code,
      defect_qty,
      defect_name_raw,
      item_product,
    });
  }
  return out;
}

function buildMasterCodeToGroup(masterRows: MasterRow[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const row of masterRows) {
    const code = String(row.process_code ?? "")
      .trim()
      .toUpperCase();
    const g = String(row.process_group ?? "").trim();
    if (code && g) m.set(code, g);
  }
  return m;
}

function effectiveAssemblyGroupKeys(rows: ReadonlyArray<AssemblyDefectRow>): string[] {
  const clone = rows.map((r) => ({ ...r }));
  let lastP = "";
  for (const r of clone) {
    const p = String(r.product ?? "").trim();
    if (p) lastP = p;
    (r as AssemblyDefectRow & { _effP?: string })._effP = lastP;
  }
  let nextP = "";
  for (let i = clone.length - 1; i >= 0; i--) {
    const p = String(clone[i].product ?? "").trim();
    if (p) nextP = p;
    const cur = clone[i] as AssemblyDefectRow & { _effP?: string };
    if (!cur._effP) cur._effP = nextP;
  }

  const keys: string[] = [];
  const seen = new Set<string>();
  for (const r of clone) {
    const p = String((r as AssemblyDefectRow & { _effP?: string })._effP ?? "").trim();
    const g = String(r.process_group ?? "").trim();
    const k = `${p}__${g}`;
    if (!p || !g || seen.has(k)) continue;
    seen.add(k);
    keys.push(k);
  }
  return keys;
}

export type BuildCumulativeDefectParams = {
  baseDate: string;
  workBytes: ArrayBuffer;
  defectBytes: ArrayBuffer;
  masterRows: MasterRow[];
  assemblyRows: ReadonlyArray<AssemblyDefectRow>;
};

/**
 * Lot 매칭: 작업일보 Lot ID = 코드별 불량현황 부모 LOTID.
 * 공정대분류: master의 공정ID(공정코드) → 공정대분류.
 */
export function buildCumulativeDefectSummaryRows(p: BuildCumulativeDefectParams): AccumulatedDefectSummaryRow[] {
  const wbWork = XLSX.read(new Uint8Array(p.workBytes), { type: "array" });
  const sheetWork =
    wbWork.SheetNames?.includes(SHEET_WORK_TODAY) === true
      ? SHEET_WORK_TODAY
      : wbWork.SheetNames?.[0] ?? "";
  if (!sheetWork) throw new Error("작업일보 엑셀에 시트가 없습니다.");
  const wsWork = wbWork.Sheets[sheetWork];
  if (!wsWork) throw new Error(`작업일보 시트 '${sheetWork}'를 열 수 없습니다.`);

  const matrixWork = toMatrix(wsWork);
  const hWork = findWorkHeaderRow(matrixWork);
  if (hWork == null) {
    throw new Error("작업일보에서 헤더 행(공정ID·공정·작업종료일자·생산수량·Reject)을 찾지 못했습니다.");
  }
  const workRows = readWorkRows(matrixWork, hWork);
  resolveProductColumn(workRows);

  const lotProcToProduct = new Map<string, string>();
  const lotToProducts = new Map<string, Set<string>>();
  for (const w of workRows) {
    const k = `${w.lot_id}__${w.process_code}`;
    if (w.product) lotProcToProduct.set(k, w.product);
    if (!lotToProducts.has(w.lot_id)) lotToProducts.set(w.lot_id, new Set());
    if (w.product) lotToProducts.get(w.lot_id)!.add(w.product);
  }

  const wbDef = XLSX.read(new Uint8Array(p.defectBytes), { type: "array" });
  const sheetDef = wbDef.SheetNames?.[0] ?? "";
  if (!sheetDef) throw new Error("코드별 불량현황 엑셀에 시트가 없습니다.");
  const wsDef = wbDef.Sheets[sheetDef];
  if (!wsDef) throw new Error("코드별 불량현황 시트를 열 수 없습니다.");
  const matrixDef = toMatrix(wsDef);
  const hDef = findDefectHeaderRow(matrixDef);
  if (hDef == null) {
    throw new Error("코드별 불량현황에서 '부모 LOTID' 헤더 행을 찾지 못했습니다.");
  }
  const defectRows = readDefectRows(matrixDef, hDef);

  const codeToGroup = buildMasterCodeToGroup(p.masterRows);

  type AggKey = string;
  const bucket = new Map<AggKey, Map<string, { qty: number; display: string }>>();

  const ensureBucket = (pgKey: string) => {
    if (!bucket.has(pgKey)) bucket.set(pgKey, new Map());
    return bucket.get(pgKey)!;
  };

  for (const d of defectRows) {
    const workHit = workRows.filter((w) => w.lot_id === d.lot_id);
    if (workHit.length === 0) continue;

    let processCode = d.process_code;
    if (!processCode) {
      const codes = [...new Set(workHit.map((w) => w.process_code))];
      if (codes.length === 1) processCode = codes[0] ?? "";
    }
    if (!processCode) {
      const fromRow = workHit.find((w) => w.process_code);
      processCode = fromRow?.process_code ?? "";
    }
    if (!processCode) continue;

    const process_group = codeToGroup.get(processCode.trim().toUpperCase()) ?? "";
    if (!process_group) continue;

    const pk = `${d.lot_id}__${processCode.trim().toUpperCase()}`;
    let product = lotProcToProduct.get(pk) ?? "";
    if (!product) {
      const set = lotToProducts.get(d.lot_id);
      if (set && set.size === 1) product = [...set][0] ?? "";
    }
    if (!product) product = d.item_product.trim();
    if (!product) continue;

    const lowerKey = normalizeDefectKey(d.defect_name_raw);
    const display = displayDefectName(d.defect_name_raw, lowerKey);
    const aggKey = `${product}__${process_group}`;
    const inner = ensureBucket(aggKey);
    const prev = inner.get(lowerKey);
    const addQty = d.defect_qty;
    if (prev) {
      inner.set(lowerKey, { qty: prev.qty + addQty, display: prev.display });
    } else {
      inner.set(lowerKey, { qty: addQty, display });
    }
  }

  const summaryByGroup = new Map<string, string>();
  for (const [aggKey, inner] of bucket) {
    const lines = [...inner.entries()]
      .map(([lk, { qty, display }]) => ({ lk, qty, display }))
      .filter((x) => x.qty > 0)
      .sort((a, b) => a.display.localeCompare(b.display, "ko"));
    if (lines.length === 0) continue;
    summaryByGroup.set(
      aggKey,
      lines.map((x) => `${x.display} : ${x.qty}`).join("\n"),
    );
  }

  const orderKeys = effectiveAssemblyGroupKeys(p.assemblyRows);
  const out: AccumulatedDefectSummaryRow[] = [];
  const used = new Set<string>();
  for (const k of orderKeys) {
    const text = summaryByGroup.get(k);
    if (!text) continue;
    const sep = k.indexOf("__");
    if (sep < 0) continue;
    const product = k.slice(0, sep);
    const process_group = k.slice(sep + 2);
    if (!product || !process_group) continue;
    out.push({
      date: p.baseDate,
      product,
      process_group,
      defect_summary: text,
    });
    used.add(k);
  }
  for (const [k, text] of summaryByGroup) {
    if (used.has(k)) continue;
    const sep = k.indexOf("__");
    if (sep < 0) continue;
    const product = k.slice(0, sep);
    const process_group = k.slice(sep + 2);
    if (!product || !process_group) continue;
    out.push({
      date: p.baseDate,
      product,
      process_group,
      defect_summary: text,
    });
  }

  return out;
}
