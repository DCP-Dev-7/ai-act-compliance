"use client";
import { useState } from "react";
import { useLoad } from "@/lib/api";
import { Action, CustomerFrame, useCustomer } from "@/components/CustomerFrame";
import { useSession } from "@/components/Shell";
import { FIELD_LABELS, fmtValue } from "@/lib/labels";

export default function InventoryPage() {
  const { id, customer, reloadCustomer } = useCustomer();
  const { meta } = useSession();
  const systems = useLoad<any[]>(`/customers/${id}/systems`);
  const [note, setNote] = useState("");
  async function done(r: any) {
    setNote(`추출 완료 — 방식: ${r.provider}${r.note ? ` · ${r.note}` : ""}`);
    await Promise.all([systems.reload(), reloadCustomer()]);
  }
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>AI 인벤토리</h2>
          <p className="sub">자료에서 뽑은 AI 시스템과 사실입니다. 모든 사실에는 근거 문서와 인용 구간이 붙습니다. 판정은 이 사실만 사용합니다.</p>
        </div>
        <Action label="인벤토리 추출(다시 실행)" path={`/customers/${id}/inventory/extract`} roles={["consultant"]} onDone={done} />
      </div>
      {note && <div className="msg ok">{note}</div>}
      {systems.error && <div className="msg err">{systems.error}</div>}
      {systems.data?.length === 0 && <div className="card"><p className="sub">아직 추출된 시스템이 없습니다. 자료 접수 후 컨설턴트가 ‘인벤토리 추출’을 실행합니다.</p></div>}
      {(systems.data ?? []).map((s) => (
        <div className="card" key={s.id}>
          <div className="spread">
            <h2>{s.name}</h2>
            <span className="tag">추출 방식: {s.extracted_by}</span>
          </div>
          <div className="tablewrap">
            <table>
              <thead><tr><th style={{ width: 170 }}>속성</th><th style={{ width: 190 }}>값</th><th>인용 근거</th></tr></thead>
              <tbody>
                {s.facts.filter((f: any) => f.field !== "name").map((f: any) => (
                  <tr key={f.id}>
                    <td>{FIELD_LABELS[f.field] ?? f.field}</td>
                    <td>{f.field === "purpose" ? <span className="sub">(인용문 참조)</span> : <b>{fmtValue(f.field, f.value, meta?.domain_labels)}</b>}
                      {!f.supported && <div><span className="tag bad">근거 미확인</span></div>}</td>
                    <td>
                      {f.source === "extracted" && f.quote ? (
                        <blockquote className="cite">“{f.quote}”<div className="src">문서 #{f.doc_id} {f.doc_title} · 위치 {f.span_start}–{f.span_end}</div></blockquote>
                      ) : f.source === "consultant" ? <span className="tag navy">컨설턴트 수정</span> : <span className="sub">자료에 언급 없음 — 기본값 적용</span>}
                    </td>
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
