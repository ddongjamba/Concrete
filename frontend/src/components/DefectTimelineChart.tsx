"use client";
import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { tracksApi } from "@/lib/api";

interface Entry {
  id: string;
  inspection_date: string | null;
  severity_score: number;
  crack_width_mm: number | null;
  crack_length_mm: number | null;
  change_vs_prev: Record<string, number> | null;
}

interface ChartPoint {
  date: string;
  score: number;
  width: number | null;
  length: number | null;
}

const THRESHOLD_LINES = [
  { y: 80, label: "긴급", color: "#dc2626" },
  { y: 60, label: "경보", color: "#f97316" },
  { y: 30, label: "주의", color: "#eab308" },
];

function ScoreDot(props: any) {
  const { cx, cy, payload } = props;
  const s = payload.score;
  const color = s >= 80 ? "#dc2626" : s >= 60 ? "#f97316" : s >= 30 ? "#eab308" : "#22c55e";
  return <circle cx={cx} cy={cy} r={5} fill={color} stroke="white" strokeWidth={2} />;
}

export default function DefectTimelineChart({ trackId }: { trackId: string }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [metric, setMetric] = useState<"score" | "width" | "length">("score");

  useEffect(() => {
    tracksApi.get(trackId).then((r) => {
      setEntries(r.data.entries ?? []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [trackId]);

  if (loading) return <div className="h-40 flex items-center justify-center text-slate-400 text-sm">로딩 중...</div>;
  if (entries.length < 2) {
    return (
      <div className="h-32 flex items-center justify-center text-slate-400 text-sm">
        시계열 차트는 2회 이상 점검 후 표시됩니다.
      </div>
    );
  }

  const data: ChartPoint[] = entries.map((e) => ({
    date: e.inspection_date?.slice(0, 7) ?? "?",
    score: e.severity_score,
    width: e.crack_width_mm,
    length: e.crack_length_mm,
  }));

  const latest = entries[entries.length - 1];
  const prev = entries[entries.length - 2];
  const delta = latest.change_vs_prev;

  return (
    <div>
      {/* 요약 카드 */}
      {delta && (
        <div className="flex gap-4 mb-4 text-xs">
          <Stat label="심각도" current={latest.severity_score} delta={delta.score_delta} unit="" />
          {latest.crack_width_mm && (
            <Stat label="균열 폭" current={latest.crack_width_mm} delta={delta.width_delta} unit="mm" />
          )}
          {latest.crack_length_mm && (
            <Stat label="균열 길이" current={latest.crack_length_mm} delta={delta.length_delta} unit="mm" />
          )}
        </div>
      )}

      {/* 메트릭 선택 */}
      <div className="flex gap-1 mb-3">
        {(["score", "width", "length"] as const).map((m) => (
          <button key={m} onClick={() => setMetric(m)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              metric === m ? "bg-blue-600 text-white" : "text-slate-500 hover:bg-slate-100"
            }`}>
            {m === "score" ? "심각도" : m === "width" ? "균열 폭(mm)" : "균열 길이(mm)"}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
            formatter={(v: any, name: string) => [
              metric === "score" ? v : `${v?.toFixed(2)} mm`,
              name === "score" ? "심각도" : name === "width" ? "폭" : "길이",
            ]}
          />
          {metric === "score" && THRESHOLD_LINES.map((t) => (
            <ReferenceLine key={t.y} y={t.y} stroke={t.color} strokeDasharray="4 3"
              label={{ value: t.label, position: "insideTopRight", fontSize: 10, fill: t.color }} />
          ))}
          <Line
            type="monotone"
            dataKey={metric}
            stroke="#3b82f6"
            strokeWidth={2}
            dot={metric === "score" ? <ScoreDot /> : { r: 4, fill: "#3b82f6" }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Stat({ label, current, delta, unit }: {
  label: string; current: number; delta?: number; unit: string;
}) {
  const isUp = delta !== undefined && delta > 0;
  const isDown = delta !== undefined && delta < 0;
  return (
    <div className="bg-slate-50 rounded-lg px-3 py-2 flex-1">
      <div className="text-slate-400">{label}</div>
      <div className="flex items-baseline gap-1 mt-0.5">
        <span className="text-base font-semibold text-slate-800">
          {typeof current === "number" ? current.toFixed(unit ? 1 : 0) : current}{unit}
        </span>
        {delta !== undefined && delta !== 0 && (
          <span className={isUp ? "text-red-500" : "text-green-500"}>
            {isUp ? "▲" : "▼"} {Math.abs(delta).toFixed(unit ? 1 : 0)}{unit}
          </span>
        )}
      </div>
    </div>
  );
}
