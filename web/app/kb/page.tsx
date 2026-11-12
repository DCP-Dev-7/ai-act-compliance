"use client";
import { fmt, useLoad } from "@/lib/api";

export default function KbPage() {
  const kb = useLoad<any>("/kb");
  const k = kb.data;
  return (
    <>
      <h1>법령 지식베이스</h1>
      {kb.error && <div className="msg err">{kb.error}</div>}
      {k && (
        <>
          <p className="sub">{k.label} · 버전 <span className="mono">{k.version}</span> · 기준일 {k.effective_date}</p>
          <div className="msg info">{k.notice}</div>
          <div className="card">
            <h2>조문 단위 요약 <span className="tag warn">{k.summary_label}</span></h2>
            {k.clauses.map((c: any) => (
              <div key={c.clause_id} style={{ borderBottom: "1px solid #ebe7dd", padding: "10px 0" }}>
                <h3>{c.article} · {c.title} <span className="mono sub">{c.clause_id}</span></h3>
                <p>{c.summary}</p>
                <ul className="plain">{c.obligations.map((o: string, i: number) => <li key={i}>{o}</li>)}</ul>
                <p className="sub" style={{ marginTop: 4 }}>출처: {c.sources.map((s: string) => <a key={s} href={s} target="_blank" rel="noreferrer noopener" style={{ marginRight: 8 }}>{new URL(s).hostname}</a>)}</p>
              </div>
            ))}
          </div>
          <div className="card">
            <h2>통제 매핑: AI 기본법 ↔ ISMS-P ↔ ISO/IEC 42001 <span className="tag bad">{k.mapping_label}</span></h2>
            <p className="sub">범주 수준의 대응 관계입니다. 특정 인증 항목 번호를 확정하지 않습니다.</p>
            <div className="tablewrap">
              <table>
                <thead><tr><th>AI 기본법 조문</th><th>ISMS-P</th><th>ISO/IEC 42001</th><th>메모</th></tr></thead>
                <tbody>
                  {k.mappings.map((m: any) => {
                    const c = k.clauses.find((x: any) => x.clause_id === m.clause_id);
                    return <tr key={m.clause_id}><td>{c ? `${c.article} ${c.title}` : m.clause_id}</td><td>{m.isms_p}</td><td>{m.iso42001}</td><td>{m.note}</td></tr>;
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h2>KB 버전 이력</h2>
            <ul className="plain">
              {k.versions.map((v: any) => <li key={v.version}><span className="mono">{v.version}</span> {v.label} · 적용 {fmt(v.applied_at)} {v.is_active && <span className="tag ok">활성</span>}</li>)}
            </ul>
          </div>
        </>
      )}
    </>
  );
}
