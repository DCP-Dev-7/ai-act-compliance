"use client";
import Link from "next/link";
import { useLoad, fmt } from "@/lib/api";
import { useSession } from "@/components/Shell";

export default function Dashboard() {
  const { meta, user } = useSession();
  const { data, error, loading } = useLoad<any[]>("/customers");
  const states = meta?.workflow_states ?? [];
  return (
    <>
      <div className="spread">
        <div>
          <h1>고객사 현황</h1>
          <p className="sub">진단 → 체계 구축 → 증적 보관 구독의 진행 상태입니다. {user?.role === "customer" && "담당 고객사만 표시됩니다."}</p>
        </div>
        {user && user.role !== "customer" && (
          <div className="actions">
            <Link className="btn ghost" href="/learn">AI 기본법 한눈에</Link>
            <Link className="btn" href="/customers/new">고객사 등록</Link>
          </div>
        )}
      </div>
      {error && <div className="msg err">{error}</div>}
      <div className="card" style={{ marginTop: 14 }}>
        {loading ? <p className="sub">불러오는 중…</p> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>고객사</th><th>진행 상태</th><th>단계</th><th>데이터 정책</th><th>증적</th><th>재평가 작업</th><th>최근 변경</th></tr></thead>
              <tbody>
                {(data ?? []).map((c) => (
                  <tr key={c.id}>
                    <td><Link href={`/customers/${c.id}`}><b>{c.name}</b></Link><div className="sub">{c.industry ? `${c.industry} · ` : ""}직원 {c.employees}명 · {c.is_synthetic ? "가상 데이터" : ""}{c.scenario_letter ? ` · 시나리오 ${c.scenario_letter}` : ""}</div></td>
                    <td><span className={`tag ${c.state === "evidence_stored" ? "ok" : "navy"}`}>{c.state_label}</span></td>
                    <td>{c.state_index + 1} / {states.length || 8}</td>
                    <td>{c.allow_external ? <span className="tag">외부 LLM 허용</span> : <span className="tag warn">외부 반출 금지</span>}</td>
                    <td>{c.evidence_count}건</td>
                    <td>{c.open_tasks > 0 ? <span className="tag warn">미해결 {c.open_tasks}건</span> : "없음"}</td>
                    <td className="sub">{fmt(c.updated_at)}</td>
                  </tr>
                ))}
                {data && data.length === 0 && <tr><td colSpan={7}>고객사가 없습니다.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {user && user.role !== "customer" && (
        <p className="hint">처음이라면 <Link href="/learn">AI 기본법 한눈에</Link>를 먼저 읽고, ‘고객사 등록’에서 연습 시나리오(B~E사)를 골라 1단계부터 직접 돌려 보세요. 시나리오마다 판정 결과가 다릅니다. 화면별 설명은 <Link href="/guide#1-고객사-현황">사용 가이드에서 보기</Link>.</p>
      )}
    </>
  );
}
