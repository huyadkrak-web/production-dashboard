import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChartColumn } from "lucide-react";
import { PdfReportIconBadge } from "./PdfReportIconBadge";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MonthlyDefectPpmRow } from "../api";
import { getWeeklyDefectPpm, postMonthlyDefectPpm } from "../api";
import { PDF_CHART_SECTION_TITLE_MONTHLY_PPM } from "../pdfChartSectionTitles";
import {
  aggregateWeeklyRowsByMonthLabel,
  alignMonthlyRowToColumns,
  chartDataKeyAt,
  formatPpmKr,
  padMonthlyLabelsForChartAxis,
  inferDefectColumnNamesUnion,
  isNullishChartNumber,
  monthLabelChronologicalSortKey,
  mergeMonthlyDefectPpmData,
  normalizeWeeklyDefectPpmRow,
  num,
  parseDefectApiMonthlyItems,
  rowHasNoChartableMonthlyPpm,
  toSaveMonthlyRows,
  weekToShipmentMonthLabel,
  type MonthlyRowUi,
} from "../defectPpmBoardShared";
import {
  DEFECT_PPM_COMPOSED_CHART_MARGIN,
  DEFECT_PPM_FIXED_CHART_WIDTH,
  DEFECT_PPM_PLOT_HEIGHT,
  WEEKLY_DEFECT_STACK_COLORS,
  WEEKLY_TOTAL_PPM_LINE_COLOR,
  buildWeeklyPdfLegendEntries,
  defectPpmBarCategoryGap,
  defectPpmXAxisPaddingPx,
  getDefectPpmBarLayoutOptions,
  type WeeklyPdfLegendEntry,
} from "../weeklyDefectPpmShared";

const PPM_MIN_LABEL = 50;

const LINE_STROKE_WIDTH = 3;
const TOTAL_PPM_LABEL_FONT_SIZE = 17;
const TOTAL_PPM_LABEL_FONT_WEIGHT = 700;

type StackTooltipPayloadEntry = {
  name?: string;
  value?: number;
  dataKey?: string | number;
  color?: string;
  payload?: Record<string, unknown>;
};

type MonthlyChartTooltipProps = {
  active?: boolean;
  label?: React.ReactNode;
  payload?: ReadonlyArray<StackTooltipPayloadEntry>;
};

type MonthlyChartSourceRow = MonthlyRowUi & Record<string, unknown>;

function ChartTooltip({ active, payload, label }: MonthlyChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const visible = payload.filter((e) => !isNullishChartNumber(e.value));
  if (!visible.length) return null;
  return (
    <div
      className="card"
      style={{
        padding: "10px 12px",
        minWidth: 160,
        fontSize: 12,
        backgroundColor: "#ffffff",
        border: "1px solid #ddd",
      }}
    >
      <div style={{ marginBottom: 6, fontWeight: 600 }}>월 {label}</div>
      {visible.map((entry: StackTooltipPayloadEntry) => (
        <div key={String(entry.dataKey)} style={{ color: entry.color }}>
          {entry.name}: {formatPpmKr(num(entry.value))}
        </div>
      ))}
    </div>
  );
}

const MONTHLY_X_TICK = { fill: "#1e293b", fontSize: 15, fontWeight: 600 };
const MONTHLY_Y_TICK = { fill: "#1e293b", fontSize: 14, fontWeight: 600 };
const MONTHLY_AXIS_STROKE = "#64748b";

function readMonthlyLabel(row: MonthlyChartSourceRow): string {
  const fallback = row.month ?? row.week ?? row["월"] ?? row.month_label;
  return String(row.label ?? fallback ?? "").trim();
}

function readMonthlyDefectValue(
  row: MonthlyChartSourceRow,
  colIdx: number,
  columnName: string,
): number {
  if (Array.isArray(row.defectValues)) {
    return num(row.defectValues[colIdx]);
  }
  if (Array.isArray(row.defects)) {
    const byIndex = row.defects[colIdx];
    if (byIndex && typeof byIndex === "object") {
      const value = num((byIndex as Record<string, unknown>).value);
      if (value !== 0) return value;
    }
    const byName = row.defects.find((item) => {
      if (!item || typeof item !== "object") return false;
      return String((item as Record<string, unknown>).name ?? "").trim() === columnName;
    });
    if (byName && typeof byName === "object") {
      return num((byName as Record<string, unknown>).value);
    }
  }
  if (columnName !== "") {
    return num(row[columnName]);
  }
  return 0;
}

