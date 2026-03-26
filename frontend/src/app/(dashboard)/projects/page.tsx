"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { projectsApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";

interface Project {
  id: string;
  name: string;
  address: string;
  building_type: string;
  status: string;
  created_at: string;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", address: "", building_type: "apartment", description: "" });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    projectsApi.list().then((r) => {
      setProjects(r.data.items ?? r.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const r = await projectsApi.create(form);
      setProjects((prev) => [r.data, ...prev]);
      setShowCreate(false);
      setForm({ name: "", address: "", building_type: "apartment", description: "" });
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">프로젝트</h1>
          <p className="text-sm text-slate-500 mt-1">건물별 균열 점검 이력 관리</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          + 새 프로젝트
        </button>
      </div>

      {/* 프로젝트 생성 모달 */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold mb-4">새 프로젝트</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <input
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="건물명 (예: 한강아파트 A동)"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <input
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="주소"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                required
              />
              <select
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.building_type}
                onChange={(e) => setForm({ ...form, building_type: e.target.value })}
              >
                <option value="apartment">아파트</option>
                <option value="office">오피스</option>
                <option value="hospital">병원</option>
                <option value="school">학교</option>
                <option value="other">기타</option>
              </select>
              <textarea
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                placeholder="메모 (선택)"
                rows={2}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="flex-1 border border-slate-300 text-slate-600 rounded-lg py-2 text-sm hover:bg-slate-50"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {creating ? "생성 중..." : "생성"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 목록 */}
      {loading ? (
        <div className="text-center py-20 text-slate-400">불러오는 중...</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-4xl mb-3">🏗</div>
          <p className="text-slate-500">아직 프로젝트가 없습니다.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 text-blue-600 text-sm hover:underline"
          >
            첫 번째 프로젝트 만들기
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="bg-white rounded-xl border border-slate-200 p-5 hover:border-blue-300 hover:shadow-sm transition-all group"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                    {p.name}
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">{p.address}</p>
                </div>
                <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                  {p.building_type}
                </span>
              </div>
              <div className="text-xs text-slate-400">
                생성일: {formatDate(p.created_at)}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
