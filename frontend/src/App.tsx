import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { flushSync } from "react-dom";
import { ChartColumn, ChartLine, Cog, Gauge } from "lucide-react";
import DataTable from "./components/DataTable";
import { PdfReportIconBadge } from "./components/PdfReportIconBadge";
import WeeklyDefectPPM from "./components/WeeklyDefectPPM";
import MonthlyDefectPPM from "./components/MonthlyDefectPPM";
import DefectAutoUploadPanel from "./components/DefectAutoUploadPanel";
import LotDefectPpm from "./components/LotDefectPpm";
import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";
import * as XLSX from "xlsx";
import {
  API_BASE,
  AssemblyDefectRow,
  ComputeResponse,
  AccumulatedDefectSummaryRow,
  MasterRow,
  PlanRow,
  getMaster,
  getPlan,
  postMaster,
  ProductionProgressRow,
} from "./api";
import demoComputeRaw from "./demo/demoCompute.json";
import demoMaster from "./demo/demoMaster.json";
import { buildCumulativeDefectSummaryRows } from "./cumulativeDefectTypesFromExcels";
import demoPlan from "./demo/demoPlan.json";
import {
  PDF_CHART_SECTION_TITLE_MONTHLY_PPM,
  PDF_CHART_SECTION_TITLE_WEEKLY_PPM,
} from "./pdfChartSectionTitles";
import {
  buildWeeklyPdfLegendEntries,
  PDF_ONE_PAGE_ROOT_WIDTH_PX,
  type WeeklyPdfLegendEntry,
} from "./weeklyDefectPpmShared";

const DEMO_COMPUTE = demoComputeRaw as ComputeResponse;
const DEMO_PLAN_ROWS = demoPlan as PlanRow[];

/** PDF 1페이지 표 전용 조립행(화면 normalize 결과와 동일 형태) */
type AsmRowWithEffective = AssemblyDefectRow & {
  effectiveProduct: string;
  effectiveProcessGroup: string;
};

/**
 * PDF·대시보드 제품 셀렉트·제품별 저장 API 키에 공통 사용.
 * 원본 `product`(예: DIE, UDP2.0)는 표/JSON에는 그대로 두고, UI·저장 키만 이 값으로 맞춘다.
 */
function pdfProductDisplayForPdfTable(product: string): string {
  const s = String(product ?? "").trim();
  if (s === "UDP2.0") return "UDP";
  if (s === "DIE") return "132FBGA";
  return s;
}

function addUniqueDashboardProductKeys(set: Set<string>, raw: unknown) {
  const t = String(raw ?? "").trim();
  if (!t) return;
  set.add(pdfProductDisplayForPdfTable(t));
}

/** 생산 진척·조립 공정 불량 표(화면·PDF) 공정명 셀 표시 전용. 원본 process_name 미변경. */
const SOURCE_PROCESS_NAME_WB1_NAND = "W/B 1 (NAND+NAND)";

function productionProgressProcessNameDisplay(name: unknown): ReactNode {
  const s = String(name ?? "").trim();
  if (s === "D/A") {
    return "D/A 1차";
  }
  if (s === SOURCE_PROCESS_NAME_WB1_NAND) {
    return (
      <span style={{ whiteSpace: "nowrap", verticalAlign: "middle" }}>
        W/B{" "}
        <span style={{ fontSize: "0.78em" }}>(NAND+NAND)</span>
      </span>
    );
  }
  return s;
}

/** PDF 생산진척 병합용: 행별 표시 제품키(UDP2.0→UDP), 빈 셀은 엑셀식 연속 채움 */
function buildProgressPdfEffectiveDisplayProducts(
  rows: ReadonlyArray<ProductionProgressRow>,
): string[] {
  const raw = rows.map((r) => pdfProductDisplayForPdfTable(String(r.product ?? "").trim()));
  const out = [...raw];
  let last = "";
  for (let i = 0; i < out.length; i++) {
    if (out[i]) last = out[i];
    else out[i] = last;
  }
  let next = "";
  for (let i = out.length - 1; i >= 0; i--) {
    if (out[i]) next = out[i];
    else if (next) out[i] = next;
  }
  return out;
}

/**
 * 생산일보 계산 결과 기준「현재 제품」기본값.
 * 진척 표는 PDF와 동일한 엑셀식 제품 채움 후 첫 표시 키(UDP2.0→UDP, DIE→132FBGA)를 쓴다.
 */
function inferDefaultDashboardProductFromComputeData(data: ComputeResponse): string {
  const prog = data.생산진척현황 ?? [];
  if (prog.length > 0) {
    const eff = buildProgressPdfEffectiveDisplayProducts(prog);
    for (const k of eff) {
      const t = String(k ?? "").trim();
      if (t) return t;
    }
  }
  const asm = data.조립공정불량 ?? [];
  let lastRaw = "";
  for (const r of asm) {
    const raw = String(r.product ?? "").trim();
    if (raw) lastRaw = raw;
    if (lastRaw) {
      const disp = pdfProductDisplayForPdfTable(lastRaw);
      if (disp) return disp;
    }
  }
  return "";
}

/** 새 생산일보 계산 묶음인지 구분(이전 선택 UDP가 새 132FBGA 일보에 남지 않게) */
function computeDashboardProductSyncKey(data: ComputeResponse): string {
  const eff = buildProgressPdfEffectiveDisplayProducts(data.생산진척현황 ?? []);
  const head = eff.slice(0, 16).join("\x1f");
  return `${data.meta.base_date}\x00${eff.length}\x00${head}`;
}

function pdfNormProcessGroup(g: unknown): string {
  return String(g ?? "").trim();
}

function progressProductRowSpanAtEff(effectiveDisplayProduct: ReadonlyArray<string>, i: number): number {
  const pk = effectiveDisplayProduct[i];
  let n = 0;
  for (let j = i; j < effectiveDisplayProduct.length && effectiveDisplayProduct[j] === pk; j++) n++;
  return n;
}

function progressGroupRowSpanAtEff(
  rows: ReadonlyArray<ProductionProgressRow>,
  effectiveDisplayProduct: ReadonlyArray<string>,
  i: number,
): number {
  const pk = effectiveDisplayProduct[i];
  const g = pdfNormProcessGroup(rows[i].process_group);
  let n = 0;
  for (let j = i; j < rows.length; j++) {
    if (effectiveDisplayProduct[j] !== pk) break;
    if (pdfNormProcessGroup(rows[j].process_group) !== g) break;
    n++;
  }
  return n;
}

function asmEffectiveProductRowSpanAt(rows: ReadonlyArray<AsmRowWithEffective>, i: number): number {
  const p = rows[i].effectiveProduct;
  let n = 0;
  for (let j = i; j < rows.length && rows[j].effectiveProduct === p; j++) n++;
  return n;
}

function asmEffectiveGroupRowSpanAt(rows: ReadonlyArray<AsmRowWithEffective>, i: number): number {
  const p = rows[i].effectiveProduct;
  const g = rows[i].effectiveProcessGroup;
  let n = 0;
  for (
    let j = i;
    j < rows.length && rows[j].effectiveProduct === p && rows[j].effectiveProcessGroup === g;
    j++
  )
    n++;
  return n;
}

/** PDF 1페이지 표: 제품·공정대분류 병합 셀 정렬 */
const PDF_ONE_PAGE_TABLE_MERGED_TD: CSSProperties = {
  textAlign: "center",
  verticalAlign: "middle",
};

/** PDF 조립 공정 불량 표 본문: 숫자 열 우측 정렬 */
const PDF_ONE_PAGE_ASM_TD_RIGHT: CSSProperties = {
  textAlign: "right",
  verticalAlign: "middle",
};

/** PDF 조립 공정 불량: 제품·공정대분류 rowSpan 셀(가로·세로 중앙, 패딩은 전역 .table td와 동일) */
const PDF_ONE_PAGE_ASM_MERGED_TD: CSSProperties = {
  textAlign: "center",
  verticalAlign: "middle",
};

/** PDF 조립 공정 불량: 공정명(좌측) */
const PDF_ONE_PAGE_ASM_TD_LEFT: CSSProperties = {
  textAlign: "left",
  verticalAlign: "middle",
};

/** PDF 조립 공정 불량: 누적불량유형(좌측, 다줄은 상단 기준) */
const PDF_ONE_PAGE_ASM_TD_REMARK: CSSProperties = {
  textAlign: "left",
  verticalAlign: "top",
  wordBreak: "keep-all",
  overflowWrap: "break-word",
};

/** PDF 표 헤더/셀 가운데 정렬(공정대분류·PPM 등) */
const PDF_ONE_PAGE_TH_TD_CENTER: CSSProperties = {
  textAlign: "center",
  verticalAlign: "middle",
};

/** PDF: 공정대분류·PPM 헤더/셀 내부 — flex로 시각적 중앙 고정 */
const PDF_ONE_PAGE_FLEX_CENTER_INNER: CSSProperties = {
  display: "flex",
  width: "100%",
  justifyContent: "center",
  alignItems: "center",
  textAlign: "center",
};

/** PDF 1페이지 전용: 캡처 시 `pdf-export-mode`의 th !important를 덮어 헤더 대비·굵기 강화 */
const PDF_ONE_PAGE_INJECTED_CSS = `
[data-pdf-one-page-layout="true"].pdf-export-mode .card {
  border: 2px solid #94a3b8 !important;
  border-radius: 14px !important;
  box-sizing: border-box !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-section-title-panel {
  border-width: 1.5px !important;
  border-style: solid !important;
  border-color: #94a3b8 !important;
  border-radius: 10px !important;
  box-sizing: border-box !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .table.prod-progress-table,
[data-pdf-one-page-layout="true"].pdf-export-mode .table.asm-defect-table {
  border: 1px solid #64748b !important;
  box-sizing: border-box !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .prod-progress-table thead th,
[data-pdf-one-page-layout="true"].pdf-export-mode .asm-defect-table thead th {
  background: #0c2748 !important;
  color: #f8fafc !important;
  font-weight: 700 !important;
  font-size: 13.5px !important;
  padding: 10px 12px !important;
  border-color: #4d6d8f !important;
  border-bottom: 1px solid #6b93b8 !important;
  letter-spacing: 0.03em !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-one-page-section-title {
  font-weight: 700 !important;
  font-size: 21px !important;
  line-height: 1.28 !important;
  color: #0f172a !important;
  letter-spacing: -0.02em !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-one-page-chart-title {
  font-weight: 700 !important;
  font-size: 20px !important;
  line-height: 1.32 !important;
  color: #0f172a !important;
  letter-spacing: -0.02em !important;
  margin: 0 0 10px 0 !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-one-page-section-title .pdf-report-section-title-text,
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-one-page-chart-title .pdf-report-section-title-text {
  font-size: inherit !important;
  font-weight: inherit !important;
  line-height: inherit !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-one-page-card-header-tight {
  margin-bottom: 12px !important;
}
[data-pdf-one-page-layout="true"].pdf-export-mode .pdf-one-page-card-header-tight + .tableWrap {
  margin-top: 2px !important;
}
/* PDF 1페이지 생산·조립 표 본문만: 글자 크기 + 행 구분선 대비 */
[data-pdf-one-page-layout="true"].pdf-export-mode .prod-progress-table tbody td,
[data-pdf-one-page-layout="true"].pdf-export-mode .asm-defect-table tbody td {
  font-size: 14px !important;
  line-height: 1.45 !important;
  border-bottom: 1px solid #8b9caa !important;
}
/* PDF 조립 표만: rowSpan 행은 열마다 td 개수가 달라 nth-child 불가 — 패딩만 생산 표와 동일(10px 12px)로 고정, 정렬은 각 td 인라인 */
[data-pdf-one-page-layout="true"].pdf-export-mode .asm-defect-table tbody td {
  padding: 10px 12px !important;
  box-sizing: border-box !important;
}
`;

/** PDF 1페이지 표 섹션 제목(h2) — 전역 .pdf-export-mode와 함께 쓰는 보조 클래스용 */
const PDF_ONE_PAGE_SECTION_TITLE_CLASS = "pdf-one-page-section-title";

/** PDF 1페이지 차트 블록 제목 */
const PDF_ONE_PAGE_CHART_TITLE_CLASS = "pdf-one-page-chart-title";

const PDF_ONE_PAGE_CARD_HEADER_TIGHT_CLASS = "pdf-one-page-card-header-tight";

/**
 * PDF 생산 진척 현황 컬럼 폭(%), 합계 100.
 * 제품·공정명·특이사항 축소 → 공정대분류·숫자열 재분배(특이사항 = 조립 누적불량유형).
 */
const PDF_ONE_PAGE_PROD_COL_WIDTHS_PCT = [
  "3.55%",
  "7%",
  "14.2%",
  "10.32%",
  "10.32%",
  "10.32%",
  "10.32%",
  "10.32%",
  "10.32%",
  "13.33%",
] as const;

/**
 * PDF 조립 공정 불량 컬럼 폭(%), 합계 100.
 * 제품·공정명·누적불량유형 축소 → 공정대분류·불량 개수/PPM 4열 재분배.
 */
const PDF_ONE_PAGE_ASM_COL_WIDTHS_PCT = [
  "3.55%",
  "7%",
  "14.2%",
  "9.37%",
  "9.37%",
  "10.795%",
  "10.795%",
  "10.795%",
  "10.795%",
  "13.33%",
] as const;

const PDF_ONE_PAGE_TABLE_FIXED: CSSProperties = {
  width: "100%",
  tableLayout: "fixed",
};

/** 월간플랜 카드 상단: 좌(월 선택) / 우(업로드·파일명) */
const PLAN_MONTH_CARD_TOP: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  width: "100%",
  marginBottom: 12,
  gap: 16,
};
/** 입력 카드 파일 행: 라벨(좌) + 파일 input 래퍼(우, 폭 약 65%) */
const INPUT_FILE_ROW: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  width: "100%",
  gap: 12,
};
const INPUT_FILE_INPUT_WRAP: CSSProperties = {
  width: "68%",
  maxWidth: "28rem",
  minWidth: "9rem",
  flexShrink: 0,
};
/** PDF 전용 1페이지 레이아웃 — 화면 밖 고정, 이후 html2canvas 대상 */
const PDF_ONE_PAGE_ROOT_STYLE: CSSProperties = {
  position: "fixed",
  left: "-9999px",
  top: 0,
  width: 1320,
  maxWidth: "none",
  margin: 0,
  padding: 0,
  boxSizing: "border-box",
  pointerEvents: "none",
  overflow: "hidden",
  zIndex: -1,
  backgroundColor: "#ffffff",
};

const PDF_ONE_PAGE_INNER_STYLE: CSSProperties = {
  width: "100%",
  maxWidth: "none",
  margin: "0 auto",
  /* 좌우 12px→8px: 카드 가용 폭 소폭 확대(상하 유지) */
  padding: "8px 8px",
  boxSizing: "border-box",
};

const PDF_ONE_PAGE_CARD_SECTION_STYLE: CSSProperties = {
  marginTop: 12,
  width: "100%",
  minWidth: 0,
  maxWidth: "none",
  boxSizing: "border-box",
};

const PDF_ONE_PAGE_CHART_PLACEHOLDER_STYLE: CSSProperties = {
  width: "100%",
  minWidth: 0,
  minHeight: 220,
  marginTop: 8,
  border: "1px dashed #cbd5e1",
  borderRadius: 4,
  backgroundColor: "#f8fafc",
  display: "flex",
  alignItems: "stretch",
  justifyContent: "center",
  color: "#64748b",
  fontSize: 13,
  boxSizing: "border-box",
};

const PDF_ONE_PAGE_MANUAL_LEGEND_WRAP: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  justifyContent: "center",
  alignItems: "center",
  gap: "8px 16px",
  width: "100%",
  maxWidth: "100%",
  padding: "10px 10px 8px",
  marginTop: 4,
  fontSize: 12,
  fontWeight: 600,
  color: "#0f172a",
  lineHeight: 1.35,
  borderTop: "1px solid #e2e8f0",
  backgroundColor: "#ffffff",
  boxSizing: "border-box",
};