function MonthlyChartManualLegend({ labels }: { labels: string[] }) {
  return (
    <div
      className="weekly-defect-manual-legend"
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        gap: "8px 16px",
        padding: "10px 12px 8px",
        fontSize: 12,
        fontWeight: 600,
        color: "#0f172a",
        lineHeight: 1.35,
        borderTop: "1px solid #e2e8f0",
        background: "#ffffff",
        boxSizing: "border-box",
        width: "100%",
        maxWidth: "100%",
      }}
    >
      {labels.map((lab, idx) => (
        <span key={`${lab}-${idx}`} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 14,
              height: 14,
              flexShrink: 0,
              backgroundColor: WEEKLY_DEFECT_STACK_COLORS[idx % WEEKLY_DEFECT_STACK_COLORS.length],
              borderRadius: 2,
            }}
            aria-hidden
          />
          {lab}
        </span>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            width: 18,
            height: 3,
            flexShrink: 0,
            backgroundColor: WEEKLY_TOTAL_PPM_LINE_COLOR,
            borderRadius: 1,
          }}
          aria-hidden
        />
        총 불량율(ppm)
      </span>
    </div>
  );
}

type MonthlyDefectPPMProps = {
  forceFixedChartSize?: boolean;
  pdfExportMode?: boolean;
  onPdfLegendEntriesChange?: (entries: readonly WeeklyPdfLegendEntry[]) => void;
  /** `WWnn` → 월 라벨 매핑 시 ISO 주차 연도(기본 UTC 현재 연도). 대시보드 기준일 연도와 맞추면 좋음 */
  weekIsoReferenceYear?: number;
  /** ``/defect-auto/compute`` 월 집계(동일 월 label 덮어쓰기) */
  defectAutoMergeMonthly?: { token: number; rows: unknown[] } | null;
};

