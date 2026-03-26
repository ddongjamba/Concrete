import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Facade Inspect — 드론 외벽 균열 탐지",
  description: "AI 기반 건물 외벽 균열 자동 분석 및 시계열 추적 서비스",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
