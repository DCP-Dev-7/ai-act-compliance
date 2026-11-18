"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, useLoad } from "@/lib/api";
import { useSession } from "@/components/Shell";
import { DOC_KIND, isHighImpactStateKey } from "@/lib/labels";

type Scenario = {
  key: string; letter: string; name: string; title: string; industry: string; employees: number; description: string;
  allow_external: boolean; monthly_budget_usd: number; subscribed: boolean; current_state: Record<string, boolean>;
  selectable: boolean; lesson: string; points: string[]; documents: { kind: string; title: string }[];
};
type StateItem = { key: string; label: string; help: string; clause_ids: string[] };
type Catalog = {
  industries: string[];
  state_items: StateItem[];
  scenarios: Scenario[];
};

const EMPTY = { name: "", industry: "", employees: "", description: "", allow_external: false, monthly_budget_usd: "50", subscribed: false };

export default function NewCustomerPage() {
  const router = useRouter();
  const { user } = useSession();
  const allowed = user?.role === "consultant" || user?.role === "ops";
  const cat = useLoad<Catalog>(allowed ? "/scenarios" : null);
  const existing = useLoad<any[]>(allowed ? "/customers" : null);
  const [mode, setMode] = useState<"blank" | "scenario">("blank");
  const [scenario, setScenario] = useState("");
  const [form, setForm] = useState(EMPTY);
  // 설문 답: true=예, false=아니오, 키 없음=아직 답하지 않음(등록 불가)
  const [state, setState] = useState<Record<string, boolean>>({});
  const [tried, setTried] = useState(false); // 등록을 한 번 눌렀는지 — 그 뒤에만 '답하지 않음' 안내를 보인다
  const surveyRef = useRef<HTMLDivElement>(null);
  const [withContact, setWithContact] = useState(false);
  const [contact, setContact] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const selectable = (cat.data?.scenarios ?? []).filter((s) => s.selectable);
  const picked = selectable.find((s) => s.key === scenario);
  const ready = !!cat.data && !!existing.data; // 기존 회사명을 알아야 중복 없는 이름을 제안할 수 있다
  const items = cat.data?.state_items ?? [];
  const unanswered = items.filter((i) => typeof state[i.key] !== "boolean");

  function uniqueName(base: string): string {
    const taken = new Set((existing.data ?? []).map((c) => c.name));
    if (!taken.has(base)) return base;
    for (let i = 2; i < 100; i++) {
      const n = base.replace(" (가상)", ` ${i} (가상)`);
      if (!taken.has(n)) return n;
    }
    return base;
  }

  function pick(key: string) {
    const s = selectable.find((x) => x.key === key);
    if (!s) return;
    setMode("scenario");
    setScenario(key);
    setForm({ name: uniqueName(s.name), industry: s.industry, employees: String(s.employees), description: s.description,
      allow_external: s.allow_external, monthly_budget_usd: String(s.monthly_budget_usd), subscribed: s.subscribed });
    setState({ ...s.current_state });
    setTried(false);
    setError("");
  }
  function blank() {
    setMode("blank");
    setScenario("");
    setForm(EMPTY);
    setState({});
    setTried(false);
    setError("");
  }

  // 학습 화면에서 넘어온 경우(?scenario=b) 그 시나리오를 미리 고른다
  useEffect(() => {
    if (!cat.data || !existing.data) return;
    const q = new URLSearchParams(window.location.search).get("scenario");
    if (q && cat.data.scenarios.some((s) => s.key === q && s.selectable)) pick(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cat.data, existing.data]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!cat.data) return;
    if (unanswered.length > 0) {
      setTried(true);
      setError(`‘4. 현재 이행 상태’에서 답하지 않은 문항이 ${unanswered.length}개 있습니다. 문항마다 예 또는 아니오를 골라 주세요.`);
      const first = surveyRef.current?.querySelector<HTMLInputElement>(`input[name="q-${unanswered[0].key}"]`);
      first?.focus();
      first?.closest(".q")?.scrollIntoView({ block: "center" });
      return;
    }
    setBusy(true);
    try {
      const body: any = {
        name: form.name, industry: form.industry, employees: Number(form.employees || 0), description: form.description,
        allow_external: form.allow_external, monthly_budget_usd: Number(form.monthly_budget_usd || 0), subscribed: form.subscribed,
        current_state: Object.fromEntries(items.map((i) => [i.key, state[i.key] === true])),
        scenario: mode === "scenario" ? scenario : "",
      };
      if (withContact) body.contact = contact;
      const c = await api("/customers", { json: body });
      router.push(`/customers/${c.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  function question(i: StateItem) {
    const v = state[i.key];
    const missing = tried && typeof v !== "boolean";
    const set = (val: boolean) => setState((prev) => ({ ...prev, [i.key]: val }));
    return (
      <div key={i.key} className={`q${missing ? " missing" : ""}`}>
        <div className="qtext">
          <span id={`ql-${i.key}`}><b>{i.label}</b></span>{" "}
          {i.clause_ids.map((c) => <Link key={c} href={`/kb#${c}`} target="_blank" className="tag" style={{ marginLeft: 4 }}>{c.startsWith("art31") ? "제31조" : c === "art34" ? "제34조" : c}</Link>)}
          <span className="hint" id={`qh-${i.key}`}>{i.help}</span>
        </div>
        <div className="qans">
          <div className="seg" role="radiogroup" aria-labelledby={`ql-${i.key}`} aria-describedby={`qh-${i.key}${missing ? ` qe-${i.key}` : ""}`}
            aria-required="true" aria-invalid={missing || undefined}>
            <label className={v === true ? "on yes" : ""}>
              <input type="radio" name={`q-${i.key}`} value="yes" checked={v === true} onChange={() => set(true)} />
              <span>예<small>(하고 있음)</small></span>
            </label>
            <label className={v === false ? "on no" : ""}>
              <input type="radio" name={`q-${i.key}`} value="no" checked={v === false} onChange={() => set(false)} />
              <span>아니오<small>(안 하고 있음)</small></span>
            </label>
          </div>
          {missing && <span className="qerr" id={`qe-${i.key}`} role="alert">예 또는 아니오를 선택하세요</span>}
        </div>
      </div>
    );
  }

  if (user && !allowed) return <div className="msg err">고객사 등록은 컨설턴트·운영자만 할 수 있습니다.</div>;

  return (
    <>
      <p className="sub" style={{ margin: 0 }}><Link href="/">고객사</Link> /</p>
      <h1>고객사 등록</h1>
      <p className="sub">새 고객사를 만들면 1단계(자료 접수)부터 시작합니다. 이 데모는 가상 데이터 전용입니다 — 실제 회사명·개인정보를 넣지 마세요.</p>
      {cat.error && <div className="msg err">{cat.error}</div>}

      <form onSubmit={submit}>
        <div className="card">
          <h2>1. 어떻게 시작할까요?</h2>
          {!ready && <p className="sub">불러오는 중…</p>}
          <div className="choice" hidden={!ready}>
            <label className={`pick${mode === "blank" ? " on" : ""}`}>
              <input type="radio" name="mode" checked={mode === "blank"} onChange={blank} />
              <span><b>빈 고객으로 시작 (자료 직접 입력)</b><span className="hint">회사 정보만 등록하고, 설문·소개서 같은 자료는 등록 뒤에 직접 올립니다.</span></span>
            </label>
            <label className={`pick${mode === "scenario" ? " on" : ""}`}>
              <input type="radio" name="mode" checked={mode === "scenario"} onChange={() => pick(scenario || selectable[0]?.key || "")} disabled={selectable.length === 0} />
              <span><b>연습 시나리오로 시작</b><span className="hint">가상 회사를 골라 폼과 자료를 자동으로 채웁니다. 시나리오마다 판정 결과가 달라 법을 익히기 좋습니다.</span></span>
            </label>
          </div>
          {mode === "scenario" && (
            <>
              <div className="scenarios" role="radiogroup" aria-label="연습 시나리오">
                {selectable.map((s) => (
                  <label key={s.key} className={`pick${scenario === s.key ? " on" : ""}`}>
                    <input type="radio" name="scenario" checked={scenario === s.key} onChange={() => pick(s.key)} />
                    <span><b>{s.letter}사 <span className="tag warn">가상</span></b><span>{s.title}</span></span>
                  </label>
                ))}
              </div>
              {picked && (
                <div className="msg info" style={{ marginTop: 12, marginBottom: 0 }}>
                  <b>이 시나리오에서 배울 점</b> — {picked.lesson}
                  <div style={{ marginTop: 6 }}>함께 접수되는 가상 자료 {picked.documents.length}건: {picked.documents.map((d) => `${d.title.replace("[가상] ", "")}(${DOC_KIND[d.kind] ?? d.kind})`).join(", ")}</div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="row">
          <div className="card">
            <h2>2. 회사 정보</h2>
            <label htmlFor="name">회사명</label>
            <input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={100} placeholder="예: F사 (가상)" />
            <p className="hint">목록에 표시되는 이름입니다. 이미 있는 이름은 쓸 수 없습니다. 데모이므로 실제 회사명 대신 ‘○사 (가상)’처럼 적으세요.</p>

            <label htmlFor="industry">업종</label>
            <select id="industry" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} required>
              <option value="">선택하세요</option>
              {(cat.data?.industries ?? []).map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
            <p className="hint">의료·채용·금융처럼 법이 정한 ‘고영향 영역’과 가까운 업종인지 미리 가늠하는 용도입니다. 판정 자체는 업종이 아니라 AI 기능별 사실로 합니다.</p>

            <label htmlFor="employees">직원 수</label>
            <input id="employees" type="number" min={0} max={1000000} value={form.employees} onChange={(e) => setForm({ ...form, employees: e.target.value })} required />
            <p className="hint">회사 규모를 가늠하기 위한 참고 정보입니다. 이 법의 의무는 직원 수로 달라지지 않습니다.</p>

            <label htmlFor="description">서비스 소개</label>
            <textarea id="description" rows={4} maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="예: [가상] 어떤 서비스를 누구에게 제공하고, AI를 어디에 쓰는지" />
            <p className="hint">한두 문장이면 됩니다. 고객사 화면 맨 위에 표시됩니다. 판정에는 쓰이지 않습니다(판정은 접수 자료로 합니다).</p>
          </div>

          <div className="card">
            <h2>3. 데이터 정책·구독</h2>
            <label className="check">
              <input type="checkbox" checked={form.allow_external} onChange={(e) => setForm({ ...form, allow_external: e.target.checked })} />
              <span><b>외부 LLM 호출 허용</b></span>
            </label>
            <p className="hint">
              <b>허용</b>: 고객 자료를 외부 AI(예: Anthropic API)에 보내 분석할 수 있습니다. 보내기 전에 이름·전화번호·이메일 같은 개인정보를 가립니다(비식별화 후 전송).<br />
              <b>끄면 외부 반출 금지</b>: 고객 자료가 밖으로 나가지 않습니다. 사내 추론 서버가 있으면 그것을, 없으면 mock(규칙)만 씁니다. 민감한 자료를 다루는 고객은 꺼 두세요.<br />
              지금처럼 LLM 모드가 mock이면 어느 쪽이든 외부 호출이 없습니다.
            </p>

            <label htmlFor="budget">월 AI 예산 (USD)</label>
            <input id="budget" type="number" min={0} max={100000} step="0.01" value={form.monthly_budget_usd} onChange={(e) => setForm({ ...form, monthly_budget_usd: e.target.value })} required />
            <p className="hint">이 고객사 작업에 쓸 외부 AI 비용의 한 달 상한입니다. 넘으면 외부 호출을 멈추고 mock으로 대체합니다. mock 모드에서는 비용이 0입니다.</p>

            <label className="check">
              <input type="checkbox" checked={form.subscribed} onChange={(e) => setForm({ ...form, subscribed: e.target.checked })} />
              <span><b>구독 (증적 보관·변경 감시)</b></span>
            </label>
            <p className="hint">진단이 끝난 뒤에도 증적을 계속 보관하고, 법령이나 서비스가 바뀌면 다시 볼 일을 알려 주는 월 구독입니다. 구독 고객만 주간 기술 점검·월간 보고서 대상이 됩니다.</p>

            <h2 style={{ marginTop: 18 }}>5. 고객 담당자 로그인 (선택)</h2>
            <label className="check">
              <input type="checkbox" checked={withContact} onChange={(e) => setWithContact(e.target.checked)} />
              <span><b>고객 담당자 계정 만들기</b></span>
            </label>
            <p className="hint">고객 담당자는 자기 회사 화면만 볼 수 있고 자료를 올릴 수 있지만, 판정 확정·문서 승인은 할 수 없습니다. 고객 쪽 화면을 시연하려면 만드세요.</p>
            {withContact && (
              <>
                <label htmlFor="cemail">로그인 이메일</label>
                <input id="cemail" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} required placeholder="예: owner@f-company.example" autoComplete="off" />
                <p className="hint">로그인 아이디로 씁니다. 메일은 발송되지 않습니다. 가상 주소(…@….example)를 쓰세요.</p>
                <label htmlFor="cpw">비밀번호 (8자 이상)</label>
                <input id="cpw" type="text" value={contact.password} onChange={(e) => setContact({ ...contact, password: e.target.value })} required minLength={8} autoComplete="off" />
                <p className="hint">컨설턴트가 정해 담당자에게 전달합니다. 서버에는 해시로만 저장되어 나중에 다시 볼 수 없으니 적어 두세요.</p>
                <label htmlFor="cname">담당자 이름 (선택)</label>
                <input id="cname" value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} placeholder="예: 김가상 매니저" />
                <p className="hint">화면 오른쪽 위에 표시됩니다. 비우면 ‘회사명 담당자’로 표시합니다.</p>
              </>
            )}
          </div>
        </div>

        <div className="card">
          <h2>4. 현재 이행 상태 (설문 8문항)</h2>
          <p className="sub">
            문항마다 지금 하고 있으면 <b>예</b>, 안 하고 있으면 <b>아니오</b>를 고르세요. 8문항 모두 답해야 등록할 수 있습니다.
            갭 리포트가 ‘법이 요구하는 것’과 여기 답을 비교해 빠진 것을 찾습니다.
            {mode === "scenario" && " 연습 시나리오의 기본 답이 미리 선택되어 있으며, 바꿀 수 있습니다."}
          </p>
          <div ref={surveyRef}>
            <div className="qlist">
              {items.filter((i) => !isHighImpactStateKey(i.key)).map(question)}
            </div>
            <section className="qbox" aria-labelledby="qbox-title">
              <h3 id="qbox-title">고영향 AI인 경우에만 해당 (제34조)</h3>
              <p className="hint">
                의료·채용·대출·교육 평가 등 고영향 분야의 AI라면 아래 항목도 필요합니다.
                해당 없으면 ‘아니오’로 두셔도 갭 리포트에서 고영향이 아닌 경우 의무로 잡히지 않습니다.
              </p>
              <div className="qlist">
                {items.filter((i) => isHighImpactStateKey(i.key)).map(question)}
              </div>
            </section>
          </div>
        </div>

        {error && <div className="msg err" role="alert">{error}</div>}
        <div className="actions">
          <button type="submit" disabled={busy || !allowed}>{busy ? "등록 중…" : mode === "scenario" ? "등록하고 시나리오 자료 접수" : "고객사 등록"}</button>
          <Link className="btn ghost" href="/">취소</Link>
          <span className="hint">등록 내용은 감사 로그에 남습니다(비밀번호 제외).</span>
        </div>
      </form>
    </>
  );
}
