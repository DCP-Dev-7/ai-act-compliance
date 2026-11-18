import type { Metadata } from "next";
import Markdown from "react-markdown";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import { guideHref, guideImg, loadGuide } from "@/lib/guide";

export const metadata: Metadata = { title: "사용 가이드 — AI 기본법 준수 플랫폼 (데모)" };
// 빌드할 때 web/content/USER_GUIDE.md 를 읽어 정적 페이지로 만든다(실행 중 API 호출 없음).
export const dynamic = "force-static";

export default function GuidePage() {
  const { title, body, headings } = loadGuide();
  const toc = headings.filter((h) => h.depth === 2 && h.text !== "목차");
  return (
    <>
      <h1>사용 가이드</h1>
      <p className="sub">{title.replace(/^사용 가이드\s*[:：]\s*/, "")}</p>
      <div className="guide">
        <nav className="guide-toc" aria-label="가이드 목차">
          <b>목차</b>
          <ul>
            {toc.map((h) => (
              <li key={h.id}><a href={`#${h.id}`}>{h.text}</a></li>
            ))}
          </ul>
          <a className="top" href="#guide-top">↑ 맨 위로</a>
        </nav>
        <article className="card guide-body" id="guide-top">
          <Markdown
            // 물결표 하나(B~E사, 1~13번)가 취소선으로 바뀌지 않게 한다
            remarkPlugins={[[remarkGfm, { singleTilde: false }]]}
            rehypePlugins={[rehypeSlug]}
            components={{
              a({ href, children }) {
                const l = guideHref(href ?? "");
                return l.external ? <a href={l.href} target="_blank" rel="noreferrer">{children}</a> : <a href={l.href}>{children}</a>;
              },
              img({ src, alt }) {
                const url = guideImg(typeof src === "string" ? src : "");
                return (
                  <a className="shot" href={url} target="_blank" rel="noreferrer" title="크게 보기">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={url} alt={alt ?? ""} loading="lazy" />
                  </a>
                );
              },
              table({ children }) {
                return <div className="tablewrap"><table>{children}</table></div>;
              },
            }}
          >
            {body}
          </Markdown>
        </article>
      </div>
    </>
  );
}
