"use client";
import { useState } from "react";
import { api, fmt, fmtDate, useLoad } from "@/lib/api";
import { Action, CustomerFrame, useCustomer } from "@/components/CustomerFrame";
import { EVIDENCE_KIND } from "@/lib/labels";

export default function EvidencePage() {
  const { id, customer, reloadCustomer } = useCustomer();
  const ev = useLoad<any[]>(`/customers/${id}/evidence`);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = async () => { await Promise.all([ev.reload(), reloadCustomer()]); };
  async function verify() {
    setBusy(true);
    setErr("");
    try {
      setResult(await api(`/customers/${id}/evidence/verify`, { method: "POST" }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>증적함</h2>
          <p className="sub">추가만 가능한(append-only) 저장소입니다. 각 항목은 SHA-256 해시와 직전 항목의 체인 해시로 연결되며 5년간 보관됩니다. 수정·삭제 기능은 없습니다.</p>
        </div>
        <div className="actions">
          <Action label="증적 보관(승인본)" path={`/customers/${id}/evidence/store-package`} roles={["consultant"]} onDone={reload} ghost />
          <button onClick={verify} disabled={busy}>{busy ? "검증 중…" : "체인 검증"}</button>
        </div>
      </div>
      {err && <div className="msg err">{err}</div>}
      {result && (
        <div className={`msg ${result.ok ? "ok" : "err"}`} role="status">
          {result.ok ? `체인 검증 정상 — ${result.count}건, 최신 체인 해시 ${result.head_hash.slice(0, 16)}…` : `체인 검증 실패 — 문제 ${result.problems.length}건`}
          <span className="sub"> ({fmt(result.verified_at)}, 백엔드 {result.backend})</span>
          {!result.ok && <ul className="plain">{result.problems.map((p: any, i: number) => <li key={i}>#{p.seq ?? "-"} {p.problem}</li>)}</ul>}
        </div>
      )}
      <div className="card">
        <div className="tablewrap">
          <table>
            <thead><tr><th>#</th><th>종류·제목</th><th>SHA-256</th><th>체인 해시(직전 → 현재)</th><th>크기</th><th>보관 시각</th><th>보관 기한</th><th></th></tr></thead>
            <tbody>
              {(ev.data ?? []).map((e) => (
                <tr key={e.id}>
                  <td>{e.seq}</td>
                  <td><span className="tag">{EVIDENCE_KIND[e.kind] ?? e.kind}</span><div>{e.title}</div><div className="sub">{e.created_by}</div></td>
                  <td className="mono" title={e.sha256}>{e.sha256.slice(0, 20)}…</td>
                  <td className="mono" title={`${e.prev_hash} → ${e.chain_hash}`}>{e.prev_hash.slice(0, 10)}… → {e.chain_hash.slice(0, 10)}…</td>
                  <td>{e.size.toLocaleString()} B</td>
                  <td>{fmt(e.created_at)}</td>
                  <td>{fmtDate(e.retention_until)}</td>
                  <td><a href={`/api/evidence/${e.id}/content`}>원본</a></td>
                </tr>
              ))}
              {ev.data?.length === 0 && <tr><td colSpan={8} className="sub">보관된 증적이 없습니다. 문서 승인 후 ‘증적 보관’을 실행하세요.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </CustomerFrame>
  );
}
