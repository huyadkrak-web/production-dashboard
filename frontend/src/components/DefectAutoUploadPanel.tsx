import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  computeDefectAuto,
  getDefectAutoShipmentMoveDates,
  getDefectAutoShipmentSummary,
  postDefectAutoReset,
  type DefectAutoShipmentMoveDateRow,
  type DefectAutoShipmentSummary,
  uploadDefectShipment,
} from "../api";

type DefectAutoUploadPanelProps = {
  onComputeSuccess?: (weekly: unknown[], monthly: unknown[]) => void;
  /** 출하·주·월·LOT 자동 데이터 초기화 후, 차트 병합 상태도 비울 때 사용 */
  onResetSuccess?: (weekly: unknown[], monthly: unknown[]) => void;
  workFile: File | null;
  /** 입력 카드에서 선택한 코드별 불량현황; compute 시 defect_file로 전송 */
  codeDefectFile: File | null;
};

/** 입력 카드 `INPUT_FILE_INPUT_WRAP`과 동일 */
const SHIPMENT_FILE_INPUT_WRAP: CSSProperties = {
  width: "68%",
  maxWidth: "28rem",
  minWidth: "9rem",
  flexShrink: 0,
};

/** move_date 일자별 rollup → YYYY-MM 단위 합산(행 수·이동수량). UI 전용. */
function aggregateShipmentRollupsByMonth(
  rollups: DefectAutoShipmentMoveDateRow[],
): { ym: string; rowCount: number; totalQty: number }[] {
  const byMonth = new Map<string, { rowCount: number; totalQty: number }>();
  for (const r of rollups) {
    const ds = String(r.date ?? "").trim();
    if (!ds) continue;
    const ym = ds.slice(0, 7);
    if (!/^\d{4}-\d{2}$/.test(ym)) continue;
    const cur = byMonth.get(ym) ?? { rowCount: 0, totalQty: 0 };
    cur.rowCount += Number(r.row_count) || 0;
    cur.totalQty += Number(r.total_qty) || 0;
    byMonth.set(ym, cur);
  }
  return [...byMonth.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([ym, v]) => ({ ym, rowCount: v.rowCount, totalQty: v.totalQty }));
}

/**
 * 공정불량 자동화: 출하 업로드, compute 시 부모에 weekly/monthly 전달(표 병합).
 * 작업일보·코드별 불량현황 파일은 입력 카드에서 선택합니다.
 */
