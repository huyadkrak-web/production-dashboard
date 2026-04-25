import React from "react";
import type { LucideIcon } from "lucide-react";
import { PdfReportIconBadge } from "./PdfReportIconBadge";

export default function DataTable<T extends Record<string, unknown>>(props: {
  title: string;
  titleMarker?: { text: string; color?: string };
  /** PDF(html2canvas) 캡처 시에만 제목 앞에 SVG 배지 표시 */
  pdfExportMode?: boolean;
  pdfSectionIcon?: LucideIcon;
  tableClassName?: string;
  columns: ReadonlyArray<{
    key: keyof T;
    label: string;
    align?: "left" | "right" | "center";
    render?: (args: {
      row: T;
      rowIndex: number;
      rows: ReadonlyArray<T>;
      raw: unknown;
      formatted: React.ReactNode;
    }) =>
      | {
          node: React.ReactNode;
          rowSpan?: number;
          colSpan?: number;
          skip?: boolean;
          align?: "left" | "right" | "center";
        }
      | React.ReactNode;
  }>;
  rows: ReadonlyArray<T>;
  format?: Partial<Record<keyof T, (v: unknown) => React.ReactNode>>;
}) {
  const { title, titleMarker, pdfExportMode, pdfSectionIcon, tableClassName, columns, rows, format } = props;
  const showPdfBadge = Boolean(pdfExportMode && pdfSectionIcon);
  return (
    <section className="card">
      <div
        className={
          pdfExportMode ? "cardHeader pdf-section-title-panel" : "cardHeader"
        }
      >
        <h2
          className={
            showPdfBadge ? "cardTitle pdf-report-section-title" : "cardTitle"
          }
        >
          {showPdfBadge && pdfSectionIcon ? (
            <>
              <PdfReportIconBadge Icon={pdfSectionIcon} title={title} />
              <span className="pdf-report-section-title-text">{title}</span>
              {titleMarker ? (
                <span
                  style={{
                    fontSize: 10,
                    marginLeft: 6,
                    color: titleMarker.color ?? "#334155",
                    fontWeight: 600,
                  }}
                >
                  {titleMarker.text}
                </span>
              ) : null}
            </>
          ) : (
            <>
              {title}
              {titleMarker ? (
                <span
                  style={{
                    fontSize: 10,
                    marginLeft: 6,
                    color: titleMarker.color ?? "#334155",
                    fontWeight: 600,
                  }}
                >
                  {titleMarker.text}
                </span>
              ) : null}
            </>
          )}
        </h2>
        <div className="cardMeta">{rows.length} rows</div>
      </div>
      <div className="tableWrap">
        <table className={tableClassName ? `table ${tableClassName}` : "table"}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={String(c.key)} style={{ textAlign: c.align ?? "left" }}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="emptyCell" colSpan={columns.length}>
                  데이터가 없습니다.
                </td>
              </tr>
            ) : (
              rows.map((r, i) => (
                <tr key={i}>
                  {columns.map((c, colIndex) => {
                    const raw = r[c.key];
                    const cell = format?.[c.key]?.(raw) ?? String(raw ?? "");
                    const rendered = c.render?.({
                      row: r,
                      rowIndex: i,
                      rows,
                      raw,
                      formatted: cell,
                    });

                    if (rendered && typeof rendered === "object" && "skip" in rendered && rendered.skip) {
                      return null;
                    }

                    const node =
                      rendered && typeof rendered === "object" && "node" in rendered
                        ? rendered.node
                        : rendered ?? cell;
                    const rowSpan =
                      rendered && typeof rendered === "object" && "rowSpan" in rendered
                        ? rendered.rowSpan
                        : undefined;
                    const colSpan =
                      rendered && typeof rendered === "object" && "colSpan" in rendered
                        ? rendered.colSpan
                        : undefined;
                    const align =
                      rendered && typeof rendered === "object" && "align" in rendered
                        ? rendered.align
                        : c.align ?? "left";

                    const multiline =
                      typeof node === "string" && (node.includes("\n") || node.includes("\r"));
                    const isLastColumn = colIndex === columns.length - 1;
                    return (
                      <td
                        key={String(c.key)}
                        style={{ textAlign: align }}
                        rowSpan={rowSpan}
                        colSpan={colSpan}
                      >
                        {isLastColumn ? (
                          <div className="lastColumnContent">{multiline ? (
                            <div className="multilineCell">
                              {String(node)
                                .split(/\r?\n/)
                                .map((line, i) => (
                                  <div key={i}>{line || "-"}</div>
                                ))}
                            </div>
                          ) : (
                            node
                          )}</div>
                        ) : multiline ? (
                          <div className="multilineCell">
                            {String(node)
                              .split(/\r?\n/)
                              .map((line, i) => (
                                <div key={i}>{line || "-"}</div>
                              ))}
                          </div>
                        ) : (
                          node
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

