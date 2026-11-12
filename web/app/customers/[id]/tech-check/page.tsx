"use client";
import { fmt, useLoad } from "@/lib/api";
import { Action, CustomerFrame, useCustomer } from "@/components/CustomerFrame";

const CHECK: Record<string, string> = { prior_notice: "사전 고지 문구(제31조)", image_metadata: "생성 이미지 메타데이터(제31조)" };

export default function TechCheckPage() {
  const { id, customer } = useCustomer();
  const tc = useLoad<any>(`/customers/${id}/tech-checks`);
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>기술 점검</h2>
          <p className="sub">허용 목록에 있는 대상만 점검합니다: {tc.data?.allowlist.map((a: string) => <span className="mono" key={a}>{a} </span>)}· 결과는 증적으로 보관됩니다.</p>
        </div>
        <Action label="지금 점검" path={`/customers/${id}/tech-check`} roles={["consultant", "ops"]} onDone={() => tc.reload()} />
      </div>
      {tc.error && <div className="msg err">{tc.error}</div>}
      {tc.data?.items.length === 0 && <div className="card"><p className="sub">점검 기록이 없습니다.</p></div>}
      {(tc.data?.items ?? []).map((t: any) => (
        <div className="card" key={t.id}>
          <div className="spread">
            <h2>점검 #{t.id} <span className="sub">{fmt(t.created_at)} · {t.triggered_by} · 대상 {t.target}</span></h2>
            <div><span className="tag ok">통과 {t.passed}</span> <span className={`tag ${t.failed ? "bad" : ""}`}>미흡 {t.failed}</span> <span className="tag">증적 #{t.evidence_id}</span></div>
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr><th>결과</th><th>점검 항목</th><th>대상</th><th>내용</th></tr></thead>
              <tbody>
                {t.results.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.passed ? <span className="tag ok">통과</span> : <span className="tag bad">미흡</span>}</td>
                    <td>{CHECK[r.check] ?? r.check}</td>
                    <td className="mono">{r.target}</td>
                    <td>{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </CustomerFrame>
  );
}
