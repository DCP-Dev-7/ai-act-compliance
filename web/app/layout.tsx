import type { Metadata } from "next";
import Shell from "@/components/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 기본법 준수 플랫폼 (데모)",
  description: "인공지능기본법 진단·체계 구축·증적 보관 데모 — 가상 데이터, 법률 자문 아님",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
