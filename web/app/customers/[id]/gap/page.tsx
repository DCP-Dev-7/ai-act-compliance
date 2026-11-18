"use client";
import { fmt, fmtDate, useLoad } from "@/lib/api";
import { Action, ArticleRefs, CustomerFrame, useCustomer } from "@/components/CustomerFrame";

export default function GapPage() {
  const { id, customer, reloadCustomer } = useCustomer();
  const gap = useLoad<any>(`/customers/${id}/gap-report`);
  const reload = async () => { await Promise.all([gap.reload(), reloadCustomer()]); };
  const r = gap.data?.report;
  const sev: Record<string, string> = { high: "bad", medium: "warn", low: "" };
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>갭 리포트</h2>
          <p className="sub">확정된 판정의 의무와 설문상 현재 이행 상태를 비교한 결과입니다.</p>
        </div>
        <Action label="갭 리포트 생성" path={`/customers/${id}/gap-report`} roles={["consultant"]} onDone={reload} />
      </div>
      {gap.error && <div className="msg err">{gap.error}</div>}
      {!r && !gap.loading && <div className="card"><p className="sub">갭 리포트가 없습니다. 모든 판정이 확정된 뒤 생성할 수 있습니다.</p></div>}
      {r && (
        <>
          <div className="card">
            <p className="sub">v{r.version} · KB {r.kb_version} · 작성 {r.created_by} · {fmt(r.created_at)} · 발견 사항 <b>{r.findings.length}건</b></p>
            {r.findings.length === 0 && r.no_gap_note && (
              <div className="msg ok" style={{ marginTop: 8 }}>
                <b>{r.no_gap_note.split(" — ")[0]}</b> — {r.no_gap_note.split(" — ").slice(1).join(" — ")}
                <div className="sub" style={{ marginTop: 4 }}>0건은 오류가 아니라 판정 결과입니다. 근거는 ‘판정’ 탭에서 확인하세요.</div>
              </div>
            )}
            <div className="tablewrap">
              <table>
                <thead><tr><th>코드</th><th>발견 사항</th><th>심각도</th><th>담당</th><th>기한</th><th>대상 시스템</th><th>근거 조문(요약)</th></tr></thead>
                <tbody>
                  {r.findings.map((f: any) => (
                    <tr key={f.code}>
                      <td className="mono">{f.code}</td>
                      <td><b>{f.title}</b><div>{f.detail}</div><div className="sub">권고: {f.recommendation}</div></td>
                      <td><span className={`tag ${sev[f.severity]}`}>{f.severity_label}</span></td>
                      <td>{f.owner}</td>
                      <td>{fmtDate(f.due_date)}</td>
                      <td>{f.systems.map((s: any) => s.name).join(", ")}</td>
                      <td><ArticleRefs ids={f.articles} clauses={gap.data.clauses} /></td>
                    </tr>
                  ))}
                  {r.findings.length === 0 && <tr><td colSpan={7}>해야 할 일(갭)이 없습니다.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h2>리포트 미리보기 (HTML)</h2>
            <iframe className="preview" sandbox="" srcDoc={r.html} title="갭 리포트 미리보기" />
          </div>
        </>
      )}
    </CustomerFrame>
  );
}
