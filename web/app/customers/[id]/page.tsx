"use client";
import Link from "next/link";
import { useState } from "react";
import { api, fmt, useLoad } from "@/lib/api";
import { Action, CustomerFrame, useCustomer } from "@/components/CustomerFrame";
import { useSession } from "@/components/Shell";
import { DOC_KIND, isHighImpactStateKey } from "@/lib/labels";
import { STEP_HELP } from "@/lib/learn";
import docExamples from "@/lib/docExamples.json";

type DocExample = { title: string; content: string; tip: string };
const EXAMPLES = docExamples as Record<string, DocExample>;

export default function CustomerOverview() {
  const { id, customer, reloadCustomer, customerError } = useCustomer();
  const { user, meta } = useSession();
  const docs = useLoad<any[]>(`/customers/${id}/documents`);
  const audit = useLoad<any[]>(`/audit?customer_id=${id}&limit=12`);
  const cat = useLoad<any>("/scenarios");
  const [form, setForm] = useState({ kind: "other", title: "", content: "" });
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const base = `/customers/${id}`;

  async function reloadAll() {
    await Promise.all([reloadCustomer(), docs.reload(), audit.reload()]);
  }
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api(`${base}/documents`, { json: form });
      setForm({ kind: "other", title: "", content: "" });
      setMsg("자료를 접수했습니다.");
      await reloadAll();
    } catch (e2) {
      setErr((e2 as Error).message);
    }
  }
  const canUpload = user?.role === "customer" || user?.role === "consultant";
  const si = customer?.state_index ?? 0;
  const steps: { label: string; desc: string; el: React.ReactNode; min: number }[] = [
    { label: "1. 자료 접수", desc: "설문·소개서·약관·개발 문서를 올립니다.", min: 0,
      el: !customer ? null : !customer.has_samples
        ? <span className="hint">빈 고객입니다. 아래 ‘자료 올리기’로 직접 입력하세요.</span>
        : <Action label="샘플 자료 불러오기(가상)" path={`${base}/documents/load-samples`} roles={["customer", "consultant"]} onDone={reloadAll} ghost /> },
    { label: "2. AI 인벤토리 추출", desc: "자료에서 AI 시스템과 사실을 뽑고 인용 근거를 붙입니다.", min: 0,
      el: <Action label="인벤토리 추출" path={`${base}/inventory/extract`} roles={["consultant"]} onDone={reloadAll} /> },
    { label: "3. 판정 초안", desc: "법령 규칙(결정 트리)으로 초안을 만듭니다.", min: 1,
      el: <Action label="판정 초안 생성" path={`${base}/classify`} roles={["consultant"]} onDone={reloadAll} /> },
    { label: "4. 판정 확정", desc: "컨설턴트가 근거를 검토하고 확정합니다.", min: 2, el: <Link className="btn ghost" href={`${base}/classification`}>판정 화면으로</Link> },
    { label: "5. 갭 리포트", desc: "의무와 현재 이행 상태를 비교합니다.", min: 3,
      el: <Action label="갭 리포트 생성" path={`${base}/gap-report`} roles={["consultant"]} onDone={reloadAll} /> },
    { label: "6. 문서 초안", desc: "고지 문구 3종, 약관 조항 등 초안을 만듭니다.", min: 4,
      el: <Action label="문서 초안 생성" path={`${base}/generated-documents/generate`} roles={["consultant"]} onDone={reloadAll} /> },
    { label: "7. 승인", desc: "컨설턴트가 문서 초안을 승인합니다.", min: 5,
      el: <Action label="문서 승인" path={`${base}/approve`} roles={["consultant"]} onDone={reloadAll} /> },
    { label: "8. 증적 보관", desc: "확정 판정서와 승인 문서를 해시 체인에 보관합니다(5년).", min: 6,
      el: <Action label="증적 보관" path={`${base}/evidence/store-package`} roles={["consultant"]} onDone={reloadAll} /> },
  ];

  const stateEntries = Object.entries(customer?.current_state ?? {}) as [string, boolean][];
  const stateRow = ([k, v]: [string, boolean]) => (
    <li key={k}>{meta?.state_labels[k] ?? k}: {v ? <span className="tag ok">예</span> : <span className="tag bad">아니오</span>}</li>
  );

  const sc = (cat.data?.scenarios ?? []).find((x: any) => x.key === customer?.scenario);

  return (
    <CustomerFrame customer={customer} id={id}>
      {customerError && <div className="msg err">{customerError}</div>}
      {customer && sc && (
        <div className="msg info">
          <b>연습 시나리오 {sc.letter} <span className="tag warn">가상</span></b> — {sc.lesson}
          <details style={{ marginTop: 4 }}>
            <summary>이 시나리오에서 볼 것</summary>
            <ul className="plain" style={{ marginTop: 6 }}>
              {sc.points.map((x: string, i: number) => <li key={i}>{x}</li>)}
              <li>예상 갭: {sc.expected_gaps.length === 0 ? "0건(의무 거의 없음)" : `${sc.expected_gaps.length}건 (${sc.expected_gaps.join(", ")})`} — 기본 설문 답 기준</li>
            </ul>
            <Link href="/learn">AI 기본법 한눈에에서 다른 시나리오와 비교 →</Link>
          </details>
        </div>
      )}
      {customer && (
        <div className="row">
          <div className="card">
            <h2>고객사 정보 <span className="tag warn">가상 데이터</span></h2>
            <p>{customer.description}</p>
            <dl className="kv">
              {customer.industry && <><dt>업종</dt><dd>{customer.industry}</dd></>}
              <dt>직원 수</dt><dd>{customer.employees}명</dd>
              <dt>구독(증적 보관·변경 감시)</dt><dd>{customer.subscribed ? "구독 중" : "미구독"}</dd>
              <dt>현재 이행 상태(설문)</dt>
              <dd>
                {Object.keys(customer.current_state).length === 0 ? <span className="sub">설문 접수 전</span> : (
                  <>
                    <ul className="plain">{stateEntries.filter(([k]) => !isHighImpactStateKey(k)).map(stateRow)}</ul>
                    {stateEntries.some(([k]) => isHighImpactStateKey(k)) && (
                      <div className="qbox ro">
                        <h3>고영향 AI인 경우에만 해당 (제34조)</h3>
                        <ul className="plain">{stateEntries.filter(([k]) => isHighImpactStateKey(k)).map(stateRow)}</ul>
                      </div>
                    )}
                  </>
                )}
              </dd>
            </dl>
          </div>
          <div className="card">
            <h2>데이터 정책·LLM 사용</h2>
            <dl className="kv">
              <dt>외부 LLM 호출</dt>
              <dd>{customer.allow_external ? <span className="tag">허용(비식별화 후 전송)</span> : <span className="tag warn">금지 — 내부 추론 또는 mock만 사용</span>}</dd>
              <dt>실제 사용 공급자</dt><dd>{customer.llm.effective} <span className="sub">({customer.llm.effective_model})</span></dd>
              <dt>월 예산</dt><dd>${customer.monthly_budget_usd.toFixed(2)} 중 ${customer.month_cost_usd.toFixed(4)} 사용</dd>
            </dl>
            <div className="actions" style={{ marginTop: 12 }}>
              <Action label={customer.allow_external ? "외부 반출 금지로 전환" : "외부 LLM 허용으로 전환"} path={`${base}/policy`} method="PATCH"
                json={{ allow_external: !customer.allow_external }} roles={["consultant", "ops"]} onDone={reloadAll} ghost />
            </div>
            <p className="hint" style={{ marginTop: 8 }}>운영 환경에서는 고객 자료·증적이 DCP 국내 데이터센터 안에만 보관됩니다. 이 데모는 가상 데이터만 사용합니다.</p>
          </div>
        </div>
      )}

      <div className="card">
        <h2>진행 단계와 다음 작업</h2>
        <div className="tablewrap">
          <table>
            <tbody>
              {steps.map((s, i) => (
                <tr key={s.label}>
                  <td style={{ width: 170, opacity: si < s.min ? 0.5 : 1 }}><b>{s.label}</b> {(i < si || si === 7) && <span className="tag ok">완료</span>}{i === si && si < 7 && <span className="tag warn">현재</span>}</td>
                  <td className="sub">
                    <span style={{ opacity: si < s.min ? 0.5 : 1 }}>{s.desc}</span>
                    <details className="stephelp">
                      <summary>이 단계는?</summary>
                      <dl>
                        <dt>무슨 일이 일어나나</dt><dd>{STEP_HELP[i].what}</dd>
                        <dt>법적으로는</dt><dd>{STEP_HELP[i].legal}</dd>
                        <dt>컨설턴트가 확인할 것</dt><dd>{STEP_HELP[i].check}</dd>
                      </dl>
                    </details>
                  </td>
                  <td style={{ width: 300, opacity: si < s.min ? 0.5 : 1 }}>{s.el}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="hint">단계를 건너뛰면 서버가 거절합니다. 앞 단계를 다시 실행하면 그 단계로 되돌아갑니다(재평가). 단계마다 ‘이 단계는?’을 누르면 설명이 펼쳐집니다(요약 — 원문 확인 필요, 법률 자문 아님).</p>
      </div>

      <div className="row">
        <div className="card">
          <h2>접수 자료 ({docs.data?.length ?? 0}건)</h2>
          {msg && <div className="msg ok">{msg}</div>}
          {(docs.data ?? []).map((d) => (
            <details key={d.id} style={{ marginBottom: 8 }}>
              <summary><b>{d.title}</b> <span className="tag">{DOC_KIND[d.kind] ?? d.kind}</span> <span className="sub">문서 #{d.id} · {d.chars}자 · {d.uploaded_by} · {fmt(d.created_at)}</span></summary>
              <pre className="doc">{d.content}</pre>
            </details>
          ))}
          {docs.data?.length === 0 && <p className="sub">아직 접수된 자료가 없습니다. {customer?.has_samples ? "‘샘플 자료 불러오기(가상)’를 누르거나 직접 올려 주세요." : "오른쪽 ‘자료 올리기’로 직접 입력해 주세요."}</p>}
        </div>
        <div className="card">
          <h2>자료 올리기 (텍스트)</h2>
          {err && <div className="msg err" role="alert">{err}</div>}
          <form onSubmit={upload}>
            <label htmlFor="kind">종류</label>
            <select id="kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {Object.entries(DOC_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <label htmlFor="title">제목</label>
            <input id="title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
            <label htmlFor="content">내용 (실제 개인정보·영업비밀을 넣지 마세요)</label>
            <textarea id="content" rows={6} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} required />
            <div className="actions" style={{ marginTop: 10 }}>
              <button type="submit" disabled={!canUpload}>올리기</button>
              <button type="button" className="ghost" disabled={!canUpload} onClick={() => { const ex = EXAMPLES[form.kind]; if (ex) setForm({ ...form, title: ex.title, content: ex.content }); }}>‘{DOC_KIND[form.kind] ?? form.kind}’ 작성 예시 넣기</button>
              {!canUpload && <span className="hint"> 고객 담당자·컨설턴트 전용</span>}
            </div>
            <p className="hint" style={{ marginTop: 8 }}>
              <b>{DOC_KIND[form.kind] ?? form.kind}</b> 쓰는 요령: {EXAMPLES[form.kind]?.tip}
              {" "}mock 모드의 추출은 키워드 규칙이라 이 형식을 벗어나면 시스템을 못 찾을 수 있습니다. 종류를 바꾸면 예시와 요령도 바뀝니다.
            </p>
          </form>
        </div>
      </div>

      <div className="card">
        <h2>최근 감사 로그</h2>
        <div className="tablewrap">
          <table>
            <thead><tr><th>시각</th><th>수행자</th><th>역할</th><th>작업</th><th>대상</th></tr></thead>
            <tbody>
              {(audit.data ?? []).map((a) => (
                <tr key={a.id}><td>{fmt(a.at)}</td><td>{a.actor}</td><td>{a.role}</td><td className="mono">{a.action}</td><td>{a.entity} {a.entity_id}</td></tr>
              ))}
              {audit.data?.length === 0 && <tr><td colSpan={5} className="sub">기록 없음</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </CustomerFrame>
  );
}