const PDF_ONE_PAGE_TABLE_HOST_STYLE: CSSProperties = {
  width: "100%",
  minWidth: 0,
  maxWidth: "none",
  boxSizing: "border-box",
};

/** 1페이지 PDF 차트 SVG→PNG 배율 (html2canvas scale와 분리; 고 DPI 디바이스에서 상향 가능) */
function pdfEffectiveSvgRasterScale(): number {
  if (typeof window === "undefined") return 3;
  const dpr = Number(window.devicePixelRatio) || 2;
  return Math.min(4, Math.max(3, Math.ceil(dpr * 1.25)));
}

/** html2canvas scale — 디바이스 픽셀 비율 반영, 선명도 우선(문서 용량 증가 허용) */
function pdfEffectiveHtml2canvasScale(): number {
  if (typeof window === "undefined") return 3;
  const dpr = Number(window.devicePixelRatio) || 2;
  return Math.min(3.5, Math.max(2.75, Math.ceil(dpr * 1.35)));
}

async function pdfReflowChartsOnce(): Promise<void> {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("resize"));
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
}

/** jsPDF에 넣을 래스터 크기·위치(mm) — 1·2페이지 동일 규칙(가로 우선, 세로 넘치면 가로 축소·가운데) */
function defectPpmPdfRasterDestMm(
  canvasPxW: number,
  canvasPxH: number,
  pageWmm: number,
  pageHmm: number,
): { imgWidthMm: number; imgHeightMm: number; xMm: number; yMm: number } {
  let imgWidthMm = pageWmm;
  let imgHeightMm = (canvasPxH * imgWidthMm) / canvasPxW;
  if (imgHeightMm > pageHmm) {
    imgHeightMm = pageHmm;
    imgWidthMm = (canvasPxW * imgHeightMm) / canvasPxH;
  }
  return {
    imgWidthMm,
    imgHeightMm,
    xMm: (pageWmm - imgWidthMm) / 2,
    yMm: 2,
  };
}

/** 2페이지 LOT: 1페이지에 실린 래스터와 동일 이상으로 가로가 커지지 않게(양옆 여백 동일감) */
function defectPpmPdfRasterDestMmCappedToMaxWidth(
  canvasPxW: number,
  canvasPxH: number,
  pageWmm: number,
  pageHmm: number,
  maxWidthMm: number,
): { imgWidthMm: number; imgHeightMm: number; xMm: number; yMm: number } {
  let { imgWidthMm, imgHeightMm, xMm, yMm } = defectPpmPdfRasterDestMm(
    canvasPxW,
    canvasPxH,
    pageWmm,
    pageHmm,
  );
  if (imgWidthMm <= maxWidthMm) {
    return { imgWidthMm, imgHeightMm, xMm, yMm };
  }
  imgWidthMm = maxWidthMm;
  imgHeightMm = (canvasPxH * imgWidthMm) / canvasPxW;
  if (imgHeightMm > pageHmm) {
    imgHeightMm = pageHmm;
    imgWidthMm = (canvasPxW * imgHeightMm) / canvasPxH;
  }
  xMm = (pageWmm - imgWidthMm) / 2;
  return { imgWidthMm, imgHeightMm, xMm, yMm };
}

function selectLargestSvgFromRoot(root: HTMLElement | null) {
  if (!root) return null;
  const list = Array.from(root.querySelectorAll("svg"));
  let bestIdx = -1;
  let bestArea = -1;
  let bestEl: SVGSVGElement | null = null;
  for (let index = 0; index < list.length; index++) {
    const svg = list[index] as SVGSVGElement;
    let cw = svg.clientWidth;
    let ch = svg.clientHeight;
    if (cw <= 0 || ch <= 0) {
      const br = svg.getBoundingClientRect();
      cw = br.width;
      ch = br.height;
    }
    const area = cw * ch;
    if (area > bestArea) {
      bestArea = area;
      bestIdx = index;
      bestEl = svg;
    }
  }
  if (!bestEl || bestIdx < 0 || bestArea <= 0) return null;
  let w = bestEl.clientWidth;
  let h = bestEl.clientHeight;
  if (w <= 0 || h <= 0) {
    const br = bestEl.getBoundingClientRect();
    w = br.width;
    h = br.height;
  }
  if (w <= 0 || h <= 0) return null;
  return { svg: bestEl, index: bestIdx, width: w, height: h };
}

/** data: URL 등으로 `<img>`가 디코드된 뒤에만 html2canvas를 호출하기 위한 대기 */
async function awaitLotPdfChartImgReady(img: HTMLImageElement, dataUrl: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("LOT chart <img> load failed"));
    img.src = dataUrl;
    if (img.complete && img.naturalWidth > 0) {
      queueMicrotask(() => resolve());
    }
  });
  if (typeof img.decode === "function") {
    try {
      await img.decode();
    } catch {
      /* ignore */
    }
  }
  await new Promise<void>((r) => requestAnimationFrame(() => r()));
}

