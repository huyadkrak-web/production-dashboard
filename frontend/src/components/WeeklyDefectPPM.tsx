import React, { useEffect, useMemo, useRef, useState } from "react";
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
import type { WeeklyDefectPpmRow } from "../api";
import { getWeeklyDefectPpm, postWeeklyDefectPpm } from "../api";
import { PDF_CHART_SECTION_TITLE_WEEKLY_PPM } from "../pdfChartSectionTitles";
import demoWeeklyPpm from "../demo/demoWeeklyPpm.json";
import {
  alignWeeklyRowToColumns,
  chartDataKeyAt,
  defaultWeeklyUiRow,
  formatPpmKr,
  inferDefectColumnNamesIndexed,
  inferDefectColumnNamesUnion,
  isIndexedDefectLayout,
  isNullishChartNumber,
  normalizeWeeklyDefectPpmRow,
  num,
  rowHasNoChartableWeeklyPpm,
  mergeWeeklyDefectPpmData,
  padWeeklyLabelsForChartAxis,
  toSaveWeeklyRows,
  weeklyBarPpmFromCount,
  weeklyLinePpmFromTotals,
  type WeeklyRowUi,
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

type WeeklyChartTooltipProps = {
  active?: boolean;
  label?: React.ReactNode;
  payload?: ReadonlyArray<StackTooltipPayloadEntry>;
};

function ChartTooltip({ active, payload, label }: WeeklyChartTooltipProps) {
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
      <div style={{ marginBottom: 6, fontWeight: 600 }}>주차 {label}</div>
      {visible.map((entry: StackTooltipPayloadEntry) => (
        <div key={String(entry.dataKey)} style={{ color: entry.color }}>
          {entry.name}: {formatPpmKr(num(entry.value))}
        </div>
      ))}
    </div>
  );
}

const WEEKLY_X_TICK = { fill: "#1e293b", fontSize: 15, fontWeight: 600 };
const WEEKLY_Y_TICK = { fill: "#1e293b", fontSize: 14, fontWeight: 600 };
const WEEKLY_AXIS_STROKE = "#64748b";

