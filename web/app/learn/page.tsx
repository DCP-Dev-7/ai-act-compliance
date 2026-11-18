"use client";
import Link from "next/link";
import { useLoad } from "@/lib/api";
import { useSession } from "@/components/Shell";
import { GAP_SHORT, HIGH_IMPACT_SHORT } from "@/lib/learn";

type Sys = {
  name: string; operator_role: string; is_generative: boolean; prior_notice: boolean; output_labeling: boolean;
  deepfake_notice: boolean; internal_exemption: boolean; high_impact_status: string; art33_recommended: boolean;
  art34_applicable: boolean; deemed_compliance_possible: boolean;
};
type Scenario = { key: string; letter: string; title: string; lesson: string; points: string[]; selectable: boolean; expected_gaps: string[]; systems: Sys[] };

const K = ({ id, children }: { id: string; children: React.ReactNode }) => <Link href={`/kb#${id}`} className="tag">{children}</Link>;

/** 결정 흐름의 한 칸: 질문 + 예/아니오일 때 생기는 일 + 해당 시나리오 */
function Step({ n, q, desc, yes, no, eg, kb }: { n: number; q: string; desc: string; yes: React.ReactNode; no: React.ReactNode; eg: string; kb: React.ReactNode }) {
  return (
    <li className="flowstep">
      <div className="flowq">
        <span className="flown" aria-hidden="true">{n}</span>
        <div>
          <h3>{q}</h3>
          <p>{desc}</p>
          <p className="sub" style={{ margin: 0 }}>{kb} · 예: {eg}</p>
        </div>
      </div>
      <div className="flowout">
        <div className="yes"><b>예 →</b> {yes}</div>
        <div className="no"><b>아니오 →</b> {no}</div>
      </div>
    </li>
  );
}

function art31(s: Sys): string {
  if (s.internal_exemption) return "예외(내부 업무용)";
  const parts = [s.prior_notice && "사전 고지", s.output_labeling && "생성물 표시", s.deepfake_notice && "딥페이크 명확 고지"].filter(Boolean);
  return parts.length ? parts.join(" + ") : "해당 없음";
}

