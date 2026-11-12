"use client";
import Link from "next/link";
import { fmt, useLoad } from "@/lib/api";
import { Action, CustomerFrame, useCustomer } from "@/components/CustomerFrame";

export default function ChangesPage() {
  const { id, customer, reloadCustomer } = useCustomer();
  const ch = useLoad<any>(`/changes?customer_id=${id}`);
  const reload = async () => { await Promise.all([ch.reload(), reloadCustomer()]); };
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>변경 이벤트·재평가 작업</h2>
          <p className="sub">법령 KB가 바뀌거나 고객이 새 버전을 릴리스하면, 영향받는 확정 판정에 재평가 작업이 생깁니다.</p>
        </div>
        {ch.data?.simulation_available
          ? <Action label="법령 변경 반영(시뮬레이션)" path="/changes/law/simulate" roles={["consultant", "ops"]} onDone={reload}
              confirmText="가상 가이드라인(사람이 일부 수정한 생성 이미지 표시 기준)을 KB v2로 적용합니다. 실제 법령 변경이 아닙니다. 계속할까요?" />
          : <span className="tag">시뮬레이션 KB({ch.data?.simulation_version}) 적용됨</span>}
      </div>
      {ch.error && <div className="msg err">{ch.error}</div>}
      <div className="card">
        <h2>재평가 작업</h2>
        <div className="tablewrap">
          <table>
            <thead><tr><th>#</th><th>상태</th><th>대상 시스템</th><th>사유</th><th>관련 조문</th><th>생성</th><th></th></tr></thead>
            <tbody>
              {(ch.data?.tasks ?? []).map((t: any) => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td>{t.status === "open" ? <span className="tag warn">미해결</span> : <span className="tag ok">완료 — {t.resolved_by}</span>}</td>
                  <td>{t.system_name}</td>
                  <td>{t.reason}</td>
                  <td className="mono">{t.clause_ids.join(", ") || "-"}</td>
                  <td>{fmt(t.created_at)}</td>
                  <td>{t.status === "open" && <Action label="완료 처리" path={`/tasks/${t.id}/resolve`} roles={["consultant"]} onDone={reload} ghost />}</td>
                </tr>
              ))}
              {ch.data?.tasks.length === 0 && <tr><td colSpan={7} className="sub">재평가 작업이 없습니다.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="hint">재평가 방법: <Link href={`/customers/${id}/classification`}>판정 화면</Link>에서 ‘판정 초안 생성(재판정)’ → 확정 → 작업 완료 처리.</p>
      </div>
      <div className="card">
        <h2>변경 이벤트</h2>
        {(ch.data?.events ?? []).map((e: any) => (
          <div key={e.id} style={{ marginBottom: 12 }}>
            <b>{e.type === "law_change" ? "법령 KB 변경" : "고객 릴리스"}</b> — {e.title} <span className="sub">{fmt(e.created_at)} · {e.created_by}</span>
            {e.type === "law_change" ? (
              <ul className="plain">
                <li>버전: <span className="mono">{e.payload.from} → {e.payload.to}</span></li>
                {e.payload.diff.changed.map((c: any) => (
                  <li key={c.clause_id}>변경 <span className="mono">{c.clause_id}</span> {c.after.title}
                    <details><summary>변경 전·후 요약 보기</summary><p className="sub">전: {c.before.summary}</p><p>후: {c.after.summary}</p></details></li>
                ))}
                {e.payload.diff.added.map((c: any) => <li key={c.clause_id}>추가 <span className="mono">{c.clause_id}</span> {c.title}<p className="sub">{c.summary}</p></li>)}
                {e.payload.diff.removed.map((c: any) => <li key={c.clause_id}>삭제 <span className="mono">{c.clause_id}</span> {c.title}</li>)}
              </ul>
            ) : <p className="sub">버전 {e.payload.version || "-"} · {e.payload.system_name || "전체 시스템"} · {e.payload.notes}</p>}
          </div>
        ))}
        {ch.data?.events.length === 0 && <p className="sub">변경 이벤트가 없습니다.</p>}
      </div>
    </CustomerFrame>
  );
}
