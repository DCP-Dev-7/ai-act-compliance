"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/components/Shell";

const ACCOUNTS = [
  { email: "a-company@demo", label: "고객 담당자 — A사 (가상)" },
  { email: "consultant@demo", label: "컨설턴트 — 판정 확정·문서 승인" },
  { email: "ops@demo", label: "운영자 — 운영 콘솔·자동화 작업" },
];

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useSession();
  const [email, setEmail] = useState("consultant@demo");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", { json: { email, password } });
      await refresh();
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <h1>로그인</h1>
      <p className="sub">AI 기본법 준수 플랫폼 데모입니다. 모든 데이터는 가상이며 법률 자문이 아닙니다.</p>
      <form className="card" onSubmit={submit}>
        {error && <div className="msg err" role="alert">{error}</div>}
        <label htmlFor="email">이메일</label>
        <input id="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        <label htmlFor="pw">비밀번호</label>
        <input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        <div style={{ marginTop: 14 }}>
          <button type="submit" disabled={busy}>{busy ? "확인 중…" : "로그인"}</button>
        </div>
      </form>
      <div className="card demo-accounts">
        <h2>데모 계정 (비밀번호 demo1234)</h2>
        {ACCOUNTS.map((a) => (
          <button key={a.email} type="button" className="ghost" onClick={() => { setEmail(a.email); setPassword("demo1234"); }}>
            <b>{a.email}</b> <span className="sub">· {a.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
