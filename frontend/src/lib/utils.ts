import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function severityColor(score: number): string {
  if (score >= 80) return "text-red-700 bg-red-50 border-red-200";
  if (score >= 60) return "text-orange-700 bg-orange-50 border-orange-200";
  if (score >= 30) return "text-yellow-700 bg-yellow-50 border-yellow-200";
  return "text-green-700 bg-green-50 border-green-200";
}

export function severityLabel(score: number): string {
  if (score >= 80) return "긴급";
  if (score >= 60) return "경보";
  if (score >= 30) return "주의";
  return "관찰";
}

export function severityDotColor(score: number): string {
  if (score >= 80) return "bg-red-500";
  if (score >= 60) return "bg-orange-500";
  if (score >= 30) return "bg-yellow-500";
  return "bg-green-500";
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit",
  });
}
