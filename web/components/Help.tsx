"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { TERM_HELP } from "@/lib/learn";

/** 용어 옆의 ? 버튼. 마우스를 올리거나 누르면 쉬운 설명과 법령 지식베이스 조문 링크를 보여 준다. */
export function Term({ k, children }: { k: string; children?: React.ReactNode }) {
  const t = TERM_HELP[k];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (!t) return <>{children}</>;
  return (
    <span className="term" ref={ref}>
      {children ?? t.title}
      <button type="button" className="helpbtn" aria-expanded={open} aria-label={`${t.title} 설명 보기`} onClick={() => setOpen(!open)}>?</button>
      <span className={`helppop${open ? " open" : ""}`} role="tooltip">
        <b>{t.title}</b>
        <span className="helptext">{t.text}</span>
        <Link href={`/kb#${t.clause}`}>조문 요약 보기: {t.clauseLabel} →</Link>
        <span className="helpnote">요약 — 원문 확인 필요</span>
      </span>
    </span>
  );
}