const MonthlyDefectPPM = React.forwardRef<HTMLDivElement, MonthlyDefectPPMProps>(
  (props, ref) => {
    const {
      forceFixedChartSize = false,
      pdfExportMode = false,
      onPdfLegendEntriesChange,
      weekIsoReferenceYear,
      defectAutoMergeMonthly = null,
    } = props;
    const [defectColumnNames, setDefectColumnNames] = useState<string[]>([""]);
    const [rows, setRows] = useState<MonthlyRowUi[]>([]);
    const [error, setError] = useState<string | null>(null);
    const tableCaptureRef = useRef<HTMLDivElement | null>(null);
    const chartCaptureRef = useRef<HTMLDivElement | null>(null);

    const rowsRef = useRef(rows);
    const defectColsRef = useRef(defectColumnNames);
    rowsRef.current = rows;
    defectColsRef.current = defectColumnNames;

    const defectAutoMergeRef = useRef(defectAutoMergeMonthly);
    defectAutoMergeRef.current = defectAutoMergeMonthly;

    const runDefectAutoMonthlyMerge = useCallback(() => {
      const p = defectAutoMergeRef.current;
      if (!p?.rows?.length) return;
      const inc = parseDefectApiMonthlyItems(p.rows);
      if (inc.length === 0) return;
      const aoByLabel = new Map<string, number>();
      for (const r of p.rows) {
        if (!r || typeof r !== "object") continue;
        const o = r as Record<string, unknown>;
        const lb = String(o.month ?? o.label ?? "").trim();
        if (!lb) continue;
        aoByLabel.set(lb, num(o.ao_qty));
      }
      const m = mergeMonthlyDefectPpmData(
        rowsRef.current,
        defectColsRef.current,
        inc,
        aoByLabel,
      );
      setDefectColumnNames(m.cols);
      setRows(m.rows);
    }, []);

    const prevDefectAutoMonthlyTokenRef = useRef<number | null>(null);
    useEffect(() => {
      if (!defectAutoMergeMonthly?.rows?.length) return;
      if (defectAutoMergeMonthly.token === prevDefectAutoMonthlyTokenRef.current) return;
      prevDefectAutoMonthlyTokenRef.current = defectAutoMergeMonthly.token;
      setTimeout(() => {
        runDefectAutoMonthlyMerge();
      }, 0);
    }, [defectAutoMergeMonthly, runDefectAutoMonthlyMerge]);

    const chartColumnIndices = useMemo(
      () =>
        defectColumnNames
          .map((n, i) => (String(n).trim() !== "" ? i : -1))
          .filter((i) => i >= 0),
      [defectColumnNames],
    );

    const chartLabels = useMemo(
      () => chartColumnIndices.map((i) => String(defectColumnNames[i]).trim()),
      [chartColumnIndices, defectColumnNames],
    );

    useEffect(() => {
      onPdfLegendEntriesChange?.(buildWeeklyPdfLegendEntries(chartLabels));
    }, [chartLabels, onPdfLegendEntriesChange]);

    const chartData = useMemo(() => {
      const series = rows
        .map((r) => r as MonthlyChartSourceRow)
        .map((r, rowIdx) => {
          const label = readMonthlyLabel(r);
          const defectValues = defectColumnNames.map((name, idx) =>
            readMonthlyDefectValue(r, idx, String(name ?? "").trim()),
          );
          const totalPpm = num(r.total_ppm ?? r.ppm);
          const hasPpmData = totalPpm !== 0 || defectValues.some((v) => num(v) !== 0);
          const safeLabel = label !== "" ? label : hasPpmData ? `월 미입력 ${rowIdx + 1}` : "";
          return { label: safeLabel, total_ppm: totalPpm, defectValues };
        })
        .filter((r) => r.label !== "")
        .sort(
          (a, b) =>
            monthLabelChronologicalSortKey(a.label) - monthLabelChronologicalSortKey(b.label),
        );

      const baseChartRows: Record<string, unknown>[] = series.map((r) => {
        const empty = rowHasNoChartableMonthlyPpm(r, chartColumnIndices);
        const out: Record<string, unknown> = {
          label: r.label,
          total_ppm: empty ? null : num(r.total_ppm),
        };
        chartColumnIndices.forEach((colIdx, chartPos) => {
          out[chartDataKeyAt(chartPos)] = empty ? null : num(r.defectValues[colIdx]);
        });
        return out;
      });

      const rowsLabelsActual = baseChartRows.map((d) => String(d.label ?? ""));
      const expandedLabelsForAxis = padMonthlyLabelsForChartAxis(rowsLabelsActual, 3);

      console.log("[MonthlyDefectPPM] month axis labels", {
        rowsLabelsActual,
        expandedLabelsForAxis,
      });

      const byLabel = new Map<string, Record<string, unknown>>();
      for (const row of baseChartRows) {
        byLabel.set(String(row.label), row);
      }

      const merged = expandedLabelsForAxis.map((lbl) => {
        const hit = byLabel.get(lbl);
        if (hit) return hit;
        const placeholder: Record<string, unknown> = { label: lbl, total_ppm: null };
        chartColumnIndices.forEach((_, chartPos) => {
          placeholder[chartDataKeyAt(chartPos)] = null;
        });
        return placeholder;
      });

      return merged;
    }, [rows, chartColumnIndices, defectColumnNames]);

    const hasChart = chartData.length > 0 && chartLabels.length > 0;

    useEffect(() => {
      if (!chartData.length || !chartLabels.length) return;
      const d0 = chartData[0] as Record<string, unknown>;
      console.log("[MonthlyDefectPPM] pre-render", {
        sampleChartRow: d0,
        labels: chartData.map((d) => String((d as Record<string, unknown>).label ?? "")),
        chartLabelsCount: chartLabels.length,
        stackedDatasetCount: chartLabels.length,
        chartRowCount: chartData.length,
      });
    }, [chartData, chartLabels]);

    const barCategoryGap = useMemo(
      () => defectPpmBarCategoryGap(chartData.length),
      [chartData.length],
    );
    const xAxisPadding = useMemo(() => defectPpmXAxisPaddingPx(chartData.length), [chartData.length]);

    useEffect(() => {
      if (!chartData.length) return;
      console.log("[DefectPpmChart][monthly] bar layout", getDefectPpmBarLayoutOptions(chartData.length));
    }, [chartData.length]);

    const applyLoadedNormalized = useCallback((normalized: MonthlyDefectPpmRow[]) => {
      if (normalized.length === 0) {
        setDefectColumnNames([""]);
        setRows([]);
        return;
      }
      const inferred = inferDefectColumnNamesUnion(normalized);
      const cols = inferred.length > 0 ? inferred : [""];
      const uiRows = normalized.map((r) => alignMonthlyRowToColumns(r, cols, false));
      setDefectColumnNames(cols);
      setRows(uiRows);
    }, []);

    const load = useCallback(async () => {
      setError(null);
      try {
        const fromApi = await getWeeklyDefectPpm();
        if (!Array.isArray(fromApi) || fromApi.length === 0) {
          applyLoadedNormalized([]);
        } else {
          const normalizedWeekly = fromApi.map((row) =>
            normalizeWeeklyDefectPpmRow(row as Record<string, unknown>),
          );
          const monthlyMerged = aggregateWeeklyRowsByMonthLabel(normalizedWeekly, (wk) =>
            weekToShipmentMonthLabel(wk, weekIsoReferenceYear),
          );
          applyLoadedNormalized(monthlyMerged);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        applyLoadedNormalized([]);
      }
      setTimeout(() => {
        if (defectAutoMergeRef.current?.rows?.length) {
          runDefectAutoMonthlyMerge();
        }
      }, 0);
    }, [weekIsoReferenceYear, applyLoadedNormalized, runDefectAutoMonthlyMerge]);

    async function save() {
      setError(null);
      try {
        await postMonthlyDefectPpm(toSaveMonthlyRows(rows, defectColumnNames));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    return (
      <section className="card" ref={ref}>
        <h2 className="cardTitle">월별 조립 불량율(ppm) 관리</h2>
        <p className="hint" style={{ marginBottom: 10 }}>
          주차별 원데이터(ao_qty·defect_total·불량 건수)를 월 라벨로 묶어 합산한 뒤 PPM으로 표시합니다. 월
          라벨은 주차 문자열이 <code>26.4</code> 형태이면 그대로 쓰고, <code>WW16</code> 형태이면 기준 연도
          기준 ISO 주차에 해당하는 달로 매핑합니다.
        </p>
        <div
          className="actions"
          style={{
            marginBottom: 8,
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <button type="button" className="button" onClick={() => void load()}>
            주차 데이터에서 불러오기
          </button>
          <button type="button" className="button" onClick={() => void save()}>
            집계 결과 저장
          </button>
        </div>

        {error ? (
          <div className="hint" style={{ color: "var(--danger)", marginBottom: 8 }}>
            {error}
          </div>
        ) : null}

        <div
          className="weekly-defect-table-capture-target"
          ref={tableCaptureRef}
          style={{
            background: "#ffffff",
            overflowX: "auto",
            maxWidth: "100%",
            minWidth: 0,
            minHeight: 80,
          }}
        >
          <div className="tableWrap" style={{ overflowX: "hidden", marginBottom: 16, maxWidth: "100%" }}>
            <table className="table defect-ppm-compact-table monthly-defect-compact-table">
              <thead>
                <tr>
                  <th>월</th>
                  <th style={{ textAlign: "center" }}>불량율(ppm)</th>
                  {defectColumnNames.map((colName, ci) => (
                    <th key={ci} style={{ textAlign: "center", minWidth: 0 }}>
                      {String(colName).trim() !== "" ? colName : "—"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={Math.max(2, defectColumnNames.length + 2)} className="emptyCell">
                      주차별 카드에서 데이터를 저장한 뒤, 위의「주차 데이터에서 불러오기」를 누르세요. 주차
                      문자열이 월로 매핑되지 않으면 여기에 표시되지 않습니다.
                    </td>
                  </tr>
                ) : (
                  rows.map((row, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{row.label}</td>
                      <td style={{ textAlign: "center", fontVariantNumeric: "tabular-nums", color: "#ef4444" }}>
                        {num(row.total_ppm) === 0 ? "" : formatPpmKr(num(row.total_ppm))}
                      </td>
                      {defectColumnNames.map((_, ci) => (
                        <td
                          key={ci}
                          style={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}
                        >
                          {num(row.defectValues[ci]) === 0 ? "" : formatPpmKr(num(row.defectValues[ci]))}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {hasChart ? (
          <div
            className={["weekly-defect-chart-capture-target", pdfExportMode ? "pdf-chart-as-card" : ""]
              .filter(Boolean)
              .join(" ")}
            ref={chartCaptureRef}
            style={
              forceFixedChartSize
                ? {
                    background: "#ffffff",
                    overflow: "visible",
                    paddingTop: 8,
                    width: DEFECT_PPM_FIXED_CHART_WIDTH,
                    minWidth: DEFECT_PPM_FIXED_CHART_WIDTH,
                    maxWidth: DEFECT_PPM_FIXED_CHART_WIDTH,
                  }
                : {
                    background: "#ffffff",
                    overflow: "visible",
                    minHeight: 120,
                    paddingTop: 8,
                    width: "100%",
                  }
            }
          >
            <div
              className={pdfExportMode ? "pdf-report-heading-row pdf-section-title-panel" : undefined}
              style={{
                fontWeight: 600,
                fontSize: 16,
                marginBottom: pdfExportMode ? 0 : 8,
                width: "100%",
                textAlign: "left",
              }}
            >
              {pdfExportMode ? (
                <PdfReportIconBadge Icon={ChartColumn} title={PDF_CHART_SECTION_TITLE_MONTHLY_PPM} />
              ) : null}
              <span>
                {pdfExportMode ? PDF_CHART_SECTION_TITLE_MONTHLY_PPM : "월별 조립 불량율(ppm) 현황"}
              </span>
            </div>
            <div
              className={
                forceFixedChartSize
                  ? "weekly-defect-ppm-chart weekly-defect-ppm-chart-fixed"
                  : "weekly-defect-ppm-chart"
              }
              style={
                forceFixedChartSize
                  ? {
                      width: DEFECT_PPM_FIXED_CHART_WIDTH,
                      marginTop: 16,
                      minWidth: DEFECT_PPM_FIXED_CHART_WIDTH,
                      maxWidth: DEFECT_PPM_FIXED_CHART_WIDTH,
                      minHeight: DEFECT_PPM_PLOT_HEIGHT + 96,
                    }
                  : { width: "100%", minHeight: 480, marginTop: 16 }
              }
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "stretch",
                  width: "100%",
                  maxWidth: forceFixedChartSize ? DEFECT_PPM_FIXED_CHART_WIDTH : "100%",
                }}
              >
                {forceFixedChartSize ? (
                  <>
                    <ComposedChart
                      width={DEFECT_PPM_FIXED_CHART_WIDTH}
                      height={DEFECT_PPM_PLOT_HEIGHT}
                      data={chartData}
                      margin={DEFECT_PPM_COMPOSED_CHART_MARGIN}
                      barCategoryGap={barCategoryGap}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                      <XAxis
                        dataKey="label"
                        tick={MONTHLY_X_TICK}
                        tickLine={{ stroke: MONTHLY_AXIS_STROKE }}
                        axisLine={{ stroke: MONTHLY_AXIS_STROKE }}
                        tickMargin={14}
                        interval={0}
                        padding={xAxisPadding}
                      />
                      <YAxis
                        tick={MONTHLY_Y_TICK}
                        tickLine={{ stroke: MONTHLY_AXIS_STROKE }}
                        axisLine={{ stroke: MONTHLY_AXIS_STROKE }}
                        tickMargin={10}
                        tickFormatter={(v) => formatPpmKr(Number(v))}
                      />
                      <Tooltip content={<ChartTooltip />} />
                      {chartLabels.map((lab, idx) => (
                        <Bar
                          key={chartDataKeyAt(idx)}
                          dataKey={chartDataKeyAt(idx)}
                          stackId="stack"
                          name={lab}
                          fill={WEEKLY_DEFECT_STACK_COLORS[idx % WEEKLY_DEFECT_STACK_COLORS.length]}
                          isAnimationActive={false}
                        >
                          <LabelList
                            dataKey={chartDataKeyAt(idx)}
                            position="center"
                            fontSize={10}
                            fill="rgba(0,0,0,0.75)"
                            formatter={(v: unknown) =>
                              isNullishChartNumber(v) || num(v) < PPM_MIN_LABEL
                                ? ""
                                : formatPpmKr(num(v))
                            }
                          />
                        </Bar>
                      ))}
                      <Line
                        type="monotone"
                        dataKey="total_ppm"
                        name="총 불량율(ppm)"
                        stroke={WEEKLY_TOTAL_PPM_LINE_COLOR}
                        strokeWidth={LINE_STROKE_WIDTH}
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                        connectNulls={false}
                        isAnimationActive={false}
                      >
                        <LabelList
                          dataKey="total_ppm"
                          position="top"
                          fontSize={TOTAL_PPM_LABEL_FONT_SIZE}
                          fontWeight={TOTAL_PPM_LABEL_FONT_WEIGHT}
                          formatter={(v: unknown) =>
                            isNullishChartNumber(v) ? "" : formatPpmKr(num(v))
                          }
                        />
                      </Line>
                    </ComposedChart>
                    <MonthlyChartManualLegend labels={chartLabels} />
                  </>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={DEFECT_PPM_PLOT_HEIGHT}>
                      <ComposedChart data={chartData} margin={DEFECT_PPM_COMPOSED_CHART_MARGIN} barCategoryGap={barCategoryGap}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                        <XAxis
                          dataKey="label"
                          tick={MONTHLY_X_TICK}
                          tickLine={{ stroke: MONTHLY_AXIS_STROKE }}
                          axisLine={{ stroke: MONTHLY_AXIS_STROKE }}
                          tickMargin={14}
                          interval={0}
                          padding={xAxisPadding}
                        />
                        <YAxis
                          tick={MONTHLY_Y_TICK}
                          tickLine={{ stroke: MONTHLY_AXIS_STROKE }}
                          axisLine={{ stroke: MONTHLY_AXIS_STROKE }}
                          tickMargin={10}
                          tickFormatter={(v) => formatPpmKr(Number(v))}
                        />
                        <Tooltip content={<ChartTooltip />} />
                        {chartLabels.map((lab, idx) => (
                          <Bar
                            key={chartDataKeyAt(idx)}
                            dataKey={chartDataKeyAt(idx)}
                            stackId="stack"
                            name={lab}
                            fill={WEEKLY_DEFECT_STACK_COLORS[idx % WEEKLY_DEFECT_STACK_COLORS.length]}
                          >
                            <LabelList
                              dataKey={chartDataKeyAt(idx)}
                              position="center"
                              fontSize={10}
                              fill="rgba(0,0,0,0.75)"
                              formatter={(v: unknown) =>
                                isNullishChartNumber(v) || num(v) < PPM_MIN_LABEL
                                  ? ""
                                  : formatPpmKr(num(v))
                              }
                            />
                          </Bar>
                        ))}
                        <Line
                          type="monotone"
                          dataKey="total_ppm"
                          name="총 불량율(ppm)"
                          stroke={WEEKLY_TOTAL_PPM_LINE_COLOR}
                          strokeWidth={LINE_STROKE_WIDTH}
                          dot={{ r: 4 }}
                          activeDot={{ r: 6 }}
                          connectNulls={false}
                        >
                          <LabelList
                            dataKey="total_ppm"
                            position="top"
                            fontSize={TOTAL_PPM_LABEL_FONT_SIZE}
                            fontWeight={TOTAL_PPM_LABEL_FONT_WEIGHT}
                            formatter={(v: unknown) =>
                              isNullishChartNumber(v) ? "" : formatPpmKr(num(v))
                            }
                          />
                        </Line>
                      </ComposedChart>
                    </ResponsiveContainer>
                    <MonthlyChartManualLegend labels={chartLabels} />
                  </>
                )}
              </div>
            </div>
          </div>
        ) : chartData.length > 0 && chartLabels.length === 0 ? (
          <div className="hint" style={{ marginTop: 12 }}>
            월별 집계는 있으나 불량명 컬럼이 비어 있습니다. 주차별 불량명이 비어 있지 않은지 확인하세요.
          </div>
        ) : (
          <div className="hint" style={{ marginTop: 12 }}>
            주차별 데이터를 불러오면 월별 그래프가 표시됩니다.
          </div>
        )}
      </section>
    );
  },
);

MonthlyDefectPPM.displayName = "MonthlyDefectPPM";
export default MonthlyDefectPPM;