export default function LearnPage() {
  const { user } = useSession();
  const cat = useLoad<{ scenarios: Scenario[] }>("/scenarios");
  const canRegister = user?.role === "consultant" || user?.role === "ops";
  return (
    <>
      <h1>AI 기본법 한눈에</h1>
      <p className="sub">처음 보는 분을 위한 5분 설명입니다. 다섯 가지 질문에 차례로 답하면 어떤 의무가 생기는지 알 수 있습니다.</p>
      <div className="msg info"><b>요약 — 원문 확인 필요 · 법률 자문 아님.</b> 이 화면은 <Link href="/kb">법령 지식베이스</Link>의 조문 요약을 쉬운 말로 풀어 쓴 것입니다. 실제 판단은 법령 원문과 전문가 검토를 거쳐야 합니다.</div>

      <div className="card">
        <h2>먼저 세 줄로</h2>
        <ul className="plain">
          <li><b>누구에게</b> — AI를 만들어 제공하는 회사(개발사업자)와, 남이 만든 AI를 붙여 제품·서비스를 제공하는 회사(이용사업자) 모두.</li>
          <li><b>무엇을</b> — 생성형 AI라면 이용자에게 <b>알리고 표시</b>해야 하고(제31조), 사람의 생명·신체·기본권에 큰 영향을 주는 <b>고영향 AI</b>라면 위험관리 같은 <b>책무</b>가 더해집니다(제34·35조).</li>
          <li><b>예외</b> — 회사 안에서만 쓰고 고객에게 제공하지 않으면 고지·표시 의무에서 빠집니다.</li>
        </ul>
        <div className="facts">
          <div><span className="sub">시행일</span><b>2026년 1월 22일</b><K id="enforcement">부칙·시행</K></div>
          <div><span className="sub">과태료 계도기간</span><b>1년 이상 운영</b><span className="sub">계도기간에도 의무 자체는 유효</span></div>
          <div><span className="sub">과태료</span><b>3천만원 이하</b><span className="sub">사전 고지 위반, 국내대리인 미지정, 시정명령 불이행 등</span><K id="art43">제43조</K></div>
          <div><span className="sub">고영향 확인 요청 회신</span><b>30일 이내</b><span className="sub">1회 연장 시 최대 60일 · 이의 10일 내 재확인</span><K id="art33">제33조</K></div>
        </div>
      </div>

      <div className="card">
        <h2>다섯 가지 질문 (결정 흐름)</h2>
        <p className="sub">이 플랫폼의 판정 규칙도 같은 순서로 움직입니다. AI 기능(시스템) 하나마다 따로 답합니다.</p>
        <ol className="flow">
          <Step n={1} q="누가 대상인가 — AI를 만들거나, AI를 붙여 서비스를 제공하나?"
            desc="직접 개발해 제공하면 ‘개발사업자’, 외부 AI(API 등)를 이용해 제품·서비스를 제공하면 ‘이용사업자’입니다. 외부 API만 붙여 써도 대상이 될 수 있습니다."
            yes={<>이 법의 인공지능사업자. 지위는 서비스(시스템)별로 정합니다. 다음 질문으로.</>}
            no={<>AI를 쓰지 않는 서비스는 여기서 끝.</>}
            eg="A·D·E사는 이용사업자, B·C사는 개발사업자" kb={<K id="art2-operator">제2조 사업자</K>} />
          <Step n={2} q="생성형인가 — 글·소리·그림·영상을 만들어 내나?"
            desc="입력을 바탕으로 새로운 결과물을 만들어 내면 생성형 AI입니다. 점수를 매기거나 분류만 하는 AI는 생성형이 아닙니다."
            yes={<>제31조 투명성 의무의 후보. <b>사전 고지</b>(AI 기반 서비스임을 미리 알림)와 <b>생성물 표시</b>(AI가 만들었다는 표시). 실제와 구분하기 어려운 소리·이미지·영상이면 <b>명확한 고지·표시</b>까지.</>}
            no={<>표시 의무는 없음. 다만 4번에서 고영향이면 사전 고지는 필요.</>}
            eg="A·D·E사는 생성형, B·C사는 아님. E사는 실제 목소리 수준이라 명확한 고지까지" kb={<><K id="art2-generative">제2조 생성형</K> <K id="art31-1">제31조 고지</K> <K id="art31-2">표시</K> <K id="art31-3">딥페이크</K></>} />
          <Step n={3} q="고객(이용자)에게 제공하나?"
            desc="같은 AI라도 고객에게 제품·서비스로 제공하는지, 직원이 내부 업무에만 쓰는지에 따라 달라집니다."
            yes={<>2번의 고지·표시 의무가 실제로 적용됩니다. 고지는 약관·계약서·서비스 화면 중 어디에 해도 됩니다.</>}
            no={<><b>내부 업무용 예외</b> — 고지·표시 의무 대상에서 제외되는 것으로 안내됩니다. 내부용이라는 사실을 기록해 둡니다. (이 데모는 내부용이라도 고영향 영역이면 예외를 적용하지 않습니다.)</>}
            eg="D사 전체, A사의 ‘고객문의 요약’은 내부 업무용" kb={<K id="art31-exception">제31조 예외</K>} />
          <Step n={4} q="고영향 영역인가 — 그리고 중대한 영향을 주나?"
            desc="두 단계로 봅니다. ① 법이 정한 영역인가: 의료, 에너지·먹는물 등 필수 인프라, 원자력, 범죄 수사 생체인식, 채용·대출 심사, 교통수단 주요 운영, 공공서비스 핵심 의사결정, 학생 평가. ② 그 쓰임이 생명·신체·기본권에 중대한 영향을 주거나 위험을 낳을 우려가 있는가."
            yes={<>고영향 AI일 수 있습니다. 5번 질문으로. (생성형이 아니어도 사전 고지가 필요해집니다.)</>}
            no={<>고영향 아님 — 제34·35조 책무 없음. 2·3번에서 정해진 의무만 남습니다.</>}
            eg="B사(채용), C사(의료)는 영역 해당. A·D·E사는 해당 없음" kb={<K id="art2-highimpact">제2조 고영향</K>} />
          <Step n={5} q="사람이 실질적으로 검토·통제하나?"
            desc="AI 결과를 사람이 직접 살펴보고 최종 결정을 내리는지 봅니다. 내용을 보지 않고 승인만 누르는 것은 ‘형식적 검토’입니다."
            yes={<><b>제외 가능(쟁점)</b> — 고영향에서 빠질 수 있지만 해석상 쟁점이므로 과기정통부 <b>확인 요청</b>을 권고합니다(제33조).</>}
            no={<><b>고영향 후보</b> — 제34조 책무와 제35조 영향평가 준비가 필요합니다. 형식적 검토뿐이면 후보로 보되 쟁점이라 확인 요청도 권고합니다.</>}
            eg="C사는 전문의가 직접 판독 → 제외 가능. B사는 검토 없이 자동 탈락 → 후보" kb={<><K id="art33">제33조 확인</K> <K id="art34">제34조 책무</K> <K id="art35">제35조 영향평가</K></>} />
        </ol>
      </div>

      <div className="card">
        <h2>그래서 생기는 의무 목록</h2>
        <div className="tablewrap">
          <table>
            <thead><tr><th>언제</th><th>해야 할 일</th><th>조문</th></tr></thead>
            <tbody>
              <tr><td>생성형 또는 고영향 AI를 고객에게 제공</td><td><b>사전 고지</b> — AI 기반으로 운용된다는 사실을 미리 알림(약관·계약서·화면)</td><td><K id="art31-1">제31조</K></td></tr>
              <tr><td>생성형 AI를 고객에게 제공</td><td><b>생성물 표시</b> — 눈에 보이는 표시 또는 워터마크·메타데이터</td><td><K id="art31-2">제31조</K></td></tr>
              <tr><td>실제와 구분하기 어려운 소리·이미지·영상</td><td><b>명확한 고지·표시</b> — 이용자가 분명히 알아볼 수 있게</td><td><K id="art31-3">제31조</K></td></tr>
              <tr><td>고영향인지 불명확</td><td><b>확인 요청 검토</b> — 과기정통부에 요청할 수 있음(30일 내 회신)</td><td><K id="art33">제33조</K></td></tr>
              <tr><td>고영향 AI</td><td><b>책무 5가지</b> — 위험관리 방안, 설명 방안, 이용자 보호 방안, 사람의 관리·감독(비상정지), 문서 5년 보관</td><td><K id="art34">제34조</K></td></tr>
              <tr><td>고영향 AI</td><td><b>영향평가</b> — 기본권에 미치는 영향을 미리 평가하도록 노력(노력 의무)</td><td><K id="art35">제35조</K></td></tr>
              <tr><td>다른 법으로 같은 수준의 조치를 이미 함</td><td><b>이행 간주</b> — 예: 디지털의료제품법. 증빙을 확보해 둠</td><td><K id="deemed">타법 관계</K></td></tr>
            </tbody>
          </table>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>그 밖에: 학습 누적 연산량이 10^26 FLOPs 이상인 초대형 AI의 안전성 확보 의무(<Link href="/kb#art32">제32조</Link>, 현재 국내에는 해당 시스템이 없는 것으로 알려짐), 국내에 주소·영업소가 없는 일정 규모 이상 사업자의 국내대리인 지정(<Link href="/kb#art36">제36조</Link>).</p>
      </div>

      <div className="card">
        <h2>연습 시나리오 5개로 보기 <span className="tag warn">전부 가상</span></h2>
        <p className="sub">같은 흐름에 다섯 회사를 넣으면 결과가 이렇게 달라집니다. A사는 처음부터 들어 있고, B~E사는 ‘고객사 등록’에서 골라 직접 돌려 볼 수 있습니다.</p>
        {cat.error && <div className="msg err">{cat.error}</div>}
        <div className="tablewrap">
          <table className="scn">
            <thead><tr><th>시나리오</th><th>AI 기능</th><th>생성형</th><th>제31조 (고지·표시)</th><th>고영향</th><th>제33조 확인 요청</th><th>예상 갭</th></tr></thead>
            <tbody>
              {(cat.data?.scenarios ?? []).map((s) => s.systems.map((y, i) => (
                <tr key={s.key + y.name} className={i === 0 ? "first" : ""}>
                  {i === 0 && (
                    <td rowSpan={s.systems.length} style={{ minWidth: 200, maxWidth: 280 }}>
                      <b>{s.letter}사</b> <span className="sub">{s.title}</span>
                      <div className="lesson">{s.lesson}</div>
                      {s.selectable && canRegister && <Link href={`/customers/new?scenario=${s.key}`}>이 시나리오로 등록 →</Link>}
                    </td>
                  )}
                  <td className="sysname">{y.name}<div className="sub">{y.operator_role === "developer" ? "개발사업자" : "이용사업자"}</div></td>
                  <td className="nw">{y.is_generative ? "예" : "아니오"}</td>
                  <td>{y.internal_exemption ? <span className="tag ok">{art31(y)}</span> : y.prior_notice ? <span className="tag warn">{art31(y)}</span> : art31(y)}</td>
                  <td><span className={`tag ${y.high_impact_status === "not_applicable" ? "" : "bad"}`}>{HIGH_IMPACT_SHORT[y.high_impact_status]}</span>{y.art34_applicable && <div className="sub">제34·35조 준비</div>}{y.deemed_compliance_possible && <div className="sub">타법 이행 간주 가능</div>}</td>
                  <td>{y.art33_recommended ? <span className="tag warn">권고</span> : "불필요"}</td>
                  {i === 0 && (
                    <td rowSpan={s.systems.length}>
                      {s.expected_gaps.length === 0 ? <span className="tag ok">0건 — 의무 거의 없음</span> : (
                        <><b>{s.expected_gaps.length}건</b><div className="sub">{s.expected_gaps.map((g) => GAP_SHORT[g] ?? g).join(" · ")}</div></>
                      )}
                    </td>
                  )}
                </tr>
              )))}
            </tbody>
          </table>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>‘예상 갭’은 각 시나리오의 기본 설문 답으로 돌렸을 때의 결과입니다. 등록할 때 설문 답을 바꾸면 달라집니다. 기대 결과는 이 데모의 규칙 해석이며 법적 판단이 아닙니다.</p>
      </div>

      <div className="card">
        <h2>시나리오마다 배울 점</h2>
        <div className="row">
          {(cat.data?.scenarios ?? []).map((s) => (
            <div key={s.key} style={{ flex: "1 1 300px" }}>
              <h3>{s.letter}사 — {s.title}</h3>
              <ul className="plain">{s.points.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
