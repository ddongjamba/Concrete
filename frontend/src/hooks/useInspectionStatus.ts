"use client";
import { useEffect, useState } from "react";
import api from "@/lib/api";

export type JobStatus = "queued" | "running" | "completed" | "failed";

interface JobStatusData {
  id: string;
  status: JobStatus;
  progress_pct: number;
  error_message?: string;
}

/**
 * 분석 진행률 폴링 훅 (3초 간격, completed/failed 시 중단)
 */
export function useInspectionStatus(jobId: string | null) {
  const [data, setData] = useState<JobStatusData | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const poll = async () => {
      const res = await api.get(`/api/v1/analysis/jobs/${jobId}`);
      setData(res.data);
      return res.data.status;
    };

    poll();
    const interval = setInterval(async () => {
      const status = await poll();
      if (status === "completed" || status === "failed") {
        clearInterval(interval);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [jobId]);

  return data;
}
