"use client";
import { fmt, useLoad } from "@/lib/api";
import { Action, ArticleRefs, CustomerFrame, useCustomer } from "@/components/CustomerFrame";
import { FIELD_LABELS } from "@/lib/labels";

const yes = (b: boolean, t = "필요", f = "해당 없음") => (b ? <span className="tag warn">{t}</span> : <span className="tag">{f}</span>);

export default function ClassificationPage() {
  const { id, customer, reloadCustomer } = useCustomer();
  const cls = useLoad<any>(`/customers/${id}/classifications`);
  const reload = async () => { await Promise.all([cls.reload(), reloadCustomer()]); };
  const clauses = cls.data?.clauses ?? {};
  return (
    <CustomerFrame customer={customer} id={id}>
      <div className="spread">
        <div>
          <h2>판정</h2>
          <p className="sub">규칙(결정 트리)이 만든 초안입니다. 컨설턴트가 근거를 확인하고 확정해야 효력이 생깁니다. 조문 내용은 요약 — 원문 확인 필요.</p>
        </div>
        <Action label="판정 초안 생성(재판정)" path={`/customers/${id}/classify`} roles={["consultant"]} onDone={reload} ghost />
      </div>
      {cls.error && <div className="msg err">{cls.error}</div>}
      {cls.data?.items.length === 0 && <div className="card"><p className="sub">판정 초안이 없습니다. 인벤토리 추출 후 ‘판정 초안 생성’을 실행하세요.</p></div>}
      {(cls.data?.items ?? []).map((c: any) => {
        const r = c.result;
        const facts: Record<string, any> = Object.fromEntries(c.system.facts.map((f: any) => [f.field, f]));
        return (
          <div className="card" key={c.id}>
            <div className="spread">
              <div>
                <h2>{c.system_name} <span className="sub">v{c.version} · KB {c.kb_version}</span></h2>
                {c.status === "confirmed"
                  ? <span className="tag ok">확정 — {c.confirmed_by} · {fmt(c.confirmed_at)}</span>
                  : <span className="tag warn">초안 — 컨설턴트 확정 전</span>}
              </div>
              {c.status !== "confirmed" && <Action label="이 판정 확정" path={`/classifications/${c.id}/confirm`} roles={["consultant"]} onDone={reload} />}
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <dl className="kv" style={{ flex: "1 1 320px" }}>
                <dt>사업자 지위</dt><dd><b>{r.operator_role_label}</b></dd>
                <dt>생성형 AI</dt><dd>{r.is_generative ? "해당" : "해당 없음"}</dd>
                <dt>제31조 사전 고지</dt><dd>{yes(r.art31.prior_notice)}</dd>
                <dt>제31조 생성물 표시</dt><dd>{yes(r.art31.output_labeling)}</dd>
                <dt>제31조 딥페이크 고지</dt><dd>{yes(r.art31.deepfake_notice)}</dd>
                <dt>내부 업무용 예외</dt><dd>{r.art31.internal_exemption ? <span className="tag ok">예외 적용</span> : <span className="tag">미적용</span>}</dd>
              </dl>
              <dl className="kv" style={{ flex: "1 1 320px" }}>
                <dt>고영향 여부</dt><dd><span className={`tag ${r.high_impact.status === "not_applicable" ? "" : "bad"}`}>{r.high_impact.status_label}</span></dd>
                <dt>1단계 영역</dt><dd>{r.high_impact.stage1_domain ? r.high_impact.domain_label : "해당 없음"}</dd>
                <dt>2단계 중대한 영향</dt><dd>{!r.high_impact.stage1_domain ? "판단 불필요(1단계 불충족)" : r.high_impact.stage2_significant === null ? "불명" : r.high_impact.stage2_significant ? "해당" : "해당 없음"}</dd>
                <dt>사람 검토 쟁점</dt><dd>{r.high_impact.issue ? <span className="tag warn">쟁점 — {r.high_impact.issue_note}</span> : "없음"}</dd>
                <dt>제33조 확인 요청</dt><dd>{yes(r.art33_recommended, "권고", "불필요")}</dd>
                <dt>제34·35조</dt><dd>{yes(r.art34_applicable, "준비 필요", "해당 없음")}</dd>
              </dl>
            </div>
            <h3 style={{ marginTop: 14 }}>판정 근거</h3>
            <ol className="plain rationale">
              {r.rationale.map((x: any, i: number) => (
                <li key={i}>
                  {x.text}
                  <div><ArticleRefs ids={x.articles} clauses={clauses} /></div>
                  {x.facts.map((f: string) => facts[f] && facts[f].quote ? (
                    <blockquote className="cite" key={f}>
                      [{FIELD_LABELS[f] ?? f}] “{facts[f].quote}”
                      <div className="src">{facts[f].source === "consultant" ? "컨설턴트 수정" : `문서 #${facts[f].doc_id} ${facts[f].doc_title ?? ""}`}</div>
                    </blockquote>
                  ) : null)}
                </li>
              ))}
            </ol>
            {r.assumptions.length > 0 && <p className="msg info" style={{ marginTop: 10 }}>가정: {r.assumptions.join(" / ")}</p>}
            <details>
              <summary>판정 버전 이력 ({c.history.length})</summary>
              <ul className="plain">
                {c.history.map((h: any) => <li key={h.id}>v{h.version} · {h.status === "confirmed" ? "확정" : h.status === "draft" ? "초안" : "대체됨"} · KB {h.kb_version} · {fmt(h.created_at)} {h.confirmed_by ? `· 확정자 ${h.confirmed_by}` : ""}</li>)}
              </ul>
            </details>
          </div>
        );
      })}
    </CustomerFrame>
  );
}
