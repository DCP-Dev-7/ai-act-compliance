import fs from "node:fs";
import path from "node:path";
import GithubSlugger from "github-slugger";

/** 원본은 docs/USER_GUIDE.md. scripts/sync_guide.sh 가 web/content 로 복사한다(직접 고치지 말 것). */
const GUIDE_FILE = path.join(process.cwd(), "content", "USER_GUIDE.md");
export const REPO_DOCS_URL = "https://github.com/DCP-Dev-7/ai-act-compliance/blob/main/docs/";

export type GuideHeading = { depth: number; text: string; id: string };

/** 마크다운 강조 기호를 뗀 제목 글자 */
function plain(s: string): string {
  return s.replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[`*_~]/g, "").trim();
}

/**
 * 가이드 본문과 옆 목차용 제목 목록.
 * 맨 위 `# 제목`은 화면의 h1 로 따로 쓰고 본문에서는 뺀다.
 * id 는 rehype-slug 와 같은 규칙(github-slugger)으로 같은 순서로 만들어 본문 제목의 id 와 일치한다.
 */
export function loadGuide(): { title: string; body: string; headings: GuideHeading[] } {
  const raw = fs.readFileSync(GUIDE_FILE, "utf8").replace(/\r\n/g, "\n");
  const m = raw.match(/^# (.+)\n/);
  const title = m ? plain(m[1]) : "사용 가이드";
  const body = m ? raw.slice(m[0].length) : raw;

  const slugger = new GithubSlugger();
  const headings: GuideHeading[] = [];
  let fenced = false;
  for (const line of body.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; continue; }
    if (fenced) continue;
    const h = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (!h) continue;
    const text = plain(h[2]);
    headings.push({ depth: h[1].length, text, id: slugger.slug(text) });
  }
  return { title, body, headings };
}

/** 가이드 안의 주소를 앱에서 열리는 주소로 바꾼다. */
export function guideHref(href: string): { href: string; external: boolean } {
  if (href.startsWith("#")) return { href, external: false };
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) return { href, external: true };
  if (href.startsWith("/")) return { href, external: false };
  // 저장소의 다른 파일(docs/ 기준 상대 경로)은 GitHub 로 보낸다
  return { href: new URL(href, REPO_DOCS_URL).toString(), external: true };
}

/** `guide/img/x.jpg`(docs/ 기준) → `/guide/img/x.jpg`(web/public) */
export function guideImg(src: string): string {
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("/")) return src;
  const clean = src.replace(/^\.\//, "");
  return clean.startsWith("guide/img/") ? `/${clean}` : new URL(clean, REPO_DOCS_URL).toString() + "?raw=true";
}
