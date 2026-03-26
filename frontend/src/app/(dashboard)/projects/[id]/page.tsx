"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { projectsApi, inspectionsApi, tracksApi } from "@/lib/api";
import { formatDate, severityLabel, severityDotColor, severityColor, cn } from "@/lib/utils";
import DefectTimelineChart from "@/components/DefectTimelineChart";

interface Inspection {
  id: string;
  label: string;
  inspection_date: string;
  status: string;
  file_count: number;
}

interface DefectTrack {
  id: string;
  location_zone: string | null;
  status: string;
  first_seen_at: string | null;
  latest_severity_score: number | null;
  latest_crack_width_mm: number | null;
  entry_count: number;
}

const STATUS_BADGE: Record<string, string> = {
  monitoring: "bg-blue-50 text-blue-700",
  worsening: "bg-red-50 text-red-700",
  stable: "bg-green-50 text-green-700",
  repaired: "bg-slate-100 text-slate-500",
  needs_review: "bg-yellow-50 text-yellow-700",
};
const STATUS_LABEL: Record<string, string> = {
  monitoring: "모니터링",
  worsening: "⚠️ 악화 중",
  stable: "안정",
  repaired: "수리 완료",
  needs_review: "검토 필요",
};

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<any>(null);
  const [inspections, setInspections] = useState<Inspection[]>([]);
  const [tracks, setTracks] = useState<DefectTrack[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<string | null>(null);
  const [tab, setTab] = useState<"inspections" | "tracks">("inspections");
  const [loading, setLoading] = useState(true);
  const [showNewInsp, setShowNewInsp] = useState(false);
  const [inspForm, setInspForm] = useState({ label: "", inspection_date: "" });
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    Promise.all([
      projectsApi.get(id),
      inspectionsApi.list(id),
      tracksApi.list(id),
    ]).then(([p, i, t]) => {
      setProject(p.data);
      setInspections(i.data.items ?? i.data);
      setTracks(t.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [id]);

  const filteredTracks = statusFilter
    ? tracks.filter((t) => t.status === statusFilter)
    : tracks;

  const handleCreateInsp = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await inspectionsApi.create(id, inspForm);
    setInspections((prev) => [r.data, ...prev]);
    setShowNewInsp(false);
    setInspForm({ label: "", inspection_date: "" });
  };

  if (loading) return <div className="p-8 text-slate-400">불러오는 중...</div>;
  if (!project) return <div className="p-8 text-slate-400">프로젝트를 찾을 수 없습니다.</div>;

  return (
    <div className="p-8">
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="text-sm text-slate-400 mb-1">
            <Link href="/projects" className="hover:text-blue-600">프로젝트</Link>
            {" / "}
            <span className="text-slate-600">{project.name}</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">{project.name}</h1>
          <p className="text-sm text-slate-500 mt-1">{project.address}</p>
        </div>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 w-fit mb-6">
        {(["inspections", "tracks"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t === "inspections" ? `점검 (${inspections.length})` : `균열 추적 (${tracks.length})`}
          </button>
        ))}
      </div>

      {/* 점검 탭 */}
      {tab === "inspections" && (
        <div>
          <div className="flex justify-end mb-4">
            <button
              onClick={() => setShowNewInsp(true)}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
            >
              + 새 점검
            </button>
          </div>

          {showNewInsp && (
            <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
              <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
                <h2 className="text-lg font-semibold mb-4">새 점검</h2>
                <form onSubmit={handleCreateInsp} className="space-y-3">
                  <input
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                    placeholder="점검명 (예: 2024-03 정기 점검)"
                    value={inspForm.label}
                    onChange={(e) => setInspForm({ ...inspForm, label: e.target.value })}
                    required
                  />
                  <input
                    type="date"
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                    value={inspForm.inspection_date}
                    onChange={(e) => setInspForm({ ...inspForm, inspection_date: e.target.value })}
                    required
                  />
                  <div className="flex gap-2 pt-2">
                    <button type="button" onClick={() => setShowNewInsp(false)}
                      className="flex-1 border border-slate-300 text-slate-600 rounded-lg py-2 text-sm">취소</button>
                    <button type="submit"
                      className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium">생성</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          <div className="space-y-3">
            {inspections.map((insp) => (
              <div key={insp.id}
                className="bg-white rounded-xl border border-slate-200 p-4 flex items-center justify-between hover:border-blue-200 transition-colors">
                <div>
                  <div className="font-medium text-slate-900">{insp.label || "이름 없는 점검"}</div>
                  <div className="text-sm text-slate-400 mt-0.5">
                    {formatDate(insp.inspection_date)} · 파일 {insp.file_count}개
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={cn(
                    "text-xs px-2 py-0.5 rounded-full",
                    insp.status === "completed" ? "bg-green-50 text-green-700" :
                    insp.status === "processing" ? "bg-blue-50 text-blue-700" :
                    "bg-slate-100 text-slate-500"
                  )}>
                    {insp.status === "completed" ? "완료" :
                     insp.status === "processing" ? "분석 중" :
                     insp.status === "pending" ? "대기" : insp.status}
                  </span>
                  <Link href={`/inspections/${insp.id}`}
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium">
                    {insp.status === "completed" ? "결과 보기" : "업로드 →"}
                  </Link>
                </div>
              </div>
            ))}
            {inspections.length === 0 && (
              <div className="text-center py-16 text-slate-400">점검 이력이 없습니다.</div>
            )}
          </div>
        </div>
      )}

      {/* 균열 추적 탭 */}
      {tab === "tracks" && (
        <div>
          <div className="flex gap-2 mb-4">
            {["", "worsening", "monitoring", "stable", "needs_review", "repaired"].map((s) => (
              <button key={s} onClick={() => setStatusFilter(s)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium border transition-colors",
                  statusFilter === s
                    ? "bg-blue-600 text-white border-blue-600"
                    : "border-slate-300 text-slate-600 hover:border-slate-400"
                )}>
                {s === "" ? "전체" : STATUS_LABEL[s] ?? s}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredTracks.map((track) => (
              <div key={track.id}
                onClick={() => setSelectedTrack(selectedTrack === track.id ? null : track.id)}
                className={cn(
                  "bg-white rounded-xl border p-4 cursor-pointer transition-all",
                  selectedTrack === track.id
                    ? "border-blue-400 shadow-md"
                    : "border-slate-200 hover:border-blue-200"
                )}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="font-medium text-slate-900">
                      {track.location_zone || "위치 미지정"}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      최초 발견: {formatDate(track.first_seen_at)} · 점검 {track.entry_count}회
                    </div>
                  </div>
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", STATUS_BADGE[track.status])}>
                    {STATUS_LABEL[track.status]}
                  </span>
                </div>

                {track.latest_severity_score !== null && (
                  <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-1.5">
                      <span className={cn("w-2 h-2 rounded-full", severityDotColor(track.latest_severity_score))} />
                      <span className="text-slate-600">
                        심각도 <strong>{track.latest_severity_score}</strong>
                        <span className="text-slate-400 ml-1">({severityLabel(track.latest_severity_score)})</span>
                      </span>
                    </div>
                    {track.latest_crack_width_mm && (
                      <span className="text-slate-500">폭 {track.latest_crack_width_mm.toFixed(1)} mm</span>
                    )}
                  </div>
                )}

                {selectedTrack === track.id && (
                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <DefectTimelineChart trackId={track.id} />
                  </div>
                )}
              </div>
            ))}
            {filteredTracks.length === 0 && (
              <div className="col-span-2 text-center py-16 text-slate-400">
                균열 추적 데이터가 없습니다.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
