"use client";
import { useState } from "react";
import { api, fmt, useLoad } from "@/lib/api";
import { useSession } from "@/components/Shell";

export default function OpsPage() {
  const { user } = useSession();
  const ops = useLoad<any>(user && user.role !== "customer" ? "/ops/summary" : null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (user?.role === "customer") return <div className="msg err">운영 콘솔은 운영자·컨설턴트만 볼 수 있습니다.</div>;
  const s = ops.data;
  const isOps = user?.role === "ops";
  async function run(name: string, label: string) {
    setBusy(name);
    setMsg(null);
    try {
      const r = await api(`/ops/jobs/${name}/run`, { method: "POST" });
      setMsg({ ok: r.status === "ok", text: `${label}: ${r.status === "ok" ? "성공" : "실패"}` });
      await ops.reload();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy("");
    }
  }
  const g = s?.golden_runs[0];
  return (
    <>
      <h1>운영 콘솔</h1>
      <p className="sub">자동화 작업, 골든셋 회귀, 토큰·비용 사용량, 예산 상태입니다. <a href="/api/metrics" target="_blank" rel="noreferrer">/metrics</a> · <a href="/api/health" target="_blank" rel="noreferrer">/health</a></p>
      {ops.error && <div className="msg err">{ops.error}</div>}
      {msg && <div className={`msg ${msg.ok ? "ok" : "err"}`} role="status">{msg.text}</div>}
      {s && (
        <>
          <div className="row">
            <div className="card">
              <h2>LLM 구성</h2>
              <dl className="kv">
                <dt>활성 모드</dt><dd><b>{s.llm.configured}</b> <span className="sub">({s.llm.model})</span></dd>
                <dt>내부 추론 엔드포인트</dt><dd>{s.llm.internal_endpoint_configured ? "구성됨(openai_compatible)" : "미구성"}</dd>
                <dt>단가(USD/1M 토큰)</dt><dd>입력 ${s.pricing.input_per_mtok_usd} · 출력 ${s.pricing.output_per_mtok_usd}</dd>
                <dt>증적 백엔드</dt><dd>{s.evidence_backend}</dd>
                <dt>스케줄러</dt><dd>{s.scheduler_enabled ? "동작 중" : "꺼짐"}</dd>
              </dl>
            </div>
            <div className="card">
              <h2>골든셋 회귀 (합성 사례)</h2>
              {g ? (
                <>
                  <p style={{ fontSize: 26, margin: "0 0 4px" }}><b>{(g.rate * 100).toFixed(1)}%</b> <span className="sub" style={{ fontSize: 14 }}>일치율 ({g.matched}/{g.total}) · 임계 {(g.threshold * 100).toFixed(0)}%</span></p>
                  <p>{g.passed ? <span className="tag ok">통과 — 승격 가능</span> : <span className="tag bad">임계 미달 — 승격 차단</span>} <span className="sub">규칙 엔진 {(g.engine_rate * 100).toFixed(1)}% · {g.config} · {fmt(g.at)}</span></p>
                  {g.mismatches.length > 0 && (
                    <details><summary>불일치 {g.mismatches.length}건</summary>
                      <ul className="plain">{g.mismatches.map((m: any, i: number) => <li key={i}>{m.id} {m.title} <span className="mono">{JSON.stringify(m.diff)}</span></li>)}</ul>
                    </details>
                  )}
                </>
              ) : <p className="sub">아직 실행 기록이 없습니다. 아래에서 ‘골든셋 회귀’를 실행하세요.</p>}
              <h3 style={{ marginTop: 10 }}>모델·프롬프트 구성</h3>
              <ul className="plain">
                {s.model_configs.map((m: any) => <li key={m.name}><span className="mono">{m.name}</span> <span className={`tag ${m.status === "승격 차단" ? "bad" : m.status === "승격 가능" ? "ok" : ""}`}>{m.status}</span></li>)}
              </ul>
            </div>
          </div>

          <div className="card">
            <h2>자동화 작업</h2>
            <div className="tablewrap">
              <table>
                <thead><tr><th>작업</th><th>주기(Asia/Seoul)</th><th>다음 실행</th><th></th></tr></thead>
                <tbody>
                  {s.jobs.map((j: any) => (
                    <tr key={j.name}>
                      <td><b>{j.label}</b> <span className="mono sub">{j.name}</span></td>
                      <td>{j.schedule}</td>
                      <td>{fmt(j.next_run)}</td>
                      <td><button className="small" disabled={!isOps || busy !== ""} onClick={() => run(j.name, j.label)}>{busy === j.name ? "실행 중…" : "지금 실행"}</button>{!isOps && <span className="hint"> 운영자 전용</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 style={{ marginTop: 14 }}>최근 실행</h3>
            <div className="tablewrap">
              <table>
                <thead><tr><th>#</th><th>작업</th><th>구분</th><th>상태</th><th>시작</th><th>결과 요약</th></tr></thead>
                <tbody>
                  {s.job_runs.map((r: any) => (
                    <tr key={r.id}>
                      <td>{r.id}</td><td>{r.label}</td><td>{r.trigger === "manual" ? "수동" : "예약"}</td>
                      <td><span className={`tag ${r.status === "ok" ? "ok" : r.status === "failed" ? "bad" : "warn"}`}>{r.status === "ok" ? "성공" : r.status === "failed" ? "실패" : "실행 중"}</span></td>
                      <td>{fmt(r.started_at)}</td>
                      <td><details><summary>보기</summary><pre className="doc mono">{JSON.stringify(r.detail, null, 1)}</pre></details></td>
                    </tr>
                  ))}
                  {s.job_runs.length === 0 && <tr><td colSpan={6} className="sub">실행 기록 없음</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          <div className="row">
            <div className="card">
              <h2>고객별 예산</h2>
              <table>
                <thead><tr><th>고객사</th><th>데이터 정책</th><th>이번 달 사용</th><th>월 예산</th><th>상태</th></tr></thead>
                <tbody>
                  {s.budgets.map((b: any) => (
                    <tr key={b.customer_id}><td>{b.customer}</td><td>{b.allow_external ? "외부 허용" : "외부 금지"}</td><td>${b.spent_usd.toFixed(4)}</td><td>${b.budget_usd.toFixed(2)}</td>
                      <td><span className={`tag ${b.status === "정상" ? "ok" : "bad"}`}>{b.status}</span></td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <h2>토큰·비용 사용량 (고객·작업별)</h2>
              <div className="tablewrap">
                <table>
                  <thead><tr><th>고객사</th><th>작업</th><th>공급자</th><th>호출</th><th>입력 토큰</th><th>출력 토큰</th><th>비용(USD)</th></tr></thead>
                  <tbody>
                    {s.usage.map((u: any, i: number) => (
                      <tr key={i}><td>{u.customer}</td><td className="mono">{u.task}</td><td>{u.provider}</td><td>{u.calls}</td><td>{u.input_tokens.toLocaleString()}</td><td>{u.output_tokens.toLocaleString()}</td><td>{u.cost_usd.toFixed(4)}</td></tr>
                    ))}
                    {s.usage.length === 0 && <tr><td colSpan={7} className="sub">사용 기록 없음</td></tr>}
                  </tbody>
                </table>
              </div>
              <p className="hint">mock·내부 추론은 토큰만 추정 집계하며 비용은 0입니다.</p>
            </div>
          </div>
        </>
      )}
    </>
  );
}
