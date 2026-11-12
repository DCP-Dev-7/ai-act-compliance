"use client";
import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, init?: { method?: string; json?: unknown; body?: string }): Promise<T> {
  const headers: Record<string, string> = {};
  let body: string | undefined = init?.body;
  if (init?.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`/api${path}`, { method: init?.method ?? (body ? "POST" : "GET"), headers, body, credentials: "same-origin" });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : text;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

export function useLoad<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError("");
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? "" : (e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, error, loading, reload };
}

export function fmt(dt?: string | null): string {
  if (!dt) return "-";
  const d = new Date(dt);
  return isNaN(d.getTime()) ? dt : d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

export function fmtDate(dt?: string | null): string {
  if (!dt) return "-";
  const d = new Date(dt);
  return isNaN(d.getTime()) ? dt : d.toLocaleDateString("ko-KR", { dateStyle: "medium" });
}
