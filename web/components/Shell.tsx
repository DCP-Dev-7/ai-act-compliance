"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

export type User = { id: number; email: string; name: string; role: "customer" | "consultant" | "ops"; role_label: string; customer_id: number | null };
export type Meta = {
  banner: string;
  llm: { configured: string; model: string; internal_endpoint_configured: boolean };
  kb_version: string | null;
  kb_label: string | null;
  workflow_states: string[];
  workflow_labels: Record<string, string>;
  domain_labels: Record<string, string>;
  doc_kind_labels: Record<string, string>;
  state_labels: Record<string, string>;
};

const Ctx = createContext<{ user: User | null; meta: Meta | null; refresh: () => Promise<void> }>({ user: null, meta: null, refresh: async () => {} });
export const useSession = () => useContext(Ctx);

export default function Shell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [ready, setReady] = useState(false);
  const [down, setDown] = useState(false);
  const path = usePathname();
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      setMeta(await api<Meta>("/meta"));
      setDown(false);
    } catch {
      setDown(true);
    }
    try {
      setUser(await api<User>("/auth/me"));
    } catch (e) {
      setUser(null);
      if (e instanceof ApiError && e.status === 401 && window.location.pathname !== "/login") router.replace("/login");
    }
    setReady(true);
  }, [router]);

  useEffect(() => {
    void refresh();
  }, [refresh, path]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    setUser(null);
    router.replace("/login");
  }

  const llmLabel = meta ? (meta.llm.configured === "mock" ? "mock (규칙·템플릿, 외부 호출 없음)" : `${meta.llm.configured} · ${meta.llm.model}`) : "확인 중";
  return (
    <Ctx.Provider value={{ user, meta, refresh }}>
      <div className="banner" role="note">
        <b>{meta?.banner ?? "가상 데이터 · 법률 자문 아님"}</b>
        <span>법령 내용은 요약 — 원문 확인 필요</span>
        <span>LLM 모드: <b>{llmLabel}</b></span>
        {meta?.kb_version && <span>법령 KB: <span className="mono">{meta.kb_version}</span></span>}
      </div>
      <div className="topbar">
        <Link href="/" className="brand">AI 기본법 준수 플랫폼 <span style={{ fontWeight: 400, opacity: 0.75 }}>데모</span></Link>
        <nav aria-label="주 메뉴">
          {user && (
            <>
              <Link href="/" className={path === "/" || path.startsWith("/customers") ? "on" : ""}>고객사</Link>
              <Link href="/learn" className={path.startsWith("/learn") ? "on" : ""}>AI 기본법 한눈에</Link>
              <Link href="/kb" className={path.startsWith("/kb") ? "on" : ""}>법령 지식베이스</Link>
              {user.role !== "customer" && <Link href="/ops" className={path.startsWith("/ops") ? "on" : ""}>운영 콘솔</Link>}
            </>
          )}
        </nav>
        {user && (
          <div className="who">
            <span>{user.name} · {user.role_label}</span>
            <button className="small ghost" style={{ color: "#fff", borderColor: "rgba(255,255,255,.5)" }} onClick={logout}>로그아웃</button>
          </div>
        )}
      </div>
      <main>
        {down && <div className="msg err">API 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요.</div>}
        {ready && (user || path === "/login") ? children : !down && <p className="sub">불러오는 중…</p>}
      </main>
    </Ctx.Provider>
  );
}