function svgElementToPngDataUrlForOnePage(
  svg: SVGSVGElement,
  cssW: number,
  cssH: number,
  rasterScale: number,
) {
  return new Promise<string>((resolve, reject) => {
    const clone = svg.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(cssW));
    clone.setAttribute("height", String(cssH));
    const serialized = new XMLSerializer().serializeToString(clone);
    const dataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serialized)}`;
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(cssW * rasterScale));
        canvas.height = Math.max(1, Math.round(cssH * rasterScale));
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("canvas 2d context 없음"));
          return;
        }
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/png"));
      } catch (e) {
        reject(e);
      }
    };
    img.onerror = () => reject(new Error("SVG 이미지 로드 실패"));
    img.src = dataUrl;
  });
}

function pickMonthlyPlanSourceRowsForCompute(
  hasUploadWorksheet: boolean,
  screenPlanRows: PlanRow[],
  monthKey: string,
  serverPlanRows: PlanRow[],
): {
  planSourceRows: PlanRow[];
  usingUploaded: boolean;
  usingServerPlan: boolean;
  usingDemo: boolean;
} {
  if (hasUploadWorksheet) {
    return {
      planSourceRows: screenPlanRows,
      usingUploaded: true,
      usingServerPlan: false,
      usingDemo: false,
    };
  }
  const fromScreen = screenPlanRows.filter((r) => r.month === monthKey);
  if (fromScreen.length > 0) {
    return {
      planSourceRows: fromScreen,
      usingUploaded: false,
      usingServerPlan: false,
      usingDemo: false,
    };
  }
  const fromServer = serverPlanRows.filter((r) => r.month === monthKey);
  if (fromServer.length > 0) {
    return {
      planSourceRows: fromServer,
      usingUploaded: false,
      usingServerPlan: true,
      usingDemo: false,
    };
  }
  const forMonthDemo = DEMO_PLAN_ROWS.filter((r) => r.month === monthKey);
  if (forMonthDemo.length > 0) {
    return {
      planSourceRows: forMonthDemo,
      usingUploaded: false,
      usingServerPlan: false,
      usingDemo: true,
    };
  }
  return {
    planSourceRows: [...DEMO_PLAN_ROWS],
    usingUploaded: false,
    usingServerPlan: false,
    usingDemo: true,
  };
}

/**
 * 조립공정불량 행을 데모 JSON·이전 계산 결과와 참조를 공유하지 않도록 복사.
 * (얕은 배열 복사만 하면 행 객체 변이 시 재계산마다 누적값이 커질 수 있음)
 */
function cloneAssemblyDefectRows(rows: ReadonlyArray<AssemblyDefectRow>): AssemblyDefectRow[] {
  return rows.map((r) => ({ ...r }));
}

function cloneProductionProgressRows(rows: ReadonlyArray<ProductionProgressRow>): ProductionProgressRow[] {
  return rows.map((r) => ({ ...r }));
}

function buildPlanByProcessCode(rows: PlanRow[]): Map<string, { month_plan: number; prev_day_plan: number }> {
  const m = new Map<string, { month_plan: number; prev_day_plan: number }>();
  for (const r of rows) {
    const c = String(r.process_code ?? "").trim();
    if (!c) continue;
    m.set(c, { month_plan: r.month_plan, prev_day_plan: r.prev_day_plan });
  }
  return m;
}

function computeProgressPercent(actual: unknown, plan: unknown): number {
  const a = Number(actual);
  const p = Number(plan);
  if (!Number.isFinite(a) || !Number.isFinite(p) || p <= 0) return 0;
  return (a / p) * 100;
}

/** 기준정보로 공정명·그룹·제품 → 공정코드 매칭 후 월간플랜 수치만 덮어씀 */
function applyPlanToProgressRows(
  rows: ProductionProgressRow[],
  planByCode: Map<string, { month_plan: number; prev_day_plan: number }>,
  masters: MasterRow[],
): ProductionProgressRow[] {
  if (planByCode.size === 0) {
    return rows.map((r) => ({
      ...r,
      progress_day: computeProgressPercent(r.cumulative_actual, r.prev_day_plan),
      progress_month: computeProgressPercent(r.cumulative_actual, r.month_plan),
      remark: "",
    }));
  }
  return rows.map((row) => {
    const p = String(row.product ?? "").trim();
    const g = String(row.process_group ?? "").trim();
    const n = String(row.process_name ?? "").trim();
    const master = masters.find(
      (m) =>
        String(m.process_group ?? "").trim() === g &&
        String(m.process_name ?? "").trim() === n &&
        String(m.product ?? "").trim() === p,
    );
    if (!master) {
      return {
        ...row,
        progress_day: computeProgressPercent(row.cumulative_actual, row.prev_day_plan),
        progress_month: computeProgressPercent(row.cumulative_actual, row.month_plan),
        remark: "",
      };
    }
    const code = String(master.process_code ?? "").trim();
    const pl = code ? planByCode.get(code) : undefined;
    if (!pl) {
      return {
        ...row,
        progress_day: computeProgressPercent(row.cumulative_actual, row.prev_day_plan),
        progress_month: computeProgressPercent(row.cumulative_actual, row.month_plan),
        remark: "",
      };
    }
    return {
      ...row,
      month_plan: pl.month_plan,
      prev_day_plan: pl.prev_day_plan,
      progress_day: computeProgressPercent(row.cumulative_actual, pl.prev_day_plan),
      progress_month: computeProgressPercent(row.cumulative_actual, pl.month_plan),
      remark: "",
    };
  });
}

function prevCalendarDay(yyyyMmDd: string): string {
  const [y, m, d] = yyyyMmDd.split("-").map((x) => Number(x));
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) {
    return DEMO_COMPUTE.meta.prev_date;
  }
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() - 1);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function fmtNum(v: unknown) {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

/**
 * 월간플랜 카드 숫자 표시 전용(월계획/기준일계획 공용).
 * 원본 숫자는 유지하고, 표시 시점에만 부동소수점 찌꺼기를 정리한다.
 */
function formatMonthlyPlanDisplay(n: number): string {
  const raw = Number(n);
  if (!Number.isFinite(raw)) return "";
  const neg = raw < 0;
  let abs = Math.abs(raw);
  const rounded = Math.round(abs);
  // 정수에 "아주 가깝게" 붙어있는 부동소수점 찌꺼기 제거용
  const intLike = Math.abs(abs - rounded) < 1e-8 * Math.max(1, abs);
  if (intLike) abs = rounded;
  else abs = Number.parseFloat(abs.toPrecision(12));
  let s = abs.toString();
  if (/[eE]/u.test(s)) {
    s = abs.toFixed(24).replace(/\.?0+$/u, "");
  }
  const [intPart, fracRaw] = s.split(".");
  const groupedInt = (intPart ?? "").replace(/\B(?=(\d{3})+(?!\d))/gu, ",");
  if (fracRaw === undefined) {
    return neg ? `-${groupedInt}` : groupedInt;
  }
  const frac = fracRaw.replace(/0+$/u, "");
  if (frac === "") {
    return neg ? `-${groupedInt}` : groupedInt;
  }
  return neg ? `-${groupedInt}.${frac}` : `${groupedInt}.${frac}`;
}

function fmtPct(v: unknown) {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "";
  return `${n.toFixed(1)}%`;
}

/**
 * 달성율(진척율) 색상: 비교 전 `Number` 변환, 소수 그대로 비교(반올림·parseInt·문자열 비교 금지).
 * `>= 90` 녹, `>= 80` 노랑, 그 외 빨강.
 */
function achievementRateTextColorFromRaw(value: unknown): string {
  const raw = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(raw)) return "#334155";
  if (raw >= 90) return "#16a34a";
  if (raw >= 80) return "#ca8a04";
  return "#dc2626";
}

/** 화면 표: 표시는 `toFixed(1)` 문자열, 색상 판단은 동일 raw 숫자로만 수행 */
function fmtPctAchievementColored(v: unknown): ReactNode {
  const raw = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(raw)) return "";
  const display = `${raw.toFixed(1)}%`;
  return (
    <span style={{ color: achievementRateTextColorFromRaw(raw) }}>{display}</span>
  );
}

function fmtPpm(v: unknown) {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "";
  return Math.round(n).toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}

/** 캘린더 연·월·일 → yyyy-mm-dd (로컬 기준일·엑셀 헤더와 비교용) */
function formatISODateYmd(y: number, m: number, d: number): string {
  const yy = String(y).padStart(4, "0");
  const mm = String(m).padStart(2, "0");
  const dd = String(d).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

/**
 * 엑셀/SheetJS 셀 값 → yyyy-mm-dd.
 * HTML date input(로컬 날짜)과 맞추기 위해 JS Date는 UTC가 아닌 로컬 연·월·일을 사용합니다.
 */
function normalizeExcelDateToISODate(v: unknown): string | null {
  if (v === null || v === undefined) return null;

  if (v instanceof Date) {
    if (Number.isNaN(v.getTime())) return null;
    return formatISODateYmd(v.getFullYear(), v.getMonth() + 1, v.getDate());
  }

  if (typeof v === "number" && Number.isFinite(v)) {
    const whole = Math.floor(v);
    const dc = (XLSX as any)?.SSF?.parse_date_code?.(whole);
    if (!dc || !Number.isFinite(dc.y) || !Number.isFinite(dc.m) || !Number.isFinite(dc.d)) {
      return null;
    }
    return formatISODateYmd(dc.y, dc.m, dc.d);
  }

  const s = String(v).trim();
  if (!s) return null;

  const isoMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) {
    const [, yy, mm, dd] = isoMatch;
    return `${yy}-${mm}-${dd}`;
  }

  const slashMatch = s.match(/^(\d{4})[\/.-](\d{1,2})[\/.-](\d{1,2})$/);
  if (slashMatch) {
    const y = Number(slashMatch[1]);
    const mo = Number(slashMatch[2]);
    const d = Number(slashMatch[3]);
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31 && Number.isFinite(y)) {
      return formatISODateYmd(y, mo, d);
    }
  }

  if (/^-?\d+(\.\d+)?$/u.test(s)) {
    const n = Number(s);
    if (Number.isFinite(n)) {
      const whole = Math.floor(n);
      const dc = (XLSX as any)?.SSF?.parse_date_code?.(whole);
      if (dc && Number.isFinite(dc.y) && Number.isFinite(dc.m) && Number.isFinite(dc.d)) {
        return formatISODateYmd(dc.y, dc.m, dc.d);
      }
    }
  }

  const dt = new Date(s);
  if (Number.isNaN(dt.getTime())) return null;
  return formatISODateYmd(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
}

/**
 * 월간플랜 수량 파싱에 간접 사용(readPlanWorksheetQuantityCell 경유).
 * 점검: /1000, *0.001, Math.round/floor/ceil, toFixed, fmtNum/toLocaleString(표시용) 없음 — 쉼표 제거 후 Number()만.
 */
function excelCellToNumber(v: unknown): number {
  if (v === null || v === undefined || v === "") return 0;
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const str = String(v).trim().replace(/,/gu, "");
  if (!str) return 0;
  const n = Number(str);
  return Number.isFinite(n) ? n : 0;
}

/**
 * 월간플랜 수량 셀. SheetJS가 내부 v를 축소 실수(예: 4.8)로 두고 w에 정수(4,800)만 줄 때
 * v×1000/100 등과 w가 일치하면 w(표시값)를 채택해 천·백 단위 축소를 되돌림. /1000·round 없음.
 */
function readPlanWorksheetQuantityCell(cell: any): number {
  if (!cell) return 0;

  const wNum =
    cell.w != null && cell.w !== "" ? excelCellToNumber(cell.w) : NaN;
  const vNum = typeof cell.v === "number" && Number.isFinite(cell.v) ? cell.v : NaN;
  const vParsed =
    cell.v != null && cell.v !== "" && typeof cell.v !== "number"
      ? excelCellToNumber(cell.v)
      : NaN;

  if (Number.isFinite(vNum) && vNum !== 0) {
    if (Number.isFinite(wNum) && wNum > 0 && Math.abs(wNum % 1) < 1e-9) {
      for (const factor of [1000, 100, 10000, 1000000]) {
        if (Math.abs(vNum * factor - wNum) < 0.51) return wNum;
      }
    }
    return vNum;
  }

  if (vNum === 0 && Number.isFinite(wNum)) return wNum;

  if (Number.isFinite(vParsed)) return vParsed;
  if (Number.isFinite(wNum)) return wNum;
  return 0;
}

/** 시트 셀: 값·표시문자 모두에서 날짜 후보 파싱 (헤더가 w에만 있을 때 대비) */
function parseIsoDateFromSheetCell(cell: any): string | null {
  if (!cell) return null;
  return (
    normalizeExcelDateToISODate(cell.v) ?? normalizeExcelDateToISODate(cell.w) ?? null
  );
}

function buildDateColumnsForHeaderRow(
  sheet: Record<string, any>,
  range: ReturnType<typeof XLSX.utils.decode_range>,
  dateHeaderRowIdx: number,
  dateStartColIdx: number,
  baseMonthKey: string,
): Array<{ colIdx: number; iso: string; inBaseMonth: boolean }> {
  const out: Array<{ colIdx: number; iso: string; inBaseMonth: boolean }> = [];
  for (let c = dateStartColIdx; c <= range.e.c; c++) {
    const addr = XLSX.utils.encode_cell({ r: dateHeaderRowIdx, c });
    const iso = parseIsoDateFromSheetCell(sheet[addr]);
    if (!iso) continue;
    out.push({
      colIdx: c,
      iso,
      inBaseMonth: iso.startsWith(baseMonthKey),
    });
  }
  return out;
}

/** C열~에서 날짜 헤더가 있는 행을 찾음. 기준일 열이 잡히는 행을 최우선, 동점이면 Excel 2행(인덱스 1)에 가까운 행 */
function pickMonthlyPlanDateHeaderRow(
  sheet: Record<string, any>,
  range: ReturnType<typeof XLSX.utils.decode_range>,
  dateStartColIdx: number,
  baseMonthKey: string,
  baseDate: string,
): { dateHeaderRowIdx: number; dateCols: Array<{ colIdx: number; iso: string; inBaseMonth: boolean }> } {
  const maxTryR = Math.min(4, range.e.r);
  let bestRow = 1;
  let bestCols: Array<{ colIdx: number; iso: string; inBaseMonth: boolean }> = [];
  let bestPrimary = -1;
  let bestSecondary = Number.NEGATIVE_INFINITY;

  for (let tryR = 0; tryR <= maxTryR; tryR++) {
    const cols = buildDateColumnsForHeaderRow(sheet, range, tryR, dateStartColIdx, baseMonthKey);
    const hasBaseDateCol = cols.some((d) => d.iso === baseDate);
    // 참고: 1_000_000은 "기준일 열 있는 헤더 행" 선택 점수용이며 월간플랜 수량 값과 무관
    const primary = (hasBaseDateCol ? 1_000_000 : 0) + cols.length;
    const secondary = -Math.abs(tryR - 1);
    if (
      primary > bestPrimary ||
      (primary === bestPrimary && secondary > bestSecondary)
    ) {
      bestPrimary = primary;
      bestSecondary = secondary;
      bestRow = tryR;
      bestCols = cols;
    }
  }

  return { dateHeaderRowIdx: bestRow, dateCols: bestCols };
}

function isSummaryRowKey(s: string) {
  return /(합산|합계|총계|소계|subtotal|sub[- ]?total|grand\s*total|total)\b/iu.test(s);
}

/** PDF 1페이지 핵심 숫자 열(진척율·PPM): 본문 td 대비 +1px·굵게, 색은 글자만 */
const PDF_ONE_PAGE_KEY_METRIC_TD_TEXT: CSSProperties = {
  fontWeight: 700,
  fontSize: 15,
  lineHeight: 1.45,
};

/**
 * PPM: 낮을수록 양호. 0~100 구간을 (100−ppm)으로 스코어화해 달성율과 동일 3단 색 규칙 적용.
 * ppm>100은 스코어 0으로 취급(적색 계열).
 */
function pdfKeyMetricTextColorForPpm(ppm: number | null): string {
  if (ppm === null || !Number.isFinite(ppm)) return "#334155";
  if (ppm < 0) return "#334155";
  const rawPpm = Number(ppm);
  const score = 100 - Math.min(rawPpm, 100);
  return achievementRateTextColorFromRaw(score);
}

function pdfKeyMetricTdStyleForProgress(value: unknown): CSSProperties {
  return {
    ...PDF_ONE_PAGE_KEY_METRIC_TD_TEXT,
    color: achievementRateTextColorFromRaw(value),
  };
}

function pdfKeyMetricTdStyleForPpm(value: unknown): CSSProperties {
  const n = typeof value === "number" ? value : Number(value);
  const ppm = Number.isFinite(n) ? n : null;
  return {
    ...PDF_ONE_PAGE_KEY_METRIC_TD_TEXT,
    color: pdfKeyMetricTextColorForPpm(ppm),
  };
}

/** 생산 진척 특이사항 상태 점: 실적누적(`cumulative_actual`) > 0 일 때만 표시 */
function shouldShowProgressRemarkStatusDot(cumulativeActual: unknown): boolean {
  const n = typeof cumulativeActual === "number" ? cumulativeActual : Number(cumulativeActual);
  return Number.isFinite(n) && n > 0;
}

/**
 * PDF 생산 진척 표 · 특이사항 열: 진척율(일) 기준 단일 상태 점(텍스트 없음).
 * 비교는 `Number` 변환 후 소수 그대로 — `achievementRateTextColorFromRaw`와 동일 밴드(90/80).
 * 호출부에서 `shouldShowProgressRemarkStatusDot(cumulative_actual)` 가 true 일 때만 사용.
 */
function pdfProgressDayRemarkDotStyle(progressDay: unknown): CSSProperties {
  const raw = typeof progressDay === "number" ? progressDay : Number(progressDay);
  const dot: CSSProperties = {
    display: "block",
    width: 11,
    height: 11,
    borderRadius: "50%",
    margin: "0 auto",
    flexShrink: 0,
    boxSizing: "border-box",
  };
  if (!Number.isFinite(raw)) {
    return { ...dot, backgroundColor: "#94a3b8" };
  }
  return { ...dot, backgroundColor: achievementRateTextColorFromRaw(raw) };
}

function isLikelyProcessCode(s: string) {
  const cleaned = s.replace(/\s+/gu, "");
  if (!cleaned) return false;
  if (cleaned.length < 3) return false;
  if (isSummaryRowKey(cleaned)) return false;
  const hasLetter = /[A-Za-z]/u.test(cleaned);
  const hasDigit = /\d/u.test(cleaned);
  return hasLetter && hasDigit;
}

/** 월간플랜 수치 추적용(존재하는 행만 로그). */
const MONTHLY_PLAN_TRACE_CODES = new Set(["FCD01", "FDA01", "FWB01"]);

function processGroupSortRank(processGroup: string): number {
  const g = String(processGroup ?? "").trim();
  if (g === "Front") return 0;
  if (g === "Back End") return 1;
  return 2;
}

/**
 * 월간플랜 시트(1번째 시트 worksheet): A열 공정코드(3행~), 날짜 헤더 행·C열~, 동일 열 수량.
 * 공정코드별로 월계획(해당 월 날짜 열 합)·기준일계획(같은 달에서 기준일까지 일별 계획 누적합)을 반환.
 * masterRows가 있으면 Front → Back End → 기타 순, 그룹 안에서는 시트 첫 등장 순 유지.
 */
function buildPlanRowsFromMonthlyWorksheet(
  worksheet: unknown,
  baseDate: string,
  masterRowsForOrder: MasterRow[],
): { rows: PlanRow[]; note: string } {
  const sheet = worksheet as Record<string, any>;
  const ref = sheet["!ref"] as string | undefined;
  if (!ref) {
    return { rows: [], note: "시트 범위를 읽을 수 없습니다." };
  }

  const range = XLSX.utils.decode_range(ref);
  const baseMonthKey = baseDate.slice(0, 7);

  const dateStartColIdx = 2;
  const processCodeColIdx = 0;

  const { dateHeaderRowIdx, dateCols } = pickMonthlyPlanDateHeaderRow(
    sheet,
    range,
    dateStartColIdx,
    baseMonthKey,
    baseDate,
  );

  const processStartRowIdx = Math.max(dateHeaderRowIdx + 1, 2);

  const baseDateCol = dateCols.find((d) => d.iso === baseDate);
  if (baseDateCol) {
    const colLetter = XLSX.utils.encode_col(baseDateCol.colIdx);
    const sampleBaseDayQty: number[] = [];
    for (let r = processStartRowIdx; r <= range.e.r && sampleBaseDayQty.length < 5; r++) {
      const codeAddr = XLSX.utils.encode_cell({ r, c: processCodeColIdx });
      const rawCode = String(sheet[codeAddr]?.v ?? sheet[codeAddr]?.w ?? "").trim();
      if (!rawCode) continue;
      const code = rawCode.replace(/\s+/gu, "");
      if (!isLikelyProcessCode(code)) continue;
      const qtyAddr = XLSX.utils.encode_cell({ r, c: baseDateCol.colIdx });
      sampleBaseDayQty.push(readPlanWorksheetQuantityCell(sheet[qtyAddr]));
    }
    console.log("월간플랜 기준일 매칭", {
      baseDate,
      headerRow: dateHeaderRowIdx + 1,
      dataStartRow: processStartRowIdx + 1,
      column: colLetter,
      headerCell: `${colLetter}${dateHeaderRowIdx + 1}`,
      sampleBaseDayQty,
    });
    const probeAddr = XLSX.utils.encode_cell({ r: processStartRowIdx, c: baseDateCol.colIdx });
    if (sheet[probeAddr] == null) {
      console.warn("월간플랜: 기준일 열 헤더는 있으나 첫 데이터 행 셀이 비어 있습니다.", {
        probeAddress: `${colLetter}${processStartRowIdx + 1}`,
      });
    }
  } else {
    console.warn("월간플랜: 기준일 열 없음 — 기준일계획이 0일 수 있습니다.", {
      baseDate,
      headerRowTried: dateHeaderRowIdx + 1,
      dateHeaderSamples: dateCols.slice(0, 10).map((d) => ({
        iso: d.iso,
        col: XLSX.utils.encode_col(d.colIdx),
      })),
    });
  }

  const aggByProcessCode = new Map<string, { baseDatePlan: number; monthPlan: number }>();
  const processCodeSheetOrder = new Map<string, number>();
  let sheetOrderSeq = 0;

  for (let r = processStartRowIdx; r <= range.e.r; r++) {
    const addr = XLSX.utils.encode_cell({ r, c: processCodeColIdx });
    const cell = sheet[addr];
    const rawVal = cell?.v ?? cell?.w ?? "";
    const raw = String(rawVal ?? "").trim();
    if (!raw) continue;

    const processCode = raw.replace(/\s+/gu, "");
    if (!isLikelyProcessCode(processCode)) continue;

    let baseDatePlan = 0;
    let monthPlan = 0;
    let anyQty = false;

    for (const dc of dateCols) {
      const qtyAddr = XLSX.utils.encode_cell({ r, c: dc.colIdx });
      const qty = readPlanWorksheetQuantityCell(sheet[qtyAddr]);

      if (qty !== 0) anyQty = true;
      if (dc.inBaseMonth && dc.iso <= baseDate) baseDatePlan += qty;
      if (dc.inBaseMonth) monthPlan += qty;
    }

    if (!anyQty) continue;

    const existing = aggByProcessCode.get(processCode);
    if (!existing) {
      processCodeSheetOrder.set(processCode, sheetOrderSeq++);
      aggByProcessCode.set(processCode, { baseDatePlan, monthPlan });
    } else {
      existing.baseDatePlan += baseDatePlan;
      existing.monthPlan += monthPlan;
    }
  }

  const codeToGroup = new Map<string, string>();
  for (const m of masterRowsForOrder) {
    if (m.is_active === false) continue;
    const c = String(m.process_code ?? "").trim();
    if (!c) continue;
    if (!codeToGroup.has(c)) codeToGroup.set(c, String(m.process_group ?? "").trim());
  }
  const useGroupSort = codeToGroup.size > 0;

  /** 시트 셀 값이 천 단위(예: 4.8 → 실제 4800)로 들어오는 경우 state에는 ×1000만 적용(반올림·포맷 없음). */
  const monthlyPlanSheetUnitScale = 1000;
  const rows: PlanRow[] = Array.from(aggByProcessCode.entries())
    .map(([process_code, agg]) => ({
      month: baseMonthKey,
      product: "",
      process_code,
      month_plan: agg.monthPlan * monthlyPlanSheetUnitScale,
      prev_day_plan: agg.baseDatePlan * monthlyPlanSheetUnitScale,
    }))
    .sort((a, b) => {
      const oa = processCodeSheetOrder.get(a.process_code) ?? 0;
      const ob = processCodeSheetOrder.get(b.process_code) ?? 0;
      if (!useGroupSort) {
        return oa - ob;
      }
      const ra = processGroupSortRank(codeToGroup.get(a.process_code) ?? "");
      const rb = processGroupSortRank(codeToGroup.get(b.process_code) ?? "");
      if (ra !== rb) return ra - rb;
      return oa - ob;
    });

  const findFirstSheetRowForProcessCode = (code: string): number | null => {
    for (let rr = processStartRowIdx; rr <= range.e.r; rr++) {
      const raw = String(
        sheet[XLSX.utils.encode_cell({ r: rr, c: processCodeColIdx })]?.v ??
          sheet[XLSX.utils.encode_cell({ r: rr, c: processCodeColIdx })]?.w ??
          "",
      ).trim();
      if (!raw) continue;
      if (raw.replace(/\s+/gu, "") === code) return rr;
    }
    return null;
  };

  const excelDisplayQty = (c: any) => excelCellToNumber(c?.w ?? c?.v);

  for (const code of MONTHLY_PLAN_TRACE_CODES) {
    const row = rows.find((x) => x.process_code === code);
    const rr = findFirstSheetRowForProcessCode(code);
    let excelRawMonthlyValue = 0;
    let excelRawBaseDayValue: number | null = null;
    if (rr != null) {
      if (baseDateCol) {
        const bc = sheet[XLSX.utils.encode_cell({ r: rr, c: baseDateCol.colIdx })];
        excelRawBaseDayValue = excelDisplayQty(bc);
      }
      for (const dc of dateCols) {
        if (!dc.inBaseMonth) continue;
        const qa = XLSX.utils.encode_cell({ r: rr, c: dc.colIdx });
        excelRawMonthlyValue += excelDisplayQty(sheet[qa]);
      }
    }
    console.log("[월간플랜 수량 검증]", {
      processCode: code,
      excelRawMonthlyValue,
      excelRawBaseDayValue,
      finalDisplayedMonthlyValue: row?.month_plan,
      finalDisplayedBaseDayValue: row?.prev_day_plan,
    });
  }

  return {
    rows,
    note:
      rows.length > 0
        ? "업로드 파일 기준으로 표시합니다."
        : "유효한 공정코드·수량 행을 찾지 못했습니다.",
  };
}

export default function App() {
  const [baseDate, setBaseDate] = useState<string>(() => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  });
  const [todayFile, setTodayFile] = useState<File | null>(null);
  /** 입력 카드에서 선택; 공정불량 자동 계산 시 defect_file로 전송(생산일보 계산은 미사용, 상태만 보관). */
  const [codeDefectFile, setCodeDefectFile] = useState<File | null>(null);
  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
  const masterRenderRows = masterRows;
  const [planRows, setPlanRows] = useState<PlanRow[]>([]);
  const [planMonth, setPlanMonth] = useState<string>(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [defectRows, setDefectRows] = useState<AccumulatedDefectSummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ---------------------------------------------------------------------------
  // 엑셀 업로드: 월간플랜(첫 번째 시트 worksheet). 누적불량유형은 월간플랜 2번째 시트에서 읽지 않음.
  // 월간플랜: 업로드 시에만 worksheet → planRows, 미업로드 시 표는 비움.
  // ---------------------------------------------------------------------------
  const [uploadedPlanSheetWorksheet, setUploadedPlanSheetWorksheet] = useState<any | null>(
    null,
  );
  const [uploadedPlanFileName, setUploadedPlanFileName] = useState<string | null>(null);
  const [planTableNote, setPlanTableNote] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [data, setData] = useState<ComputeResponse | null>(null);
  const [pdfCapture, setPdfCapture] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  const weeklyDefectRef = useRef<HTMLDivElement>(null);
  const monthlyDefectRef = useRef<HTMLDivElement>(null);
  const lotDefectRef = useRef<HTMLDivElement>(null);
  const defectAutoPatchTokenRef = useRef(0);
  const [defectAutoPatch, setDefectAutoPatch] = useState<{
    token: number;
    weekly: unknown[];
    monthly: unknown[];
  } | null>(null);
  const pdfOnePageRef = useRef<HTMLDivElement>(null);
  const monthlyPlanTableRenderLogSig = useRef<string>("");
  /** 마지막으로 동기화한 생산일보 계산 묶음 — 새 계산 시「현재 제품」을 일보 상단 기준으로 맞춤 */
  const dashboardProductSyncKeyRef = useRef<string>("");
  const [onePageWeeklyChartPng, setOnePageWeeklyChartPng] = useState<string | null>(null);
  const [onePageMonthlyChartPng, setOnePageMonthlyChartPng] = useState<string | null>(null);
  const [weeklyOnePageLegendEntries, setWeeklyOnePageLegendEntries] = useState<
    readonly WeeklyPdfLegendEntry[]
  >(() => buildWeeklyPdfLegendEntries([]));
  const [monthlyOnePageLegendEntries, setMonthlyOnePageLegendEntries] = useState<
    readonly WeeklyPdfLegendEntry[]
  >(() => buildWeeklyPdfLegendEntries([]));

  /**
   * 대시보드「현재 제품」·월별 조립 PPM 등 공통 옵션.
   * - 일보 행의 원본 product를 `pdfProductDisplayForPdfTable`로 통일(DIE→132FBGA 등).
   * - 누적불량유형(defectRows)에만 적힌 제품도 옵션에 포함(계산 행 product 비어 있을 때 보완).
   * - 여전히 비면 기준정보·월간플랜에서 보강.
   */
  const dashboardProductOptionsFromData = useMemo(() => {
    if (!data) return [] as string[];
    const u = new Set<string>();
    for (const r of data.조립공정불량 ?? []) addUniqueDashboardProductKeys(u, r.product);
    for (const r of data.생산진척현황 ?? []) addUniqueDashboardProductKeys(u, r.product);
    for (const r of defectRows) addUniqueDashboardProductKeys(u, r.product);
    if (u.size === 0) {
      const masters = masterRows.length > 0 ? masterRows : (demoMaster as MasterRow[]);
      for (const m of masters) addUniqueDashboardProductKeys(u, m.product);
    }
    if (u.size === 0) {
      for (const p of planRows) addUniqueDashboardProductKeys(u, p.product);
    }
    return [...u].sort((a, b) => a.localeCompare(b, "ko"));
  }, [data, defectRows, masterRows, planRows]);

  const [dashboardSelectedProduct, setDashboardSelectedProduct] = useState("");

  const dashboardPreferredProductFromCompute = useMemo(() => {
    if (!data) return "";
    const raw = inferDefaultDashboardProductFromComputeData(data);
    const opts = dashboardProductOptionsFromData;
    if (raw && opts.includes(raw)) return raw;
    return "";
  }, [data, dashboardProductOptionsFromData]);

  useEffect(() => {
    if (!data) {
      dashboardProductSyncKeyRef.current = "";
      setDashboardSelectedProduct("");
      return;
    }
    const opts = dashboardProductOptionsFromData;
    if (opts.length === 0) {
      setDashboardSelectedProduct("");
      return;
    }
    const syncKey = computeDashboardProductSyncKey(data);
    const preferred =
      dashboardPreferredProductFromCompute || (opts[0] ?? "");

    if (dashboardProductSyncKeyRef.current !== syncKey) {
      dashboardProductSyncKeyRef.current = syncKey;
      setDashboardSelectedProduct(preferred);
      return;
    }

    setDashboardSelectedProduct((prev) => {
      const t = String(prev ?? "").trim();
      if (!t) return preferred;
      const mapped = pdfProductDisplayForPdfTable(t);
      if (opts.includes(mapped)) return mapped;
      if (opts.includes(t)) return t;
      return preferred;
    });
  }, [data, dashboardProductOptionsFromData, dashboardPreferredProductFromCompute]);

  const resolvedDashboardProduct = useMemo(() => {
    const opts = dashboardProductOptionsFromData;
    if (!data || opts.length === 0) return "";
    const preferred = dashboardPreferredProductFromCompute || (opts[0] ?? "");
    const sel = String(dashboardSelectedProduct ?? "").trim();
    if (!sel) return preferred;
    if (opts.includes(sel)) return sel;
    const mapped = pdfProductDisplayForPdfTable(sel);
    if (opts.includes(mapped)) return mapped;
    return preferred;
  }, [
    data,
    dashboardSelectedProduct,
    dashboardProductOptionsFromData,
    dashboardPreferredProductFromCompute,
  ]);

  useEffect(() => {
    if (typeof console === "undefined" || !console.log) return;
    const syncKey = data ? computeDashboardProductSyncKey(data) : "";
    console.log("[dashboard product]", {
      dashboardSelectedProduct,
      dashboardProductOptionsFromData,
      dashboardPreferredProductFromCompute,
      computeSyncKey: syncKey,
      resolvedDashboardProduct,
    });
  }, [
    dashboardSelectedProduct,
    dashboardProductOptionsFromData,
    dashboardPreferredProductFromCompute,
    resolvedDashboardProduct,
    data,
  ]);

  const canSubmit = Boolean(todayFile && baseDate && !loading);

  useEffect(() => {
    if (!data) {
      setOnePageWeeklyChartPng(null);
      setOnePageMonthlyChartPng(null);
      return;
    }

    let cancelled = false;

    const run = async () => {
      await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
      await pdfReflowChartsOnce();
      await new Promise<void>((r) => setTimeout(r, 280));
      if (cancelled) return;

      const pdfRoot = pdfOnePageRef.current;
      const wPh = pdfRoot?.querySelector("[data-pdf-chart-placeholder=\"weekly-ppm\"]");
      const mPh = pdfRoot?.querySelector("[data-pdf-chart-placeholder=\"monthly-ppm\"]");

      console.log("[PDF][ONEPAGE IMG] placeholders", {
        pdfOnePageRoot: Boolean(pdfRoot),
        weeklyPlaceholder: Boolean(wPh),
        monthlyPlaceholder: Boolean(mPh),
      });

      const pickedW = selectLargestSvgFromRoot(weeklyDefectRef.current);
      const pickedM = selectLargestSvgFromRoot(monthlyDefectRef.current);

      if (wPh && pickedW) {
        try {
          const url = await svgElementToPngDataUrlForOnePage(
            pickedW.svg,
            pickedW.width,
            pickedW.height,
            pdfEffectiveSvgRasterScale(),
          );
          if (!cancelled) {
            setOnePageWeeklyChartPng(url);
            console.log("[PDF][ONEPAGE IMG] weekly img injected", { dataUrlLength: url.length });
          }
        } catch (e) {
          if (!cancelled) setOnePageWeeklyChartPng(null);
          console.log("[PDF][ONEPAGE IMG] weekly img inject failed", e);
        }
      } else {
        if (!cancelled) setOnePageWeeklyChartPng(null);
        console.log("[PDF][ONEPAGE IMG] weekly img skipped", {
          placeholderFound: Boolean(wPh),
          svgPicked: Boolean(pickedW),
        });
      }

      if (mPh && pickedM) {
        try {
          const url = await svgElementToPngDataUrlForOnePage(
            pickedM.svg,
            pickedM.width,
            pickedM.height,
            pdfEffectiveSvgRasterScale(),
          );
          if (!cancelled) {
            setOnePageMonthlyChartPng(url);
            console.log("[PDF][ONEPAGE IMG] monthly img injected", { dataUrlLength: url.length });
          }
        } catch (e) {
          if (!cancelled) setOnePageMonthlyChartPng(null);
          console.log("[PDF][ONEPAGE IMG] monthly img inject failed", e);
        }
      } else {
        if (!cancelled) setOnePageMonthlyChartPng(null);
        console.log("[PDF][ONEPAGE IMG] monthly img skipped", {
          placeholderFound: Boolean(mPh),
          svgPicked: Boolean(pickedM),
        });
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [data]);

  async function loadMaster() {
    setError(null);
    try {
      const apiRows = await getMaster();
      console.log("[master load] rows", Array.isArray(apiRows) ? apiRows.length : 0, apiRows);

      const mappedRows = (Array.isArray(apiRows) ? apiRows : []).map((row, idx): MasterRow => {
        const o = (row ?? {}) as Record<string, unknown>;
        const isAssemblyRaw = o.is_assembly ?? o.isAssembly;
        const isAssembly =
          typeof isAssemblyRaw === "boolean"
            ? isAssemblyRaw
              ? "Y"
              : "N"
            : String(isAssemblyRaw ?? "N")
                .trim()
                .toUpperCase();
        const isActiveRaw = o.is_active ?? o.isActive;
        return {
          product: String(o.product ?? "").trim(),
          process_code: String(o.process_code ?? o.processCode ?? "").trim(),
          process_name: String(o.process_name ?? o.processName ?? "").trim(),
          process_group: String(o.process_group ?? o.processGroup ?? "").trim(),
          is_assembly: isAssembly === "Y" ? "Y" : "N",
          display_order: Number.isFinite(Number(o.display_order ?? o.displayOrder))
            ? Number(o.display_order ?? o.displayOrder)
            : idx,
          is_active:
            typeof isActiveRaw === "boolean"
              ? isActiveRaw
              : String(isActiveRaw ?? "")
                  .trim()
                  .toLowerCase() === "true" ||
                String(isActiveRaw ?? "").trim() === "1" ||
                String(isActiveRaw ?? "").trim().toUpperCase() === "Y",
        };
      });

      console.log("[master load mapped]", mappedRows.length, mappedRows);
      setMasterRows(mappedRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function saveMaster() {
    setError(null);
    try {
      const payload = masterRenderRows
        .map((row) => ({
          product: String(row.product ?? "").trim(),
          process_code: String(row.process_code ?? "").trim(),
          process_name: String(row.process_name ?? "").trim(),
          process_group: String(row.process_group ?? "").trim(),
          is_assembly: String(row.is_assembly ?? "N")
            .trim()
            .toUpperCase(),
          display_order: Number(row.display_order) || 0,
          is_active: Boolean(row.is_active),
        }))
        .filter((row) => row.process_code !== "");

      console.log("[master save] payload", {
        count: payload.length,
        rows: payload,
      });

      await postMaster(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    console.log("[master render rows]", masterRenderRows.length, masterRenderRows);
  }, [masterRenderRows]);

  function addMasterRow() {
    setMasterRows((prev) => [
      ...prev,
      {
        product: "",
        process_code: "",
        process_name: "",
        process_group: "",
        is_assembly: "N",
        display_order: prev.length,
        is_active: true,
      },
    ]);
  }

  function removeMasterRow(i: number) {
    setMasterRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  function updateMasterRow(i: number, field: keyof MasterRow, value: string | number | boolean) {
    setMasterRows((prev) => {
      const next = [...prev];
      next[i] = { ...next[i], [field]: value };
      return next;
    });
  }

  function updatePlanRow(i: number, field: keyof PlanRow, value: string | number) {
    setPlanRows((prev) => {
      const next = [...prev];
      next[i] = { ...next[i], [field]: value };
      return next;
    });
  }

  // 월간플랜 엑셀: 첫 시트만 월간계획에 사용. 두 번째 시트가 있어도 누적불량유형으로 읽지 않음(무시).
  function onUploadPlanDefectExcel(file: File | null) {
    if (!file) return;

    setUploadError(null);
    setUploadedPlanSheetWorksheet(null);
    setUploadedPlanFileName(file.name);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const result = e.target?.result;
        if (!(result instanceof ArrayBuffer)) {
          throw new Error("파일을 읽지 못했습니다.");
        }

        const wb = XLSX.read(new Uint8Array(result), { type: "array" });

        const sheetNames = wb.SheetNames ?? [];
        if (sheetNames.length < 1) {
          throw new Error("엑셀에 시트가 없습니다.");
        }

        const planSheetName = sheetNames[0];
        const planWs = wb.Sheets[planSheetName];
        if (!planWs) {
          throw new Error("월간플랜 시트를 읽을 수 없습니다.");
        }

        setUploadedPlanSheetWorksheet(planWs);

        setUploadError(null);
      } catch (err) {
        setUploadedPlanSheetWorksheet(null);
        setUploadedPlanFileName(file.name);
        setUploadError(err instanceof Error ? err.message : String(err));
      }
    };
    reader.onerror = () => {
      setUploadedPlanSheetWorksheet(null);
      setUploadError("파일을 읽는 중 오류가 발생했습니다.");
    };
    reader.readAsArrayBuffer(file);
  }

  // ---------------------------------------------------------------------------
  // 월간플랜(1번째 시트): 업로드된 worksheet만 planRows에 반영. 미업로드 시 빈 표.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!uploadedPlanSheetWorksheet) {
      setPlanRows([]);
      setPlanTableNote("");
      return;
    }
    const { rows, note } = buildPlanRowsFromMonthlyWorksheet(
      uploadedPlanSheetWorksheet,
      baseDate,
      masterRows,
    );
    setPlanRows(rows);
    setPlanTableNote(note);
  }, [uploadedPlanSheetWorksheet, baseDate, masterRows]);

  const prodCols = useMemo(() => {
    // <input type="date"> → "YYYY-MM-DD". 타임존 이슈 없이 월만 사용.
    let month: number | null = null;
    if (baseDate && baseDate.length >= 7) {
      const m = Number(baseDate.slice(5, 7));
      if (Number.isFinite(m) && m >= 1 && m <= 12) month = m;
    }
    const monthPlanLabel = month != null ? `${month}월 계획` : "월 계획";
    return [
      { key: "product", label: "제품" },
      { key: "process_group", label: "공정 대분류" },
      { key: "process_name", label: "공정명" },
      { key: "month_plan", label: monthPlanLabel, align: "right" as const },
      { key: "prev_day_plan", label: "기준일 계획", align: "right" as const },
      { key: "cumulative_actual", label: "실적 누적", align: "right" as const },
      { key: "progress_day", label: "진척률(일)", align: "right" as const },
      { key: "progress_month", label: "진척률(월)", align: "right" as const },
      { key: "prev_day_actual", label: "전일 실적", align: "right" as const },
      {
        key: "remark",
        label: "특이사항",
        align: "center" as const,
        render: ({ row }: { row: ProductionProgressRow }) => {
          if (!shouldShowProgressRemarkStatusDot(row.cumulative_actual)) {
            return { node: null, align: "center" as const };
          }
          return {
            align: "center" as const,
            node: (
              <div
                style={{
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                  width: "100%",
                }}
              >
                <span style={pdfProgressDayRemarkDotStyle(row.progress_day)} aria-hidden />
              </div>
            ),
          };
        },
      },
    ] as const;
  }, [baseDate]);

  type AssemblyDefectRowNormalized = AssemblyDefectRow & {
    effectiveProduct: string;
    effectiveProcessGroup: string;
  };

  const stripManualPrefix = (s: string) => {
    const lines = s.split(/\r?\n/);
    const cleaned = lines
      .map((line) => line.replace(/^\s*\[수기\]\s*/u, ""))
      .filter((line) => line.trim() !== "");
    return cleaned.join("\n").trim();
  };

  const normalizeAsmRows = (originalRows: AssemblyDefectRow[]): AssemblyDefectRowNormalized[] => {
    // IMPORTANT: row 순서 보존 (sort/reorder 금지)
    const normalized: AssemblyDefectRowNormalized[] = originalRows.map((r) => ({
      ...r,
      effectiveProduct: String(r.product ?? "").trim(),
      effectiveProcessGroup: String(r.process_group ?? "").trim(),
    }));

    // forward fill
    let lastProduct = "";
    for (const r of normalized) {
      if (r.effectiveProduct) lastProduct = r.effectiveProduct;
      else r.effectiveProduct = lastProduct;
    }

    // backward fill (맨 앞 빈 product 보정)
    let nextProduct = "";
    for (let i = normalized.length - 1; i >= 0; i--) {
      if (normalized[i].effectiveProduct) nextProduct = normalized[i].effectiveProduct;
      else normalized[i].effectiveProduct = nextProduct;
    }

    return normalized;
  };

  const buildManualSummaryMap = () => {
    const map = new Map<string, string>();
    for (const row of defectRows) {
      const product = String(row.product ?? "").trim();
      const processGroup = String(row.process_group ?? "").trim();
      if (!product || !processGroup) continue;
      const summary = String(row.defect_summary ?? "").trim();
      if (!summary) continue;
      map.set(`${product}__${processGroup}`, summary);
    }
    return map;
  };

  const buildAsmRowsWithManualSummary = (
    originalRows: ReadonlyArray<AssemblyDefectRow>,
  ): AssemblyDefectRowNormalized[] => {
    const normalized = normalizeAsmRows(cloneAssemblyDefectRows(originalRows));
    const manualSummaryMap = buildManualSummaryMap();
    const tracedGroupKeys = new Set<string>();
    let traceGroupCount = 0;
    const MAX_CUM_TYPE_TRACE_GROUPS = 10;

    return normalized.map((r) => {
      const key = `${r.effectiveProduct}__${r.effectiveProcessGroup}`;
      const manualSummary = manualSummaryMap.get(key);
      const backendTypes = String(r.defect_cumulative_types ?? "").trim();
      const manualStr =
        manualSummary !== undefined && manualSummary !== null
          ? String(manualSummary).trim()
          : "";
      /** 화면/PDF "누적불량유형" 컬럼: 코드별불량 엑셀 기반 수기(defectRows)가 있으면 API 문자열을 덮어씀 */
      const mergedTypes = manualStr !== "" ? manualStr : backendTypes;

      if (traceGroupCount < MAX_CUM_TYPE_TRACE_GROUPS && !tracedGroupKeys.has(key)) {
        tracedGroupKeys.add(key);
        traceGroupCount += 1;
        console.info("[cum_type_trace] process=buildAsmRowsWithManualSummary");
        console.info("[cum_type_trace] response_field_key=defect_cumulative_types");
        console.info(`[cum_type_trace] before_filter_value=${JSON.stringify(backendTypes)}`);
        console.info(`[cum_type_trace] after_filter_value=${JSON.stringify(mergedTypes)}`);
        console.info(`[cum_type_trace] response_value=${JSON.stringify(mergedTypes)}`);
      }

      return {
        ...r,
        defect_cumulative_types: mergedTypes,
      };
    });
  };

  const buildAsmGroupMeta = (rows: ReadonlyArray<AssemblyDefectRowNormalized>) => {
    const firstIndexByGroup = new Map<string, number>();
    const countByGroup = new Map<string, number>();
    const summaryTextByGroup = new Map<string, string>();

    const keyOf = (r: AssemblyDefectRowNormalized) =>
      `${r.effectiveProduct}__${r.effectiveProcessGroup}`;

    rows.forEach((r, idx) => {
      const k = keyOf(r);
      if (!firstIndexByGroup.has(k)) firstIndexByGroup.set(k, idx);
      countByGroup.set(k, (countByGroup.get(k) ?? 0) + 1);

      const summaryFromTypes = stripManualPrefix(String(r.defect_cumulative_types ?? "").trim());
      const summaryFromManual = stripManualPrefix(String((r as unknown as { defect_summary?: unknown }).defect_summary ?? "").trim());
      const summary = summaryFromTypes || summaryFromManual;

      if (summary && !summaryTextByGroup.has(k)) summaryTextByGroup.set(k, summary);
    });

    return { keyOf, firstIndexByGroup, countByGroup, summaryTextByGroup };
  };

  const asmCols = useMemo(
    () =>
      [
        { key: "product", label: "제품" },
        { key: "process_group", label: "공정 대분류" },
        { key: "process_name", label: "공정명" },
        { key: "assembly_cumulative", label: "조립 실적 누적", align: "right" as const },
        { key: "assembly_prev_day", label: "전일 조립 실적", align: "right" as const },
        { key: "defect_prev_day_count", label: "전일 불량 개수", align: "right" as const },
        { key: "defect_prev_day_ppm", label: "전일 불량률(ppm)", align: "right" as const },
        { key: "defect_cumulative_count", label: "누적 불량 개수", align: "right" as const },
        { key: "defect_cumulative_ppm", label: "누적 불량률(ppm)", align: "right" as const },
        {
          key: "defect_cumulative_types",
          label: "누적 불량 유형",
          render: (args: {
            row: AssemblyDefectRowNormalized;
            rowIndex: number;
            rows: ReadonlyArray<AssemblyDefectRowNormalized>;
            formatted: React.ReactNode;
          }) => {
            const { row, rowIndex, rows } = args;
            const meta = buildAsmGroupMeta(rows);
            const groupKey = meta.keyOf(row);
            const isFirstGroupRow = meta.firstIndexByGroup.get(groupKey) === rowIndex;

            if (!isFirstGroupRow) return { skip: true, node: null };

            const span = meta.countByGroup.get(groupKey) ?? 1;
            const summary = meta.summaryTextByGroup.get(groupKey) ?? "";

            return { node: summary, rowSpan: span, align: "left" as const };
          },
        },
      ] as const,
    [],
  );

  const asmRowsForTable = useMemo(() => {
    if (!data) return [] as AssemblyDefectRowNormalized[];
    // IMPORTANT: 표 row 순서는 서버 계산 결과(원본) 그대로 유지해야 함.
    // normalize/effective* 는 그룹 판단(rowSpan/first row) 용도로만 사용.
    return buildAsmRowsWithManualSummary(data.조립공정불량);
  }, [data, defectRows]);

  const pdfOnePageAsmMeta = useMemo(() => buildAsmGroupMeta(asmRowsForTable), [asmRowsForTable]);

  function rowsToSheetRows(
    rows: Record<string, unknown>[],
    cols: ReadonlyArray<{ key: string; label: string }>,
  ): Record<string, string | number>[] {
    return rows.map((row) => {
      const o: Record<string, string | number> = {};
      cols.forEach(({ key, label }) => {
        const v = row[key];
        o[label] = typeof v === "number" ? v : String(v ?? "");
      });
      return o;
    });
  }

  function downloadExcel(res: ComputeResponse) {
    const base = res.meta.base_date;
    const wb = XLSX.utils.book_new();
    const sheet1 = XLSX.utils.json_to_sheet(rowsToSheetRows(res.생산진척현황, prodCols));
    // 엑셀도 표와 동일하게 원본 순서 유지 + UI와 동일한 그룹 메타로 "누적불량유형" 값 보정
    const asmNormalized = buildAsmRowsWithManualSummary(res.조립공정불량);
    const meta = buildAsmGroupMeta(asmNormalized);
    const asmExportRows = asmNormalized.map((r, idx) => {
      const key = meta.keyOf(r);
      const isFirst = meta.firstIndexByGroup.get(key) === idx;
      const summary = meta.summaryTextByGroup.get(key) ?? "";
      return {
        ...r,
        defect_cumulative_types: isFirst ? summary : "",
      };
    });
    const sheet2 = XLSX.utils.json_to_sheet(rowsToSheetRows(asmExportRows, asmCols));
    XLSX.utils.book_append_sheet(wb, sheet1, "생산 진척 현황");
    XLSX.utils.book_append_sheet(wb, sheet2, "조립 공정 불량");
    XLSX.writeFile(wb, `생산일보_${base}.xlsx`);
  }

  function savePdfFile(pdf: InstanceType<typeof jsPDF>, filename: string) {
    try {
      pdf.save(filename);
    } catch (saveErr) {
      console.error("[PDF] pdf.save 실패, blob 링크로 재시도", saveErr);
      const blob = pdf.output("blob");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }

  async function downloadPdf(baseDateStr: string) {
    const target = pdfOnePageRef.current;
    if (!target) {
      console.error(
        "[PDF] pdfOnePageRef가 없습니다. 페이지를 새로고침한 뒤 PDF 다운로드를 다시 시도해 주세요.",
      );
      window.alert("PDF 캡처 대상이 준비되지 않았습니다. 계산 결과가 렌더링된 뒤 다시 시도해 주세요.");
      return;
    }
    const captureWeekly = weeklyDefectRef.current;
    const captureMonthly = monthlyDefectRef.current;
    const contentTarget = target.querySelector("[data-pdf-capture-root]") as HTMLElement | null;
    const sizeRef = contentTarget ?? target;
    const scale = pdfEffectiveHtml2canvasScale();
    const svgRasterScale = pdfEffectiveSvgRasterScale();
    let bodyClone: HTMLElement | null = null;
    let lotClone: HTMLElement | null = null;
    const html2canvasOptsForOnePage = {
      scale,
      backgroundColor: "#ffffff",
      useCORS: true,
      allowTaint: true,
      foreignObjectRendering: false,
      logging: false,
      onclone: (_clonedDoc: Document, clonedElement: HTMLElement) => {
        const layout =
          clonedElement.getAttribute("data-pdf-one-page-layout") === "true"
            ? clonedElement
            : (clonedElement.closest("[data-pdf-one-page-layout=\"true\"]") as HTMLElement | null) ??
              (_clonedDoc.querySelector("[data-pdf-one-page-layout=\"true\"]") as HTMLElement | null);
        if (layout) {
          layout.classList.add("pdf-export-mode");
          layout.style.position = "absolute";
          layout.style.left = "0px";
          layout.style.top = "0px";
          layout.style.zIndex = "9999";
          layout.style.opacity = "1";
          layout.style.visibility = "visible";
          layout.style.display = "block";
          layout.style.overflow = "visible";
          layout.style.backgroundColor = "#ffffff";
          layout.removeAttribute("aria-hidden");
        }
        clonedElement.style.pointerEvents = "auto";
        const allNodes = clonedElement.querySelectorAll("*");
        allNodes.forEach((node) => {
          const elNode = node as HTMLElement;
          const style = elNode.style;
          style.backgroundImage = "none";
          style.maskImage = "none";
          (style as CSSStyleDeclaration & { webkitMaskImage?: string }).webkitMaskImage = "none";
          style.filter = "none";
          (style as CSSStyleDeclaration & { backdropFilter?: string }).backdropFilter = "none";
        });
        const canvases = clonedElement.querySelectorAll("canvas");
        canvases.forEach((c) => {
          if ((c.width ?? 0) === 0 || (c.height ?? 0) === 0) {
            c.remove();
          }
        });
        void clonedElement.offsetHeight;
      },
    };

    try {
      if (captureWeekly) captureWeekly.classList.add("pdf-export-mode");
      if (captureMonthly) captureMonthly.classList.add("pdf-export-mode");
      setPdfCapture(true);

      await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
      await pdfReflowChartsOnce();
      await new Promise<void>((r) => setTimeout(r, 360));

      let weeklyPng: string | null = null;
      let monthlyPng: string | null = null;

      const pickedWeekly = selectLargestSvgFromRoot(captureWeekly);
      if (pickedWeekly) {
        try {
          weeklyPng = await svgElementToPngDataUrlForOnePage(
            pickedWeekly.svg,
            pickedWeekly.width,
            pickedWeekly.height,
            svgRasterScale,
          );
          console.log("[PDF][ONEPAGE] weekly png generated");
        } catch (genWErr) {
          console.log("[PDF][ONEPAGE] weekly png generate failed", genWErr);
        }
      } else {
        console.log("[PDF][ONEPAGE] weekly png generate failed", { reason: "no chart svg" });
      }

      const pickedMonthly = selectLargestSvgFromRoot(captureMonthly);
      if (pickedMonthly) {
        try {
          monthlyPng = await svgElementToPngDataUrlForOnePage(
            pickedMonthly.svg,
            pickedMonthly.width,
            pickedMonthly.height,
            svgRasterScale,
          );
          console.log("[PDF][ONEPAGE] monthly png generated");
        } catch (genMErr) {
          console.log("[PDF][ONEPAGE] monthly png generate failed", genMErr);
        }
      } else {
        console.log("[PDF][ONEPAGE] monthly png generate failed", { reason: "no chart svg" });
      }

      flushSync(() => {
        setOnePageWeeklyChartPng(weeklyPng);
        setOnePageMonthlyChartPng(monthlyPng);
      });

      await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
      await pdfReflowChartsOnce();
      await new Promise<void>((r) => setTimeout(r, 220));

      const readChartImgs = () => {
        const wPh = target.querySelector("[data-pdf-chart-placeholder=\"weekly-ppm\"]");
        const mPh = target.querySelector("[data-pdf-chart-placeholder=\"monthly-ppm\"]");
        const wImg = wPh?.querySelector("img");
        const mImg = mPh?.querySelector("img");
        return {
          wImg: wImg instanceof HTMLImageElement ? wImg : null,
          mImg: mImg instanceof HTMLImageElement ? mImg : null,
        };
      };

      let weeklyImgReady = false;
      let monthlyImgReady = false;
      const maxImgWaitFrames = 90;
      for (let i = 0; i < maxImgWaitFrames; i++) {
        await new Promise<void>((r) => requestAnimationFrame(() => r()));
        const { wImg, mImg } = readChartImgs();
        weeklyImgReady = Boolean(wImg && wImg.complete && wImg.naturalWidth > 0);
        monthlyImgReady = Boolean(mImg && mImg.complete && mImg.naturalWidth > 0);
        if (weeklyImgReady && monthlyImgReady) {
          break;
        }
      }

      const { wImg: wImgFinal, mImg: mImgFinal } = readChartImgs();
      if (weeklyImgReady && wImgFinal) {
        console.log("[PDF][ONEPAGE] weekly img rendered", {
          naturalWidth: wImgFinal.naturalWidth,
          naturalHeight: wImgFinal.naturalHeight,
        });
      } else {
        console.log("[PDF][ONEPAGE] weekly img rendered", {
          ok: false,
          naturalWidth: wImgFinal?.naturalWidth ?? 0,
          naturalHeight: wImgFinal?.naturalHeight ?? 0,
          hasImgNode: Boolean(wImgFinal),
        });
      }
      if (monthlyImgReady && mImgFinal) {
        console.log("[PDF][ONEPAGE] monthly img rendered", {
          naturalWidth: mImgFinal.naturalWidth,
          naturalHeight: mImgFinal.naturalHeight,
        });
      } else {
        console.log("[PDF][ONEPAGE] monthly img rendered", {
          ok: false,
          naturalWidth: mImgFinal?.naturalWidth ?? 0,
          naturalHeight: mImgFinal?.naturalHeight ?? 0,
          hasImgNode: Boolean(mImgFinal),
        });
      }

      if (!weeklyImgReady || !monthlyImgReady) {
        console.warn("[PDF][ONEPAGE] 차트 img 미확인 — 캡처는 진행합니다", {
          weeklyImgReady,
          monthlyImgReady,
        });
      }

      if (sizeRef.scrollWidth < 1 || sizeRef.scrollHeight < 1) {
        window.alert("PDF 캡처 대상 콘텐츠 크기가 0입니다. 화면 렌더링 후 다시 시도해 주세요.");
        return;
      }

      bodyClone = target.cloneNode(true) as HTMLElement;
      bodyClone.classList.add("pdf-export-mode");
      bodyClone.removeAttribute("aria-hidden");
      bodyClone.style.position = "fixed";
      bodyClone.style.left = "0";
      bodyClone.style.top = "0";
      bodyClone.style.width = "1320px";
      bodyClone.style.margin = "0";
      bodyClone.style.padding = "0";
      bodyClone.style.boxSizing = "border-box";
      bodyClone.style.pointerEvents = "none";
      bodyClone.style.backgroundColor = "#ffffff";
      bodyClone.style.opacity = "1";
      bodyClone.style.visibility = "visible";
      bodyClone.style.overflow = "visible";
      bodyClone.style.zIndex = "2147483646";
      bodyClone.style.transform = "translate3d(calc(-100vw - 2400px), 0, 0)";
      document.body.appendChild(bodyClone);
      void bodyClone.offsetHeight;
      window.dispatchEvent(new Event("resize"));
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
      await pdfReflowChartsOnce();
      await new Promise<void>((r) => setTimeout(r, 240));

      const captureOverflowTargets = bodyClone.querySelectorAll(
        ".card, .tableWrap, .weekly-defect-chart-capture-target, [data-pdf-capture-root]",
      );
      captureOverflowTargets.forEach((el) => {
        (el as HTMLElement).style.overflow = "visible";
      });

      const w = Math.max(1, bodyClone.scrollWidth);
      const h = Math.max(1, bodyClone.scrollHeight);
      console.log("[PDF size FIX]", {
        scrollWidth: bodyClone.scrollWidth,
        scrollHeight: bodyClone.scrollHeight,
        offsetWidth: bodyClone.offsetWidth,
        offsetHeight: bodyClone.offsetHeight,
      });
      console.log("[PDF clone capture]", bodyClone.offsetWidth, bodyClone.offsetHeight, {
        scrollW: w,
        scrollH: h,
      });

      const canvas = await html2canvas(bodyClone, {
        ...html2canvasOptsForOnePage,
        width: w,
        height: h,
        windowWidth: w,
        windowHeight: h,
      });
      console.log("[PDF page1 canvas]", canvas.width, canvas.height);
      if (canvas.height < 200) {
        window.alert("PDF 캡처 높이가 비정상적으로 작습니다.");
        return;
      }

      if (!canvas.width || !canvas.height) {
        throw new Error(
          `[PDF] html2canvas 결과 캔버스 크기가 0입니다 (${canvas.width}x${canvas.height})`,
        );
      }

      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const imgData = canvas.toDataURL("image/png");
      const page1Dest = defectPpmPdfRasterDestMm(canvas.width, canvas.height, pageW, pageH);
      const { imgWidthMm, imgHeightMm, xMm: x, yMm: y } = page1Dest;
      console.log("[PDF place]", { pageWidth: pageW, imgWidth: imgWidthMm, x });
      pdf.addImage(imgData, "PNG", x, y, imgWidthMm, imgHeightMm);

      const lotCaptureTarget =
        (lotDefectRef.current?.matches('[data-pdf-lot-card="true"]')
          ? lotDefectRef.current
          : lotDefectRef.current?.querySelector('[data-pdf-lot-card="true"]')) ??
        (document.querySelector('[data-pdf-lot-card="true"]') as HTMLElement | null);
      console.log("[PDF lot root]", lotDefectRef.current);
      console.log("[PDF lot target]", lotCaptureTarget);
      console.log("[PDF lot target html]", lotCaptureTarget?.outerHTML?.slice(0, 500));
      if (!lotCaptureTarget) {
        console.log("[PDF lot card missing]", {
          lotDefectRef: lotDefectRef.current,
          documentTarget: document.querySelector('[data-pdf-lot-card="true"]'),
        });
        window.alert("LOT PDF 캡처 대상을 찾지 못했습니다.");
      } else {
        /* Recharts SVG는 html2canvas만으로 비어 나올 수 있어 SVG→PNG 후, 클론에서 SVG를 img로 바꾼 뒤 카드 전체를 래스터 */
        pdf.addPage("a4", "portrait");
        const pickedLot =
          selectLargestSvgFromRoot(lotCaptureTarget as HTMLElement) ??
          selectLargestSvgFromRoot(lotDefectRef.current as HTMLElement | null);
        if (!pickedLot) {
          console.warn("[PDF page2 lot] svg 없음");
          pdf.setFontSize(11);
          pdf.text("LOT chart SVG not found.", 14, 20);
        } else {
          try {
            const lotPng = await svgElementToPngDataUrlForOnePage(
              pickedLot.svg,
              pickedLot.width,
              pickedLot.height,
              svgRasterScale,
            );
            lotClone = lotCaptureTarget.cloneNode(true) as HTMLElement;
            lotClone.classList.add("pdf-export-mode");
            /* 사용자 화면엔 보이지 않되, html2canvas가 안정적으로 레이아웃을 읽게 transform은 쓰지 않음 */
            lotClone.style.position = "fixed";
            lotClone.style.left = "-20000px";
            lotClone.style.top = "0";
            lotClone.style.width = `${PDF_ONE_PAGE_ROOT_WIDTH_PX}px`;
            lotClone.style.minWidth = `${PDF_ONE_PAGE_ROOT_WIDTH_PX}px`;
            lotClone.style.maxWidth = `${PDF_ONE_PAGE_ROOT_WIDTH_PX}px`;
            lotClone.style.margin = "0";
            lotClone.style.boxSizing = "border-box";
            lotClone.style.backgroundColor = "#ffffff";
            lotClone.style.visibility = "visible";
            lotClone.style.opacity = "1";
            lotClone.style.pointerEvents = "none";
            lotClone.style.zIndex = "2147483646";
            lotClone.style.transform = "none";
            lotClone.style.overflow = "visible";
            /* 1페이지 주입 CSS 밖이므로 styles.css와 동일 테두리용 + 래스터 시 카드 테두리 안 잘리게 */
            lotClone.style.setProperty("padding", "10px", "important");
            lotClone.style.setProperty("box-sizing", "border-box", "important");

            /* 클론은 문서에 붙이기 전엔 레이아웃이 없어 SVG 면적이 0 → 선택 실패 → img 미주입 → html2canvas 빈 페이지 */
            document.body.appendChild(lotClone);
            void lotClone.offsetHeight;
            window.dispatchEvent(new Event("resize"));
            await pdfReflowChartsOnce();
            await new Promise<void>((r) => requestAnimationFrame(() => r()));

            let clonePick = selectLargestSvgFromRoot(lotClone);
            if (!clonePick && pickedLot.index >= 0) {
              const svgList = lotClone.querySelectorAll("svg");
              const byIdx = svgList[pickedLot.index] as SVGSVGElement | undefined;
              if (byIdx?.parentNode) {
                let cw = byIdx.clientWidth;
                let ch = byIdx.clientHeight;
                if (cw <= 0 || ch <= 0) {
                  const br = byIdx.getBoundingClientRect();
                  cw = br.width;
                  ch = br.height;
                }
                if (cw <= 0 || ch <= 0) {
                  cw = pickedLot.width;
                  ch = pickedLot.height;
                }
                clonePick = { svg: byIdx, index: pickedLot.index, width: cw, height: ch };
              }
            }

            let chartImg: HTMLImageElement | null = null;
            if (clonePick?.svg?.parentNode) {
              const doc = lotClone.ownerDocument ?? document;
              const img = doc.createElement("img");
              const rw = Math.max(1, Math.round(clonePick.width || pickedLot.width));
              const rh = Math.max(1, Math.round(clonePick.height || pickedLot.height));
              img.setAttribute("width", String(rw));
              img.setAttribute("height", String(rh));
              img.style.display = "block";
              img.style.width = "100%";
              img.style.height = "auto";
              img.style.maxWidth = `${rw}px`;
              img.alt = "";
              clonePick.svg.parentNode.replaceChild(img, clonePick.svg);
              chartImg = img;
            }

            if (chartImg) {
              await awaitLotPdfChartImgReady(chartImg, lotPng);
            }
            await new Promise<void>((r) => setTimeout(r, 100));
            void lotClone.offsetHeight;

            const lotCardHtml2canvasOpts = {
              scale,
              backgroundColor: "#ffffff",
              useCORS: true,
              allowTaint: true,
              foreignObjectRendering: false,
              logging: false,
              onclone: (_doc: Document, el: HTMLElement) => {
                void el.offsetHeight;
              },
            };

            const placeLotChartPngOnly = () => {
              const pw = pickedLot.width;
              const ph = pickedLot.height;
              const d = defectPpmPdfRasterDestMmCappedToMaxWidth(
                pw,
                ph,
                pageW,
                pageH,
                page1Dest.imgWidthMm,
              );
              pdf.addImage(lotPng, "PNG", d.xMm, d.yMm, d.imgWidthMm, d.imgHeightMm);
            };

            /* SVG→img 주입 실패 시 카드 전체 캡처는 비어 나올 수 있음 → 차트 PNG만이라도 표시 */
            if (!chartImg) {
              console.warn("[PDF page2 lot] chart <img> not injected — using chart PNG only");
              placeLotChartPngOnly();
            } else {
            /* 고정 height는 이미지 로드 전에 잡히면 잘려 흰 캔버스가 됨 — 요소 자연 크기로 캡처 */
            const lotCanvas = await html2canvas(lotClone, lotCardHtml2canvasOpts);
            console.log("[PDF page2 lot card canvas]", lotCanvas.width, lotCanvas.height);

            if (lotCanvas.width >= 40 && lotCanvas.height >= 40) {
              const lotImgData = lotCanvas.toDataURL("image/png");
              const lotD = defectPpmPdfRasterDestMmCappedToMaxWidth(
                lotCanvas.width,
                lotCanvas.height,
                pageW,
                pageH,
                page1Dest.imgWidthMm,
              );
              pdf.addImage(lotImgData, "PNG", lotD.xMm, lotD.yMm, lotD.imgWidthMm, lotD.imgHeightMm);
            } else {
              console.warn("[PDF page2 lot] canvas too small, fallback chart png only");
              placeLotChartPngOnly();
            }
            }
          } catch (lotErr) {
            console.error("[PDF page2 lot failed]", lotErr);
            pdf.setFontSize(11);
            pdf.text("LOT page export failed.", 14, 20);
          }
        }
      }

      savePdfFile(pdf, `생산일보_${baseDateStr}.pdf`);
    } catch (pdfErr) {
      console.error("[PDF ERROR]", pdfErr);
    } finally {
      if (bodyClone?.parentNode) {
        bodyClone.remove();
      }
      bodyClone = null;
      if (lotClone?.parentNode) {
        lotClone.remove();
      }
      lotClone = null;
      console.log("[PDF clone removed]");
      setPdfCapture(false);
      if (captureWeekly) captureWeekly.classList.remove("pdf-export-mode");
      if (captureMonthly) captureMonthly.classList.remove("pdf-export-mode");
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!todayFile) return;
    setLoading(true);
    setError(null);
    try {
      const hasUploadWorksheet = uploadedPlanSheetWorksheet != null;
      const planMonthKey = baseDate.length >= 7 ? baseDate.slice(0, 7) : planMonth;
      let serverPlanRows: PlanRow[] = [];
      if (!hasUploadWorksheet) {
        try {
          serverPlanRows = await getPlan(planMonthKey);
        } catch (err) {
          console.warn("[생산일보 계산] 저장된 월간플랜 GET 실패 — 데모·빈 플랜 경로로 진행", err);
        }
      }
      const { planSourceRows, usingUploaded, usingServerPlan, usingDemo } =
        pickMonthlyPlanSourceRowsForCompute(hasUploadWorksheet, planRows, planMonthKey, serverPlanRows);

      const masterForMatch =
        masterRows.length > 0 ? masterRows : (demoMaster as MasterRow[]);
      const planByCode = buildPlanByProcessCode(planSourceRows);

      console.log("[생산일보 계산] monthly plan source", {
        planMonthKey,
        "using uploaded monthly plan": usingUploaded,
        "using server GET /plan rows": usingServerPlan,
        "using demo monthly plan": usingDemo,
        "final plan sample 3건": planSourceRows.slice(0, 3).map((r) => ({
          process_code: r.process_code,
          month_plan: r.month_plan,
          prev_day_plan: r.prev_day_plan,
        })),
      });

      /*
       * 생산진척현황: /compute 응답 베이스 → applyPlanToProgressRows로 month_plan·prev_day_plan·remark만 화면 월간플랜과 병합.
       * prev_day_actual·cumulative_actual 등은 API 값 유지(API 실패 시에만 데모 베이스).
       * 조립공정불량 숫자: API 응답 조립공정불량(API 실패 시 데모 fallback).
       */
      let serverCompute: ComputeResponse | undefined;
      let productionProgressSource: "compute_api" | "demo_fallback" = "compute_api";
      let assemblyNumericSource: "compute_api" | "demo_compute_fallback" = "compute_api";
      let assemblyRowsResolved: AssemblyDefectRow[];
      let progressBase: ProductionProgressRow[];
      try {
        console.log("[/compute payload] source rows", {
          baseDate,
          masterRowsCount: masterForMatch.length,
          planRowsCount: planSourceRows.length,
          masterSample: masterForMatch.slice(0, 3).map((r) => ({
            product: r.product,
            process_code: r.process_code,
            process_name: r.process_name,
            process_group: r.process_group,
          })),
          planSample: planSourceRows.slice(0, 3).map((r) => ({
            month: r.month,
            product: r.product,
            process_code: r.process_code,
            month_plan: r.month_plan,
            prev_day_plan: r.prev_day_plan,
          })),
        });
        const computeUrl = `${API_BASE}/compute`;
        const formData = new FormData();
        formData.append("base_date", baseDate);
        formData.append("today_file", todayFile);
        formData.append("master_rows_json", JSON.stringify(masterForMatch));
        formData.append("plan_rows_json", JSON.stringify(planSourceRows));

        const res = await fetch(computeUrl, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(`서버 오류 (${res.status}): ${text || res.statusText}`);
        }
        serverCompute = (await res.json()) as ComputeResponse;
        progressBase = cloneProductionProgressRows(serverCompute.생산진척현황);
        assemblyRowsResolved = cloneAssemblyDefectRows(serverCompute.조립공정불량);
      } catch (apiErr) {
        productionProgressSource = "demo_fallback";
        assemblyNumericSource = "demo_compute_fallback";
        serverCompute = undefined;
        progressBase = cloneProductionProgressRows(DEMO_COMPUTE.생산진척현황);
        assemblyRowsResolved = cloneAssemblyDefectRows(DEMO_COMPUTE.조립공정불량);
        console.warn(
          "[/compute 실패] 생산진척현황·조립공정불량 숫자 demoCompute.json fallback",
          apiErr,
        );
      }

      const mergedProgress = applyPlanToProgressRows(progressBase, planByCode, masterForMatch);
      const monthPlanTotal = mergedProgress.reduce(
        (s, r) => s + (Number(r.month_plan) || 0),
        0,
      );
      const y = baseDate.slice(0, 4);
      const mNum = Number(baseDate.slice(5, 7));
      const monthLabel = `${y}년 ${mNum}월`;
      const summaryTitle = `1. 생산 진척 현황 : ${monthLabel} 생산계획(GOC) : ${monthPlanTotal.toLocaleString("ko-KR")}ea`;

      console.log("[생산진척현황] prev_day_actual 소스", {
        production_progress_prev_day_source: productionProgressSource,
        samplePrevDayActual: mergedProgress.slice(0, 3).map((r) => ({
          process_name: r.process_name,
          prev_day_actual: r.prev_day_actual,
        })),
      });

      const res: ComputeResponse = {
        ...DEMO_COMPUTE,
        meta: {
          ...DEMO_COMPUTE.meta,
          base_date: baseDate,
          prev_date: prevCalendarDay(baseDate),
          detected_sheets_today: [todayFile.name],
          detected_sheets_prev: [todayFile.name],
          month_label: monthLabel,
          month_plan_total: monthPlanTotal,
          summary_title: summaryTitle,
        },
        생산진척현황: mergedProgress,
        조립공정불량: assemblyRowsResolved,
      };

      console.log("[조립공정불량] 숫자 소스", {
        assemblyNumericSource,
        rowCount: assemblyRowsResolved.length,
        cumulativeDefectSum: assemblyRowsResolved.reduce(
          (s, r) => s + (Number(r.defect_cumulative_count) || 0),
          0,
        ),
      });

      mergedProgress.slice(0, 3).forEach((row, idx) => {
        const apiPrev = serverCompute?.생산진척현황?.[idx]?.prev_day_actual;
        console.log("[전일 실적 추적]", {
          section: "production_progress",
          processName: row.process_name,
          prevDaySourceValue: apiPrev ?? DEMO_COMPUTE.생산진척현황[idx]?.prev_day_actual,
          sourceName:
            productionProgressSource === "compute_api"
              ? "compute_api (베이스 생산진척현황.prev_day_actual → applyPlan은 month_plan·prev_day_plan·remark만)"
              : "demo_fallback (/compute 실패 시 베이스만 demoCompute)",
          finalDisplayedPrevDay: row.prev_day_actual,
        });
      });

      assemblyRowsResolved.slice(0, 3).forEach((row, idx) => {
        const fallbackPrev = DEMO_COMPUTE.조립공정불량[idx]?.assembly_prev_day;
        console.log("[전일 실적 추적]", {
          section: "assembly_defect",
          processName: row.process_name,
          prevDaySourceValue:
            assemblyNumericSource === "compute_api" ? row.assembly_prev_day : fallbackPrev,
          sourceName: assemblyNumericSource,
          finalDisplayedPrevDay: row.assembly_prev_day,
        });
      });

      setData(res);

      if (codeDefectFile) {
        try {
          const workBuf = await todayFile.arrayBuffer();
          const defectBuf = await codeDefectFile.arrayBuffer();
          setDefectRows(
            buildCumulativeDefectSummaryRows({
              baseDate,
              workBytes: workBuf,
              defectBytes: defectBuf,
              masterRows: masterForMatch,
              assemblyRows: assemblyRowsResolved,
            }),
          );
        } catch (cumErr) {
          console.warn("[누적불량유형 자동 생성]", cumErr);
          setDefectRows([]);
        }
      } else {
        setDefectRows([]);
      }
    } catch (err) {
      setData(null);
      setDefectRows([]);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page">
      <header
        className="topbar"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
        }}
      >
        <div>
          <h1 className="title">3Camp 생산일보</h1>
          <div className="subtitle">
            작업일보 엑셀 업로드 + 기준일 선택 → 생산일보 계산
          </div>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            className="button"
            disabled={!data}
            onClick={() => data && downloadExcel(data)}
          >
            엑셀 다운로드
          </button>
          <button
            type="button"
            className="button"
            disabled={!data}
            onClick={() => data && downloadPdf(data.meta.base_date)}
          >
            PDF 다운로드
          </button>
        </div>
      </header>

      <section className="card">
        <div
          className="master-header-top"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            marginBottom: 8,
          }}
        >
          <h2 className="cardTitle" style={{ marginBottom: 0 }}>
            기준정보 (product 단위)
          </h2>
          <div
            className="base-date-box"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <label
              className="label"
              htmlFor="app-base-date"
              style={{ whiteSpace: "nowrap", marginBottom: 0, fontSize: 12 }}
            >
              기준일
            </label>
            <input
              id="app-base-date"
              className="app-base-date-input"
              type="date"
              value={baseDate}
              onChange={(e) => setBaseDate(e.target.value)}
              required
            />
          </div>
        </div>
        <div
          className="actions"
          style={{ marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10 }}
        >
          <button type="button" className="button" onClick={loadMaster}>
            불러오기
          </button>
          <button type="button" className="button" onClick={saveMaster}>
            저장
          </button>
          <button type="button" className="button" onClick={addMasterRow}>
            행 추가
          </button>
        </div>
        <div className="hint" style={{ marginBottom: 8 }}>
          제품(product), 공정코드, 공정명, 공정 대분류, 조립공정, 표시순서, 사용여부
        </div>
        <div className="tableWrap" style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>제품</th>
                <th>공정코드</th>
                <th>공정명</th>
                <th>공정 대분류</th>
                <th>조립공정</th>
                <th>표시순서</th>
                <th>사용</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {masterRenderRows.map((row, i) => (
                <tr key={i}>
                  <td>
                    <input
                      value={row.product}
                      onChange={(e) => updateMasterRow(i, "product", e.target.value)}
                      placeholder="UDP, 132FBGA 등"
                    />
                  </td>
                  <td>
                    <input
                      value={row.process_code}
                      onChange={(e) => updateMasterRow(i, "process_code", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      value={row.process_name}
                      onChange={(e) => updateMasterRow(i, "process_name", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      value={row.process_group}
                      onChange={(e) => updateMasterRow(i, "process_group", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      value={row.is_assembly}
                      onChange={(e) => updateMasterRow(i, "is_assembly", e.target.value)}
                      placeholder="Y/N"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={row.display_order}
                      onChange={(e) => updateMasterRow(i, "display_order", Number(e.target.value) || 0)}
                      style={{ width: 64 }}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={row.is_active}
                      onChange={(e) => updateMasterRow(i, "is_active", e.target.checked)}
                    />
                  </td>
                  <td>
                    <button type="button" onClick={() => removeMasterRow(i)}>
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="cardTitle">월간플랜</h2>
        <div style={PLAN_MONTH_CARD_TOP}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            <label
              htmlFor="app-plan-month"
              className="label"
              style={{ whiteSpace: "nowrap", marginBottom: 0, fontSize: 12 }}
            >
              월 (YYYY-MM)
            </label>
            <input
              id="app-plan-month"
              type="month"
              value={planMonth}
              onChange={(e) => setPlanMonth(e.target.value)}
              style={{ width: "10.5rem", maxWidth: "11rem", flexShrink: 0 }}
            />
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              gap: 8,
              flex: "1 1 auto",
              minWidth: 0,
            }}
          >
            <span
              className="label"
              style={{
                flexShrink: 0,
                whiteSpace: "nowrap",
                marginBottom: 0,
                fontSize: 12,
              }}
            >
              월간플랜 업로드
            </span>
            <div style={INPUT_FILE_INPUT_WRAP}>
              <input
                type="file"
                accept=".xlsx,.xls"
                onChange={(e) => onUploadPlanDefectExcel(e.target.files?.[0] ?? null)}
                style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}
              />
            </div>
            <span
              className="hint"
              style={{
                margin: 0,
                fontSize: 12,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: "14rem",
                flexShrink: 1,
                minWidth: 0,
              }}
              title={uploadedPlanFileName ?? ""}
            >
              {uploadedPlanFileName ?? ""}
            </span>
          </div>
        </div>

        {uploadError ? (
          <div className="hint" style={{ color: "var(--danger)", marginBottom: 8 }}>
            {uploadError}
          </div>
        ) : null}

        {!uploadedPlanFileName ? (
          <div className="hint" style={{ marginBottom: 12 }}>
            업로드 전에는 월간플랜이 비어 있습니다. 월간플랜 엑셀을 업로드하면 월간계획이 반영됩니다.
          </div>
        ) : uploadError ? null : (
          <div className="hint" style={{ marginBottom: 12 }}>
            {uploadedPlanFileName}
            {planTableNote ? ` — ${planTableNote}` : null}
          </div>
        )}

        <div className="tableWrap" style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>공정코드</th>
                <th>월계획</th>
                <th>기준일 계획</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                if (planRows.length === 0) {
                  monthlyPlanTableRenderLogSig.current = "";
                } else {
                  const sample = planRows.slice(0, 2);
                  const sig = sample
                    .map(
                      (r) =>
                        `${r.process_code}\t${r.month_plan}\t${r.prev_day_plan}`,
                    )
                    .join("\n");
                  if (sig !== monthlyPlanTableRenderLogSig.current) {
                    monthlyPlanTableRenderLogSig.current = sig;
                    for (const row of sample) {
                      const finalCellTextMonthly = formatMonthlyPlanDisplay(
                        row.month_plan,
                      );
                      const finalCellTextBaseDay = formatMonthlyPlanDisplay(
                        row.prev_day_plan,
                      );
                      console.log("[월간플랜 테이블 셀]", {
                        processCode: row.process_code,
                        monthlyPlan: row.month_plan,
                        baseDayPlan: row.prev_day_plan,
                        finalCellTextMonthly,
                        finalCellTextBaseDay,
                      });
                    }
                  }
                }
                return null;
              })()}
              {planRows.map((row, i) => (
                <tr key={i}>
                  <td>
                    <input
                      value={row.process_code}
                      onChange={(e) => updatePlanRow(i, "process_code", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={formatMonthlyPlanDisplay(row.month_plan)}
                      onChange={(e) => {
                        const t = e.target.value.trim().replace(/,/gu, "");
                        if (t === "") {
                          updatePlanRow(i, "month_plan", 0);
                          return;
                        }
                        const n = Number(t);
                        if (Number.isFinite(n)) updatePlanRow(i, "month_plan", n);
                      }}
                      style={{ minWidth: 120, width: 128 }}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={formatMonthlyPlanDisplay(row.prev_day_plan)}
                      onChange={(e) => {
                        const t = e.target.value.trim().replace(/,/gu, "");
                        if (t === "") {
                          updatePlanRow(i, "prev_day_plan", 0);
                          return;
                        }
                        const n = Number(t);
                        if (Number.isFinite(n)) updatePlanRow(i, "prev_day_plan", n);
                      }}
                      style={{ minWidth: 120, width: 128 }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint" style={{ marginTop: 6, fontSize: 12, marginBottom: 0 }}>
          월간플랜 수량은 엑셀 원본값 기준으로 표시됩니다.
        </p>
      </section>

      <section className="card">
        <h2 className="cardTitle">입력</h2>
        <form
          onSubmit={onSubmit}
          style={{
            marginBottom: 8,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
            <div style={INPUT_FILE_ROW}>
              <label
                htmlFor="app-today-file"
                className="label"
                style={{
                  margin: 0,
                  padding: 0,
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                  fontSize: 12,
                }}
              >
                작업일보 엑셀
              </label>
              <div style={INPUT_FILE_INPUT_WRAP}>
                <input
                  id="app-today-file"
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={(e) => setTodayFile(e.target.files?.[0] ?? null)}
                  required
                  style={{
                    width: "100%",
                    minWidth: 0,
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>
            <div style={INPUT_FILE_ROW}>
              <label
                htmlFor="app-code-defect-file"
                className="label"
                style={{
                  margin: 0,
                  padding: 0,
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                  fontSize: 12,
                }}
              >
                코드별 불량현황 엑셀
              </label>
              <div style={INPUT_FILE_INPUT_WRAP}>
                <input
                  id="app-code-defect-file"
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={(e) => setCodeDefectFile(e.target.files?.[0] ?? null)}
                  style={{
                    width: "100%",
                    minWidth: 0,
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>
          </div>
          <button
            className="button"
            type="submit"
            disabled={!canSubmit}
            style={{ alignSelf: "flex-end", marginTop: 8 }}
          >
            {loading ? "계산 중..." : "생산일보 계산"}
          </button>
        </form>

        <div className="hint">
          기준정보·월간플랜은 위에서 관리합니다. 작업일보는 생산일보 계산에, 코드별 불량현황은
          공정불량 자동 계산에 사용합니다.
        </div>
      </section>

      <section className="card">
        <h2 className="cardTitle">결과</h2>
        {!data ? (
          <div className="hint">파일을 업로드하고 “생산일보 계산”을 누르면 표가 표시됩니다.</div>
        ) : (
          <div ref={resultRef}>
            <div
              style={{
                marginBottom: 16,
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 10,
              }}
            >
              <label
                className="label"
                htmlFor="app-dashboard-product"
                style={{ marginBottom: 0, fontSize: 12, whiteSpace: "nowrap" }}
              >
                현재 제품
              </label>
              {dashboardProductOptionsFromData.length > 0 ? (
                <select
                  id="app-dashboard-product"
                  className="app-base-date-input"
                  value={resolvedDashboardProduct}
                  onChange={(e) => setDashboardSelectedProduct(e.target.value)}
                  style={{ minWidth: 160, maxWidth: "100%" }}
                >
                  {dashboardProductOptionsFromData.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="hint">일보에 제품 정보가 없습니다.</span>
              )}
            </div>

            <section className="card" data-pdf-exclude="meta">
              <h2 className="cardTitle">메타/경고</h2>
              <div className="metaGrid">
                <div>
                  <div className="metaK">기준일</div>
                  <div className="metaV">{data.meta.base_date}</div>
                </div>
                <div>
                  <div className="metaK">전일</div>
                  <div className="metaV">{data.meta.prev_date}</div>
                </div>
                <div>
                  <div className="metaK">요약</div>
                  <div className="metaV">
                    {data.meta.summary_title ||
                      (data.meta.month_label && data.meta.month_plan_total != null
                        ? `1. 생산 진척 현황 : ${data.meta.month_label} 생산계획(GOC) : ${Math.trunc(
                            data.meta.month_plan_total,
                          ).toLocaleString("ko-KR")}ea`
                        : "-")}
                  </div>
                </div>
                <div>
                  <div className="metaK">작업일보 엑셀 시트</div>
                  <div className="metaV">{data.meta.detected_sheets_today.join(", ")}</div>
                </div>
                <div>
                  <div className="metaK">동일 파일 시트(참고)</div>
                  <div className="metaV">{data.meta.detected_sheets_prev.join(", ")}</div>
                </div>
              </div>
              {data.meta.warnings.length ? (
                <ul className="warnings">
                  {data.meta.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              ) : (
                <div className="hint">경고 없음</div>
              )}
            </section>

            <DataTable<ProductionProgressRow>
              title="생산 진척 현황"
              pdfExportMode={pdfCapture}
              pdfSectionIcon={Gauge}
              tableClassName="prod-progress-table"
              columns={prodCols}
              rows={data.생산진척현황}
              format={{
                process_name: productionProgressProcessNameDisplay,
                month_plan: fmtNum,
                prev_day_plan: fmtNum,
                cumulative_actual: fmtNum,
                progress_day: fmtPctAchievementColored,
                progress_month: fmtPctAchievementColored,
                prev_day_actual: fmtNum,
              }}
            />

            <DataTable<AssemblyDefectRowNormalized>
              title="조립 공정 불량"
              pdfExportMode={pdfCapture}
              pdfSectionIcon={Cog}
              tableClassName="asm-defect-table"
              columns={asmCols}
              rows={asmRowsForTable}
              format={{
                process_name: productionProgressProcessNameDisplay,
                assembly_cumulative: fmtNum,
                assembly_prev_day: fmtNum,
                defect_prev_day_count: fmtNum,
                defect_prev_day_ppm: fmtPpm,
                defect_cumulative_count: fmtNum,
                defect_cumulative_ppm: fmtPpm,
              }}
            />
          </div>
        )}
      </section>

      <div data-pdf-exclude="chart">
        <DefectAutoUploadPanel
          workFile={todayFile}
          codeDefectFile={codeDefectFile}
          onComputeSuccess={(weekly: unknown[], monthly: unknown[]) => {
            defectAutoPatchTokenRef.current += 1;
            setDefectAutoPatch({
              token: defectAutoPatchTokenRef.current,
              weekly,
              monthly,
            });
          }}
          onResetSuccess={(weekly: unknown[], monthly: unknown[]) => {
            defectAutoPatchTokenRef.current += 1;
            setDefectAutoPatch({
              token: defectAutoPatchTokenRef.current,
              weekly,
              monthly,
            });
          }}
        />
        <WeeklyDefectPPM
          ref={weeklyDefectRef}
          forceFixedChartSize={pdfCapture}
          pdfExportMode={pdfCapture}
          onPdfLegendEntriesChange={setWeeklyOnePageLegendEntries}
          defectAutoMergeWeekly={
            defectAutoPatch
              ? { token: defectAutoPatch.token, rows: defectAutoPatch.weekly }
              : null
          }
        />
      </div>
      <div data-pdf-exclude="chart">
        <MonthlyDefectPPM
          ref={monthlyDefectRef}
          pdfExportMode={pdfCapture}
          forceFixedChartSize={pdfCapture}
          onPdfLegendEntriesChange={setMonthlyOnePageLegendEntries}
          weekIsoReferenceYear={
            baseDate && baseDate.length >= 4 ? Number(baseDate.slice(0, 4)) : undefined
          }
          defectAutoMergeMonthly={
            defectAutoPatch
              ? { token: defectAutoPatch.token, rows: defectAutoPatch.monthly }
              : null
          }
        />
      </div>
      <div data-pdf-exclude="chart">
        <LotDefectPpm
          ref={lotDefectRef}
          pdfExportMode={pdfCapture}
          forceFixedChartSize={pdfCapture}
          autoReloadToken={defectAutoPatch?.token ?? null}
        />
      </div>

      {error ? (
        <section className="card error">
          <h2 className="cardTitle">오류</h2>
          <pre className="pre">{error}</pre>
        </section>
      ) : null}
      </div>

      <div
        ref={pdfOnePageRef}
        data-pdf-one-page-layout="true"
        aria-hidden
        style={PDF_ONE_PAGE_ROOT_STYLE}
      >
        <style dangerouslySetInnerHTML={{ __html: PDF_ONE_PAGE_INJECTED_CSS }} />
        <div data-pdf-capture-root="true" style={PDF_ONE_PAGE_INNER_STYLE}>
          <div style={PDF_ONE_PAGE_TABLE_HOST_STYLE}>
            <section className="card">
              {/*
               * PDF 1페이지 전용 블록: 화면 DataTable·pdfCapture 분기와 무관하게 항상 동일 헤더만 사용
               * (캡처 직전 프레임에서도 배지·패널 스타일 유지)
               */}
              <div
                className={`cardHeader pdf-section-title-panel ${PDF_ONE_PAGE_CARD_HEADER_TIGHT_CLASS}`}
              >
                <h2
                  className={`cardTitle pdf-report-section-title ${PDF_ONE_PAGE_SECTION_TITLE_CLASS}`}
                >
                  <PdfReportIconBadge Icon={Gauge} title="생산 진척 현황" />
                  <span className="pdf-report-section-title-text">생산 진척 현황</span>
                </h2>
              </div>
              <div className="tableWrap">
                <table className="table prod-progress-table" style={PDF_ONE_PAGE_TABLE_FIXED}>
                  <colgroup>
                    {PDF_ONE_PAGE_PROD_COL_WIDTHS_PCT.map((w, idx) => (
                      <col key={idx} style={{ width: w }} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      {prodCols.map((c) => (
                        <th
                          key={String(c.key)}
                          style={
                            c.key === "process_group"
                              ? PDF_ONE_PAGE_TH_TD_CENTER
                              : { textAlign: "align" in c ? c.align : "left" }
                          }
                        >
                          {c.key === "process_group" ? (
                            <span style={PDF_ONE_PAGE_FLEX_CENTER_INNER}>{c.label}</span>
                          ) : (
                            c.label
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.생산진척현황 ?? []).length === 0 ? (
                      <tr>
                        <td className="emptyCell" colSpan={prodCols.length}>
                          데이터가 없습니다.
                        </td>
                      </tr>
                    ) : (
                      (() => {
                        const rows = data?.생산진척현황 ?? [];
                        const effP = buildProgressPdfEffectiveDisplayProducts(rows);
                        return rows.map((r, i) => {
                          const showProduct = i === 0 || effP[i] !== effP[i - 1];
                          const showGroup =
                            i === 0 ||
                            effP[i] !== effP[i - 1] ||
                            pdfNormProcessGroup(r.process_group) !==
                              pdfNormProcessGroup(rows[i - 1].process_group);
                          return (
                            <tr key={i}>
                              {showProduct ? (
                                <td
                                  rowSpan={progressProductRowSpanAtEff(effP, i)}
                                  style={PDF_ONE_PAGE_TABLE_MERGED_TD}
                                >
                                  {effP[i] || pdfProductDisplayForPdfTable(r.product) || "—"}
                                </td>
                              ) : null}
                              {showGroup ? (
                                <td
                                  rowSpan={progressGroupRowSpanAtEff(rows, effP, i)}
                                  style={PDF_ONE_PAGE_TABLE_MERGED_TD}
                                >
                                  <span style={PDF_ONE_PAGE_FLEX_CENTER_INNER}>
                                    {pdfNormProcessGroup(r.process_group) || "—"}
                                  </span>
                                </td>
                              ) : null}
                            <td style={{ textAlign: "left", verticalAlign: "middle" }}>
                              {productionProgressProcessNameDisplay(r.process_name)}
                            </td>
                            <td style={{ textAlign: "right" }}>{fmtNum(r.month_plan)}</td>
                            <td style={{ textAlign: "right" }}>{fmtNum(r.prev_day_plan)}</td>
                            <td style={{ textAlign: "right" }}>{fmtNum(r.cumulative_actual)}</td>
                            <td
                              style={{
                                textAlign: "right",
                                ...pdfKeyMetricTdStyleForProgress(r.progress_day),
                              }}
                            >
                              {fmtPct(r.progress_day)}
                            </td>
                            <td
                              style={{
                                textAlign: "right",
                                ...pdfKeyMetricTdStyleForProgress(r.progress_month),
                              }}
                            >
                              {fmtPct(r.progress_month)}
                            </td>
                            <td style={{ textAlign: "right" }}>{fmtNum(r.prev_day_actual)}</td>
                            <td style={{ textAlign: "center", verticalAlign: "middle" }}>
                              {shouldShowProgressRemarkStatusDot(r.cumulative_actual) ? (
                                <div
                                  style={{
                                    display: "flex",
                                    justifyContent: "center",
                                    alignItems: "center",
                                    width: "100%",
                                  }}
                                >
                                  <span
                                    style={pdfProgressDayRemarkDotStyle(r.progress_day)}
                                    aria-hidden
                                  />
                                </div>
                              ) : null}
                            </td>
                          </tr>
                          );
                        });
                      })()
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <div style={PDF_ONE_PAGE_TABLE_HOST_STYLE}>
            <section className="card">
              <div
                className={`cardHeader pdf-section-title-panel ${PDF_ONE_PAGE_CARD_HEADER_TIGHT_CLASS}`}
              >
                <h2
                  className={`cardTitle pdf-report-section-title ${PDF_ONE_PAGE_SECTION_TITLE_CLASS}`}
                >
                  <PdfReportIconBadge Icon={Cog} title="조립 공정 불량" />
                  <span className="pdf-report-section-title-text">조립 공정 불량</span>
                </h2>
              </div>
              <div className="tableWrap">
                <table className="table asm-defect-table" style={PDF_ONE_PAGE_TABLE_FIXED}>
                  <colgroup>
                    {PDF_ONE_PAGE_ASM_COL_WIDTHS_PCT.map((w, idx) => (
                      <col key={idx} style={{ width: w }} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      {asmCols.map((c) => {
                        const pdfAsmCenterHeader =
                          c.key === "product" ||
                          c.key === "process_group" ||
                          c.key === "assembly_cumulative" ||
                          c.key === "assembly_prev_day" ||
                          c.key === "defect_prev_day_count" ||
                          c.key === "defect_prev_day_ppm" ||
                          c.key === "defect_cumulative_count" ||
                          c.key === "defect_cumulative_ppm";
                        return (
                          <th
                            key={String(c.key)}
                            style={
                              pdfAsmCenterHeader
                                ? PDF_ONE_PAGE_TH_TD_CENTER
                                : { textAlign: "left", verticalAlign: "middle" }
                            }
                          >
                            {pdfAsmCenterHeader ? (
                              <span style={PDF_ONE_PAGE_FLEX_CENTER_INNER}>{c.label}</span>
                            ) : (
                              c.label
                            )}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {asmRowsForTable.length === 0 ? (
                      <tr>
                        <td className="emptyCell" colSpan={asmCols.length}>
                          데이터가 없습니다.
                        </td>
                      </tr>
                    ) : (
                      asmRowsForTable.map((r, i, rows) => {
                        const showProduct =
                          i === 0 || r.effectiveProduct !== rows[i - 1].effectiveProduct;
                        const showGroup =
                          i === 0 ||
                          r.effectiveProduct !== rows[i - 1].effectiveProduct ||
                          r.effectiveProcessGroup !== rows[i - 1].effectiveProcessGroup;
                        const meta = pdfOnePageAsmMeta;
                        const groupKey = meta.keyOf(r);
                        const isFirstDefect = meta.firstIndexByGroup.get(groupKey) === i;
                        const defectSpan = meta.countByGroup.get(groupKey) ?? 1;
                        const defectSummary = meta.summaryTextByGroup.get(groupKey) ?? "";
                        const defMl =
                          defectSummary.includes("\n") || defectSummary.includes("\r");
                        return (
                          <tr key={i}>
                            {showProduct ? (
                              <td
                                rowSpan={asmEffectiveProductRowSpanAt(rows, i)}
                                style={PDF_ONE_PAGE_ASM_MERGED_TD}
                              >
                                <span style={PDF_ONE_PAGE_FLEX_CENTER_INNER}>
                                  {pdfProductDisplayForPdfTable(r.effectiveProduct)}
                                </span>
                              </td>
                            ) : null}
                            {showGroup ? (
                              <td
                                rowSpan={asmEffectiveGroupRowSpanAt(rows, i)}
                                style={PDF_ONE_PAGE_ASM_MERGED_TD}
                              >
                                <span style={PDF_ONE_PAGE_FLEX_CENTER_INNER}>
                                  {r.effectiveProcessGroup}
                                </span>
                              </td>
                            ) : null}
                            <td style={PDF_ONE_PAGE_ASM_TD_LEFT}>
                              {productionProgressProcessNameDisplay(r.process_name)}
                            </td>
                            <td style={PDF_ONE_PAGE_ASM_TD_RIGHT}>
                              {fmtNum(r.assembly_cumulative)}
                            </td>
                            <td style={PDF_ONE_PAGE_ASM_TD_RIGHT}>
                              {fmtNum(r.assembly_prev_day)}
                            </td>
                            <td style={PDF_ONE_PAGE_ASM_TD_RIGHT}>
                              {fmtNum(r.defect_prev_day_count)}
                            </td>
                            <td
                              style={{
                                ...PDF_ONE_PAGE_ASM_TD_RIGHT,
                                ...pdfKeyMetricTdStyleForPpm(r.defect_prev_day_ppm),
                              }}
                            >
                              {fmtPpm(r.defect_prev_day_ppm)}
                            </td>
                            <td style={PDF_ONE_PAGE_ASM_TD_RIGHT}>
                              {fmtNum(r.defect_cumulative_count)}
                            </td>
                            <td
                              style={{
                                ...PDF_ONE_PAGE_ASM_TD_RIGHT,
                                ...pdfKeyMetricTdStyleForPpm(r.defect_cumulative_ppm),
                              }}
                            >
                              {fmtPpm(r.defect_cumulative_ppm)}
                            </td>
                            {isFirstDefect ? (
                              <td rowSpan={defectSpan} style={PDF_ONE_PAGE_ASM_TD_REMARK}>
                                <div className="lastColumnContent">
                                  {defMl ? (
                                    <div className="multilineCell">
                                      {defectSummary.split(/\r?\n/).map((line, li) => (
                                        <div key={li}>{line || "-"}</div>
                                      ))}
                                    </div>
                                  ) : (
                                    defectSummary || "-"
                                  )}
                                </div>
                              </td>
                            ) : null}
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="card" style={PDF_ONE_PAGE_CARD_SECTION_STYLE}>
            <h2
              className={`cardTitle pdf-report-section-title ${PDF_ONE_PAGE_CHART_TITLE_CLASS}`}
            >
              <PdfReportIconBadge Icon={ChartColumn} title={PDF_CHART_SECTION_TITLE_WEEKLY_PPM} />
              <span className="pdf-report-section-title-text">{PDF_CHART_SECTION_TITLE_WEEKLY_PPM}</span>
            </h2>
            <div
              style={PDF_ONE_PAGE_CHART_PLACEHOLDER_STYLE}
              data-pdf-chart-placeholder="weekly-ppm"
            >
              {onePageWeeklyChartPng ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "stretch",
                    width: "100%",
                    maxWidth: "100%",
                    alignSelf: "stretch",
                    backgroundColor: "#ffffff",
                    borderRadius: 4,
                  }}
                >
                  <img
                    src={onePageWeeklyChartPng}
                    alt=""
                    style={{ width: "100%", maxWidth: "100%", height: "auto", display: "block" }}
                  />
                  <div style={PDF_ONE_PAGE_MANUAL_LEGEND_WRAP} aria-hidden>
                    {weeklyOnePageLegendEntries.map((e, i) => (
                      <span
                        key={`${e.label}-${i}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        {e.variant === "line" ? (
                          <span
                            style={{
                              width: 18,
                              height: 3,
                              flexShrink: 0,
                              backgroundColor: e.color,
                              borderRadius: 1,
                            }}
                          />
                        ) : (
                          <span
                            style={{
                              width: 14,
                              height: 14,
                              flexShrink: 0,
                              backgroundColor: e.color,
                              borderRadius: 2,
                            }}
                          />
                        )}
                        {e.label}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                `${PDF_CHART_SECTION_TITLE_WEEKLY_PPM} 차트 이미지 영역 (추후 주입)`
              )}
            </div>
          </section>

          <section className="card" style={PDF_ONE_PAGE_CARD_SECTION_STYLE}>
            <h2
              className={`cardTitle pdf-report-section-title ${PDF_ONE_PAGE_CHART_TITLE_CLASS}`}
            >
              <PdfReportIconBadge Icon={ChartLine} title={PDF_CHART_SECTION_TITLE_MONTHLY_PPM} />
              <span className="pdf-report-section-title-text">{PDF_CHART_SECTION_TITLE_MONTHLY_PPM}</span>
            </h2>
            <div
              style={PDF_ONE_PAGE_CHART_PLACEHOLDER_STYLE}
              data-pdf-chart-placeholder="monthly-ppm"
            >
              {onePageMonthlyChartPng ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "stretch",
                    width: "100%",
                    maxWidth: "100%",
                    alignSelf: "stretch",
                    backgroundColor: "#ffffff",
                    borderRadius: 4,
                  }}
                >
                  <img
                    src={onePageMonthlyChartPng}
                    alt=""
                    style={{ width: "100%", maxWidth: "100%", height: "auto", display: "block" }}
                  />
                  <div style={PDF_ONE_PAGE_MANUAL_LEGEND_WRAP} aria-hidden>
                    {monthlyOnePageLegendEntries.map((e, i) => (
                      <span
                        key={`${e.label}-${i}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        {e.variant === "line" ? (
                          <span
                            style={{
                              width: 18,
                              height: 3,
                              flexShrink: 0,
                              backgroundColor: e.color,
                              borderRadius: 1,
                            }}
                          />
                        ) : (
                          <span
                            style={{
                              width: 14,
                              height: 14,
                              flexShrink: 0,
                              backgroundColor: e.color,
                              borderRadius: 2,
                            }}
                          />
                        )}
                        {e.label}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                `${PDF_CHART_SECTION_TITLE_MONTHLY_PPM} 차트 이미지 영역 (추후 주입)`
              )}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

