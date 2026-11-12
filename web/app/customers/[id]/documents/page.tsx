"use client";
import { useState } from "react";
import { fmt, useLoad } from "@/lib/api";
import { Action, ArticleRefs, CustomerFrame, useCustomer } from "@/components/CustomerFrame";

export default function DocumentsPage() {
  const { id, customer, reloadCustomer } = useCustomer();
  const docs = useLoad<any>(`/customers/${id}/generated-documents`);
  const [open, setOpen] = useState<number | null>(null);
  const reload = async () => { await Promise.all([docs.reload(), reloadCustomer()]); };
  const items: any[] = docs.data?.items ?? [];
  const current = items.find((d) => d.id === open) ?? items[0];
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>문서 초안</h2>
          <p className="sub">모든 규범적 문단에는 조문 근거가 붙습니다. 근거를 확인할 수 없는 문장은 ‘근거 미확인’으로 표시됩니다.</p>
        </div>
        <div className="actions">
          <Action label="문서 초안 생성" path={`/customers/${id}/generated-documents/generate`} roles={["consultant"]} onDone={reload} ghost />
          <Action label="문서 승인" path={`/customers/${id}/approve`} roles={["consultant"]} onDone={reload}
            confirmText="현재 초안 전체를 승인합니다. ‘근거 미확인’ 문단이 있으면 먼저 확인하세요. 계속할까요?" />
        </div>
      </div>
      {docs.error && <div className="msg err">{docs.error}</div>}
      {items.length === 0 && !docs.loading && <div className="card"><p className="sub">문서 초안이 없습니다. 갭 리포트 생성 후 만들 수 있습니다.</p></div>}
      {items.length > 0 && (
        <div className="row">
          <div className="card" style={{ flex: "0 1 340px" }}>
            <h2>문서 목록</h2>
            {items.map((d) => (
              <div key={d.id} style={{ marginBottom: 10 }}>
                <button className={current?.id === d.id ? "" : "ghost"} style={{ width: "100%", textAlign: "left" }} onClick={() => setOpen(d.id)}>
                  {d.title} <span style={{ opacity: 0.8 }}>v{d.version}</span>
                </button>
                <div className="sub" style={{ marginTop: 3 }}>
                  {d.status === "approved" ? <span className="tag ok">승인 — {d.approved_by}</span> : <span className="tag warn">초안</span>}{" "}
                  <span className="tag">작성: {d.provider}</span>{" "}
                  {d.unsupported > 0 && <span className="tag bad">근거 미확인 {d.unsupported}</span>}
                </div>
              </div>
            ))}
          </div>
          {current && (
            <div className="card" style={{ flex: "2 1 520px" }}>
              <h2>{current.title}</h2>
              <p className="sub">{fmt(current.created_at)} · {current.kind_label}</p>
              {current.paragraphs.length > 0 ? current.paragraphs.map((p: any, i: number) => (
                <div key={i} style={{ borderLeft: `3px solid ${p.supported ? "#a9d3ca" : "#c0392b"}`, background: p.supported ? "transparent" : "#fbe9e6", padding: "6px 12px", marginBottom: 10 }}>
                  {p.heading && <h3>{p.heading}</h3>}
                  <p>{p.text}</p>
                  <ArticleRefs ids={p.articles} clauses={docs.data.clauses} />
                  {p.kind === "editorial" && <span className="tag">작성 메모(비규범)</span>}
                  {p.flag && <div><span className="tag bad">⚠ {p.flag}</span></div>}
                </div>
              )) : <p className="sub">구조화된 문단이 없는 문서입니다. 아래 미리보기를 확인하세요.</p>}
              <details open={current.paragraphs.length === 0}>
                <summary>HTML 미리보기</summary>
                <iframe className="preview" sandbox="" srcDoc={current.html} title={`${current.title} 미리보기`} />
              </details>
            </div>
          )}
        </div>
      )}
    </CustomerFrame>
  );
}