function WeeklyChartManualLegend({ labels }: { labels: string[] }) {
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

type WeeklyDefectPPMProps = {
  forceFixedChartSize?: boolean;
  pdfExportMode?: boolean;
  onPdfLegendEntriesChange?: (entries: readonly WeeklyPdfLegendEntry[]) => void;
  /** ``/defect-auto/compute`` 성공 시 부모가 내려주는 주차 자동 집계(동일 week 덮어쓰기) */
  defectAutoMergeWeekly?: { token: number; rows: unknown[] } | null;
};

const WeeklyDefectPPM = React.forwardRef<HTMLDivElement, WeeklyDefectPPMProps>(
  (props, ref) => {
    const {
      forceFixedChartSize = false,
      pdfExportMode = false,
      onPdfLegendEntriesChange,
      defectAutoMergeWeekly = null,
    } = props;
    const [defectColumnNames, setDefectColumnNames] = useState<string[]>([""]);
    const [rows, setRows] = useState<WeeklyRowUi[]>([]);
    const [error, setError] = useState<string | null>(null);
    const tableCaptureRef = useRef<HTMLDivElement | null>(null);
    const chartCaptureRef = useRef<HTMLDivElement | null>(null);

    const rowsRef = useRef(rows);
    const defectColsRef = useRef(defectColumnNames);
    rowsRef.current = rows;
    defectColsRef.current = defectColumnNames;

    const prevDefectAutoWeeklyTokenRef = useRef<number | null>(null);
    useEffect(() => {
      if (!defectAutoMergeWeekly?.rows?.length) return;
      if (defectAutoMergeWeekly.token === prevDefectAutoWeeklyTokenRef.current) return;
      prevDefectAutoWeeklyTokenRef.current = defectAutoMergeWeekly.token;
      const m = mergeWeeklyDefectPpmData(
        rowsRef.current,
        defectColsRef.current,
        defectAutoMergeWeekly.rows,
      );
      setDefectColumnNames(m.cols);
      setRows(m.rows);
    }, [defectAutoMergeWeekly]);

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
      const baseChartRows = rows
        .filter((r) => r.week && String(r.week).trim())
        .map((r) => {
          const empty = rowHasNoChartableWeeklyPpm(r, chartColumnIndices);
          const ao = num(r.ao_qty);
          const linePpm = weeklyLinePpmFromTotals(ao, r.defect_total);
          const out: Record<string, unknown> = {
            week: String(r.week).trim(),
            total_ppm: empty || linePpm == null ? null : linePpm,
          };
          chartColumnIndices.forEach((colIdx, chartPos) => {
            const barPpm = weeklyBarPpmFromCount(ao, r.defectValues[colIdx]);
            out[chartDataKeyAt(chartPos)] = empty || barPpm == null ? null : barPpm;
          });
          return out;
        });

      const rowsLabelsActual = baseChartRows.map((d) => String(d.week ?? ""));
      const expandedLabelsForAxis = padWeeklyLabelsForChartAxis(rowsLabelsActual, 3);

      const byLabel = new Map<string, Record<string, unknown>>();
      for (const row of baseChartRows) {
        byLabel.set(String(row.week), row);
      }

      const merged = expandedLabelsForAxis.map((lbl) => {
        const hit = byLabel.get(lbl);
        if (hit) return hit;
        const placeholder: Record<string, unknown> = { week: lbl, total_ppm: null };
        chartColumnIndices.forEach((_, chartPos) => {
          placeholder[chartDataKeyAt(chartPos)] = null;
        });
        return placeholder;
      });

      return merged;
    }, [rows, chartColumnIndices]);

    const barCategoryGap = useMemo(
      () => defectPpmBarCategoryGap(chartData.length),
      [chartData.length],
    );
    const xAxisPadding = useMemo(() => defectPpmXAxisPaddingPx(chartData.length), [chartData.length]);

    useEffect(() => {
      if (!chartData.length) return;
      console.log("[DefectPpmChart][weekly] bar layout", getDefectPpmBarLayoutOptions(chartData.length));
    }, [chartData.length]);

    function applyLoadedNormalized(normalized: WeeklyDefectPpmRow[]) {
      const indexed = isIndexedDefectLayout(normalized);
      const inferred = indexed
        ? inferDefectColumnNamesIndexed(normalized)
        : inferDefectColumnNamesUnion(normalized);
      const cols = inferred.length > 0 ? inferred : [""];
      const uiRows = normalized.map((r) => alignWeeklyRowToColumns(r, cols, indexed));
      setDefectColumnNames(cols);
      setRows(uiRows);
    }

    async function load() {
      setError(null);
      try {
        const fromApi = await getWeeklyDefectPpm();
        if (Array.isArray(fromApi) && fromApi.length > 0) {
          applyLoadedNormalized(
            fromApi.map((row) => normalizeWeeklyDefectPpmRow(row as Record<string, unknown>)),
          );
          return;
        }
      } catch {
        /* API 없을 때 데모로 폴백 */
      }
      try {
        const raw = demoWeeklyPpm as Record<string, unknown>[];
        if (Array.isArray(raw) && raw.length > 0) {
          applyLoadedNormalized(raw.map(normalizeWeeklyDefectPpmRow));
        } else {
          setDefectColumnNames([""]);
          setRows([defaultWeeklyUiRow(1)]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    async function save() {
      setError(null);
      try {
        await postWeeklyDefectPpm(toSaveWeeklyRows(rows, defectColumnNames));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    const hasChart = chartData.length > 0 && chartLabels.length > 0;

    return (
      <section className="card" ref={ref}>
        <h2 className="cardTitle">주차별 불량 ppm 관리</h2>
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
            불러오기
          </button>
          <button type="button" className="button" onClick={() => void save()}>
            저장
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
            <table className="table defect-ppm-compact-table weekly-defect-compact-table">
              <thead>
                <tr>
                  <th>주차</th>
                  <th style={{ textAlign: "center" }}>AO 수량</th>
                  <th style={{ textAlign: "center" }}>불량합(개)</th>
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
                    <td colSpan={defectColumnNames.length + 4} className="emptyCell">
                      데이터가 없습니다. 불러오기를 누르세요.
                    </td>
                  </tr>
                ) : (
                  rows.map((row, i) => {
                    const ppmLine = weeklyLinePpmFromTotals(row.ao_qty, row.defect_total);
                    const ppmDisplay =
                      ppmLine == null || !Number.isFinite(ppmLine)
                        ? ""
                        : ppmLine === 0
                          ? ""
                          : formatPpmKr(ppmLine);
                    return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{String(row.week || "")}</td>
                      <td style={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}>
                        {num(row.ao_qty) === 0 ? "" : num(row.ao_qty).toLocaleString("ko-KR")}
                      </td>
                      <td style={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}>
                        {num(row.defect_total) === 0 ? "" : String(Math.round(num(row.defect_total)))}
                      </td>
                      <td style={{ textAlign: "center", fontVariantNumeric: "tabular-nums", color: "#ef4444" }}>
                        {ppmDisplay}
                      </td>
                      {defectColumnNames.map((_, ci) => (
                        <td key={ci} style={{ textAlign: "center" }}>
                          {num(row.defectValues[ci]) === 0
                            ? ""
                            : String(Math.round(num(row.defectValues[ci])))}
                        </td>
                      ))}
                    </tr>
                    );
                  })
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
                <PdfReportIconBadge Icon={ChartColumn} title={PDF_CHART_SECTION_TITLE_WEEKLY_PPM} />
              ) : null}
              <span>
                {pdfExportMode ? PDF_CHART_SECTION_TITLE_WEEKLY_PPM : "주차별 불량 ppm 현황"}
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
                        dataKey="week"
                        tick={WEEKLY_X_TICK}
                        tickLine={{ stroke: WEEKLY_AXIS_STROKE }}
                        axisLine={{ stroke: WEEKLY_AXIS_STROKE }}
                        tickMargin={14}
                        interval={0}
                        padding={xAxisPadding}
                      />
                      <YAxis
                        tick={WEEKLY_Y_TICK}
                        tickLine={{ stroke: WEEKLY_AXIS_STROKE }}
                        axisLine={{ stroke: WEEKLY_AXIS_STROKE }}
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
                    <WeeklyChartManualLegend labels={chartLabels} />
                  </>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={DEFECT_PPM_PLOT_HEIGHT}>
                      <ComposedChart data={chartData} margin={DEFECT_PPM_COMPOSED_CHART_MARGIN} barCategoryGap={barCategoryGap}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                        <XAxis
                          dataKey="week"
                          tick={WEEKLY_X_TICK}
                          tickLine={{ stroke: WEEKLY_AXIS_STROKE }}
                          axisLine={{ stroke: WEEKLY_AXIS_STROKE }}
                          tickMargin={14}
                          interval={0}
                          padding={xAxisPadding}
                        />
                        <YAxis
                          tick={WEEKLY_Y_TICK}
                          tickLine={{ stroke: WEEKLY_AXIS_STROKE }}
                          axisLine={{ stroke: WEEKLY_AXIS_STROKE }}
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
                    <WeeklyChartManualLegend labels={chartLabels} />
                  </>
                )}
              </div>
            </div>
          </div>
        ) : chartData.length > 0 && chartLabels.length === 0 ? (
          <div className="hint" style={{ marginTop: 12 }}>
            주차는 입력되었으나 불량 컬럼명이 비어 있습니다. 헤더에 불량명을 입력하면 그래프가 표시됩니다.
          </div>
        ) : (
          <div className="hint" style={{ marginTop: 12 }}>
            주차·불량 데이터를 입력하면 그래프가 표시됩니다.
          </div>
        )}
      </section>
    );
  },
);

WeeklyDefectPPM.displayName = "WeeklyDefectPPM";
export default WeeklyDefectPPM;
