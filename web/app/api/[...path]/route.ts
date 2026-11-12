// 브라우저 → (같은 출처) /api/* → API 서버로 전달하는 런타임 프록시.
// API_URL 은 빌드 시점이 아니라 실행 시점에 읽는다(docker compose 에서 http://api:8000).
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API_URL = () => (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${API_URL()}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  for (const name of ["content-type", "cookie", "authorization", "x-webhook-token"]) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "API 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요." }, { status: 502 });
  }
  const out = new Headers();
  for (const name of ["content-type", "content-disposition", "x-content-type-options"]) {
    const v = upstream.headers.get(name);
    if (v) out.set(name, v);
  }
  for (const c of upstream.headers.getSetCookie()) out.append("set-cookie", c);
  out.set("cache-control", "no-store");
  return new Response(upstream.status === 204 ? null : await upstream.arrayBuffer(), { status: upstream.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE };
