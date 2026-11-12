"use client";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useState } from "react";
import { api, useLoad } from "@/lib/api";
import { useSession } from "@/components/Shell";

const TABS = [
  ["", "개요·자료"],
  ["/inventory", "AI 인벤토리"],
  ["/classification", "판정"],
  ["/gap", "갭 리포트"],
  ["/documents", "문서 초안"],
  ["/evidence", "증적함"],
  ["/tech-check", "기술 점검"],
  ["/changes", "변경·재평가"],
];

export function useCustomer() {
  const { id } = useParams<{ id: string }>();
  const r = useLoad<any>(`/customers/${id}`);
  return { id, customer: r.data, reloadCustomer: r.reload, customerError: r.error };
}

export function CustomerFrame({ customer, id, children }: { customer: any; id: string; children: React.ReactNode }) {
  const path = usePathname();
  const { meta } = useSession();
  const base = `/customers/${id}`;
  const states = meta?.workflow_states ?? [];
  return (
    <>
      <div className="spread">
        <div>
          <p className="sub" style={{ margin: 0 }}><Link href="/">고객사</Link> /</p>
          <h1>{customer?.name ?? "…"}</h1>
        </div>
        {customer && (
          <div className="actions">
            <span className="tag navy">현재 단계: {customer.state_label}</span>
            <span className="tag">LLM: {customer.llm.effective}{customer.llm.route_reason !== "configured" ? ` (${customer.llm.route_reason === "data_policy" ? "데이터 정책" : "예산 초과"}으로 대체)` : ""}</span>
          </div>
        )}
      </div>
      {customer && (
        <ol className="steps" aria-label="진행 단계">
          {states.map((s, i) => (
            <li key={s} className={i < customer.state_index || customer.state_index === states.length - 1 ? "done" : i === customer.state_index ? "now" : ""}>{i + 1}. {meta?.workflow_labels[s]}</li>
          ))}
        </ol>
      )}
      <div className="tabs" role="navigation" aria-label="고객사 메뉴">
        {TABS.map(([p, label]) => (
          <Link key={p} href={base + p} className={path === base + p ? "on" : ""}>{label}</Link>
        ))}
      </div>
      {children}
    </>
  );
}

/** 서버 작업 버튼. 역할이 맞지 않으면 비활성화하고 이유를 보여 준다(서버에서도 다시 검사한다). */
export function Action({ label, path, roles, onDone, method = "POST", json, ghost, confirmText }: {
  label: string; path: string; roles: string[]; onDone?: (r: any) => void | Promise<void>; method?: string; json?: unknown; ghost?: boolean; confirmText?: string;
}) {
  const { user } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const allowed = !!user && roles.includes(user.role);
  const roleNames: Record<string, string> = { customer: "고객 담당자", consultant: "컨설턴트", ops: "운영자" };
  async function run() {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError("");
    try {
      const r = await api(path, { method, json });
      await onDone?.(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <span>
      <button className={ghost ? "ghost" : ""} disabled={!allowed || busy} onClick={run} title={allowed ? "" : `${roles.map((r) => roleNames[r]).join("·")} 전용`}>
        {busy ? "처리 중…" : label}
      </button>
      {!allowed && <span className="hint"> {roles.map((r) => roleNames[r]).join("·")} 전용</span>}
      {error && <div className="msg err" role="alert" style={{ marginTop: 8 }}>{error}</div>}
    </span>
  );
}

export function ArticleRefs({ ids, clauses }: { ids: string[]; clauses: Record<string, any> }) {
  if (!ids?.length) return null;
  return (
    <span className="refs">
      {ids.map((a) => (
        <span key={a} className="tag" style={{ marginRight: 4 }} title={clauses?.[a] ? `${clauses[a].summary} (요약 — 원문 확인 필요)` : a}>
          {clauses?.[a] ? `${clauses[a].article} ${clauses[a].title.split("—").pop()?.trim()}` : a}
        </span>
      ))}
    </span>
  );
}
