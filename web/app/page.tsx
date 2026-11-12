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
      <h1>고객사 현황</h1>
      <p className="sub">진단 → 체계 구축 → 증적 보관 구독의 진행 상태입니다. {user?.role === "customer" && "담당 고객사만 표시됩니다."}</p>
      {error && <div className="msg err">{error}</div>}
      <div className="card" style={{ marginTop: 14 }}>
        {loading ? <p className="sub">불러오는 중…</p> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>고객사</th><th>진행 상태</th><th>단계</th><th>데이터 정책</th><th>증적</th><th>재평가 작업</th><th>최근 변경</th></tr></thead>
              <tbody>
                {(data ?? []).map((c) => (
                  <tr key={c.id}>
                    <td><Link href={`/customers/${c.id}`}><b>{c.name}</b></Link><div className="sub">직원 {c.employees}명 · {c.is_synthetic ? "가상 데이터" : ""}</div></td>
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
    </>
  );
}