export default function DefectAutoUploadPanel({
  onComputeSuccess,
  onResetSuccess,
  workFile,
  codeDefectFile,
}: DefectAutoUploadPanelProps) {
  const [shipmentFile, setShipmentFile] = useState<File | null>(null);
  const [shipmentFileInputKey, setShipmentFileInputKey] = useState(0);
  const [defectAutoMessage, setDefectAutoMessage] = useState<string>("");
  const [defectAutoLoading, setDefectAutoLoading] = useState(false);
  const [shipmentSummary, setShipmentSummary] = useState<DefectAutoShipmentSummary | null>(null);
  const [moveDateRollups, setMoveDateRollups] = useState<DefectAutoShipmentMoveDateRow[]>([]);
  const [moveDateSelect, setMoveDateSelect] = useState("");

  const refreshShipmentMeta = useCallback(async () => {
    try {
      const [sumRes, datesRes] = await Promise.all([
        getDefectAutoShipmentSummary(),
        getDefectAutoShipmentMoveDates(),
      ]);
      setShipmentSummary(sumRes.shipment_summary ?? null);
      setMoveDateRollups(Array.isArray(datesRes.move_dates) ? datesRes.move_dates : []);
      setMoveDateSelect("");
    } catch {
      setShipmentSummary(null);
      setMoveDateRollups([]);
      setMoveDateSelect("");
    }
  }, []);

  useEffect(() => {
    void refreshShipmentMeta();
  }, [refreshShipmentMeta]);

  async function handleShipmentUpload() {
    if (!shipmentFile) {
      setDefectAutoMessage("출하 파일을 먼저 선택하세요.");
      return;
    }
    setDefectAutoLoading(true);
    setDefectAutoMessage("");
    try {
      const up = await uploadDefectShipment(shipmentFile);
      await refreshShipmentMeta();
      const dup = up.shipment_summary?.duplicate_skipped === true;
      const uploadOkMsg = dup
        ? "이미 동일 출하가 저장되어 있어 변경하지 않았습니다."
        : "파일 업로드가 완료되었습니다.";
      setDefectAutoMessage(uploadOkMsg);
      window.alert(uploadOkMsg);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setDefectAutoMessage(msg);
      window.alert(`실패: ${msg}`);
    } finally {
      setDefectAutoLoading(false);
    }
  }

  async function handleResetAll() {
    const ok = window.confirm(
      "초기화 하시겠습니까?\n\n" +
        "출하(Supabase), 주차·월별 자동 집계, LOT별 PPM(서버)을 모두 비웁니다.\n" +
        "이후 출하 파일 → 공정불량 자동 계산을 처음부터 다시 진행해야 합니다.\n\n" +
        "「확인」을 누르면 실행되고, 「취소」를 누르면 아무 일도 하지 않습니다.",
    );
    if (!ok) return;
    setDefectAutoLoading(true);
    setDefectAutoMessage("");
    try {
      const resetRes = await postDefectAutoReset();
      await refreshShipmentMeta();
      setShipmentFile(null);
      setShipmentFileInputKey((k) => k + 1);
      onResetSuccess?.([], []);
      const resetMsg = resetRes.message || "초기화 완료";
      setDefectAutoMessage(resetMsg);
      window.alert(resetMsg);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setDefectAutoMessage(msg);
      window.alert(`실패: ${msg}`);
    } finally {
      setDefectAutoLoading(false);
    }
  }

  async function handleCompute() {
    if (!codeDefectFile) {
      setDefectAutoMessage("입력 카드에서 코드별 불량현황 엑셀을 먼저 선택해주세요.");
      return;
    }
    if (!workFile) {
      setDefectAutoMessage("입력 카드에서 작업일보 엑셀을 먼저 선택해주세요.");
      return;
    }
    setDefectAutoLoading(true);
    setDefectAutoMessage("");
    try {
      const res = await computeDefectAuto(codeDefectFile, workFile);
      console.log("[defect-auto] weekly", res.weekly);
      console.log("[defect-auto] monthly", res.monthly);
      onComputeSuccess?.(res.weekly, res.monthly);
      setDefectAutoMessage(
        "공정불량 자동 계산이 완료되었습니다. 주차별·월별 표에 병합 반영됩니다.",
      );
      window.alert("공정불량 자동 계산이 완료되었습니다. (주·월 표에 병합 반영)");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setDefectAutoMessage(msg);
      window.alert(`실패: ${msg}`);
    } finally {
      setDefectAutoLoading(false);
    }
  }

  const shipmentByMonth = useMemo(
    () => aggregateShipmentRollupsByMonth(moveDateRollups),
    [moveDateRollups],
  );

  return (
    <section className="card" data-pdf-exclude="meta">
      <h2 className="cardTitle">공정불량 자동화</h2>
      <p className="hint" style={{ marginBottom: 12 }}>
        출하 파일(공장 받기.xlsx)을 서버에 올린 뒤 자동 집계합니다. &quot;공정불량 자동 계산&quot; 성공 시
        같은
        주차·같은 월 행은 자동 집계로 덮어쓰고, 나머지 수기 행은 유지됩니다. 작업일보·코드별
        불량현황은 입력 카드에서 선택한 파일을 사용합니다. 저장은 각각 주차/월별 카드의 저장
        버튼을 사용하세요. 처음부터 다시 맞출 때는 &quot;공정불량 자동화 초기화&quot;로 출하·주·월·LOT
        자동 데이터를 한 번에 비울 수 있습니다.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            width: "100%",
            gap: 12,
            flexWrap: "wrap",
            rowGap: 8,
          }}
        >
          <label
            htmlFor="defect-auto-shipment-file"
            className="label"
            style={{
              margin: 0,
              padding: 0,
              whiteSpace: "nowrap",
              flexShrink: 0,
              fontSize: 12,
            }}
          >
            출하 파일
          </label>
          <div
            style={{
              ...SHIPMENT_FILE_INPUT_WRAP,
              position: "relative",
            }}
          >
            <input
              key={shipmentFileInputKey}
              id="defect-auto-shipment-file"
              type="file"
              accept=".xlsx,.xls"
              disabled={defectAutoLoading}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setShipmentFile(f);
                setDefectAutoMessage(f ? `선택됨: ${f.name}` : "");
              }}
              style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}
            />
            <div
              style={{
                position: "absolute",
                right: "100%",
                top: "50%",
                transform: "translateY(-50%)",
                marginRight: 8,
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 11,
                color: "var(--muted, #64748b)",
                whiteSpace: "nowrap",
                pointerEvents: "auto",
                zIndex: 1,
              }}
            >
              <label htmlFor="defect-auto-move-dates" style={{ whiteSpace: "nowrap", margin: 0 }}>
                이동일자
              </label>
              <select
                id="defect-auto-move-dates"
                disabled={defectAutoLoading || moveDateRollups.length === 0}
                value={moveDateSelect}
                onChange={(e) => setMoveDateSelect(e.target.value)}
                title="저장된 출하의 이동일자(엑셀 기준)입니다. 일자별 행 수로 같은 파일을 두 번 올렸는지 등을 가늠할 수 있습니다."
                style={{
                  maxWidth: "11rem",
                  minWidth: "7.5rem",
                  fontSize: 11,
                  padding: "3px 5px",
                  lineHeight: 1.2,
                }}
              >
                <option value="">
                  {moveDateRollups.length === 0 ? "없음" : `요약 (${moveDateRollups.length}일)`}
                </option>
                {moveDateRollups.map((r) => (
                  <option key={r.date} value={r.date}>
                    {r.date} · {r.row_count}건 · {r.total_qty.toLocaleString("ko-KR")}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            marginTop: 8,
          }}
        >
          <button
            type="button"
            className="button"
            disabled={defectAutoLoading}
            onClick={handleShipmentUpload}
          >
            출하 파일 업로드
          </button>
          <button
            type="button"
            className="button"
            disabled={defectAutoLoading}
            onClick={handleCompute}
          >
            공정불량 자동 계산
          </button>
          <button
            type="button"
            className="button"
            disabled={defectAutoLoading}
            onClick={handleResetAll}
            title="출하·주·월·LOT 자동 집계를 서버에서 모두 삭제합니다"
          >
            공정불량 자동화 초기화
          </button>
        </div>
      </div>

      <div className="hint" style={{ marginTop: 12, marginBottom: 0 }}>
        {shipmentSummary ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span style={{ fontWeight: 600 }}>출하 누적</span>
            {shipmentByMonth.length > 0 ? (
              <ul style={{ margin: "0 0 0 1rem", padding: 0, listStylePosition: "outside" }}>
                {shipmentByMonth.map(({ ym, rowCount, totalQty }) => (
                  <li key={ym} style={{ marginBottom: 2 }}>
                    {ym}: Lot {rowCount.toLocaleString("ko-KR")}건 / 이동수량{" "}
                    {totalQty.toLocaleString("ko-KR")}
                  </li>
                ))}
              </ul>
            ) : (
              <span style={{ color: "var(--muted, #64748b)" }}>
                월별 요약은 이동일자 요약(`/shipment-move-dates`) 데이터가 있을 때 표시됩니다.
              </span>
            )}
            <span>
              전체: {shipmentSummary.min_date} ~ {shipmentSummary.max_date} / Lot{" "}
              {shipmentSummary.lot_count.toLocaleString("ko-KR")}건 / 이동수량{" "}
              {shipmentSummary.total_qty.toLocaleString("ko-KR")}
            </span>
          </div>
        ) : (
          "출하 누적: 아직 업로드된 출하 데이터가 없습니다."
        )}
      </div>

      {defectAutoMessage ? (
        <div className="hint" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
          {defectAutoMessage}
        </div>
      ) : null}
      {defectAutoLoading ? <div className="hint">처리 중…</div> : null}
    </section>
  );
}
