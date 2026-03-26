"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { alertsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Alert {
  id: string;
  track_id: string;
  alert_type: string;
  title: string;
  body: string | null;
  is_read: boolean;
  created_at: string;
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const r = await alertsApi.list(false);
    setAlerts(r.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleRead = async (id: string) => {
    await alertsApi.markRead(id);
    setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, is_read: true } : a));
  };

  const handleReadAll = async () => {
    await alertsApi.markAllRead();
    setAlerts((prev) => prev.map((a) => ({ ...a, is_read: true })));
  };

  const unread = alerts.filter((a) => !a.is_read).length;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">알림</h1>
          {unread > 0 && (
            <p className="text-sm text-slate-500 mt-1">읽지 않은 알림 {unread}건</p>
          )}
        </div>
        {unread > 0 && (
          <button
            onClick={handleReadAll}
            className="text-sm text-blue-600 hover:text-blue-700"
          >
            모두 읽음 처리
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-20 text-slate-400">불러오는 중...</div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-4xl mb-3">🔔</div>
          <p className="text-slate-500">알림이 없습니다.</p>
        </div>
      ) : (
        <div className="space-y-2 max-w-2xl">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={cn(
                "bg-white rounded-xl border p-4 transition-colors",
                alert.is_read
                  ? "border-slate-200 opacity-60"
                  : "border-orange-200 bg-orange-50/40"
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <span className="text-lg mt-0.5">
                    {alert.alert_type === "worsening" ? "⚠️" : "🔔"}
                  </span>
                  <div>
                    <div className="font-medium text-slate-900 text-sm">{alert.title}</div>
                    {alert.body && (
                      <div className="text-xs text-slate-500 mt-0.5">{alert.body}</div>
                    )}
                    <div className="text-xs text-slate-400 mt-1.5">
                      {new Date(alert.created_at).toLocaleString("ko-KR")}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Link
                    href={`/defect-tracks/${alert.track_id}`}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    균열 보기
                  </Link>
                  {!alert.is_read && (
                    <button
                      onClick={() => handleRead(alert.id)}
                      className="text-xs text-slate-400 hover:text-slate-600 border border-slate-200 px-2 py-0.5 rounded"
                    >
                      읽음
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
