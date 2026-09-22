/** Backend API client (P2). All paths go through vite proxy /api -> 4100. */

export interface SessionItem {
  id: string;
  project_id: string | null;
  title: string | null;
  updated_at: string | null;
  raw: string | Record<string, unknown> | null;
  synced_at: string | null;
}

export interface ProjectItem {
  id: string;
  name: string | null;
  path: string | null;
  raw: string | Record<string, unknown> | null;
  updated_at: string | null;
}

export interface HealthResponse {
  status: string;
  db: string;
  opencode: {
    reachable: boolean;
    health?: unknown;
    error?: string;
  };
}

export interface SyncResponse {
  projects: number;
  sessions: number;
  synced: boolean;
  warnings?: string[];
  transitions?: TransitionItem[];
  duration_ms?: number;
  fetched?: { projects: number; sessions: number };
  upserted?: { projects: number; sessions: number };
  marker?: { checked: number; hit: number; skipped: number };
}

async function parseJsonSafe(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function toErrorMessage(status: number, payload: unknown): string {
  if (payload && typeof payload === "object") {
    const d = payload as Record<string, unknown>;
    const detail = d["detail"];
    if (typeof detail === "string") return `HTTP ${status}: ${detail}`;
    if (detail && typeof detail === "object") {
      try {
        return `HTTP ${status}: ${JSON.stringify(detail)}`;
      } catch {
        /* fallthrough */
      }
    }
    try {
      const s = JSON.stringify(payload);
      if (s && s !== "{}") return `HTTP ${status}: ${s}`;
    } catch {
      /* ignore */
    }
  }
  if (typeof payload === "string" && payload) return `HTTP ${status}: ${payload}`;
  return `HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const payload = await parseJsonSafe(res);
  if (!res.ok) throw new Error(toErrorMessage(res.status, payload));
  return payload as T;
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", { signal });
}

export function triggerSync(): Promise<SyncResponse> {
  return request<SyncResponse>("/api/sync", { method: "POST" });
}

export async function listSessions(limit = 200): Promise<SessionItem[]> {
  const data = await request<{ sessions: SessionItem[] }>(
    `/api/sessions?limit=${limit}`
  );
  return Array.isArray(data.sessions) ? data.sessions : [];
}

export async function fetchProjects(): Promise<ProjectItem[]> {
  const data = await request<{ projects: ProjectItem[] }>("/api/projects");
  return Array.isArray(data.projects) ? data.projects : [];
}

/** P3: completion transition record. */
export type TransitionKind = "created" | "updated" | "finished" | "anomaly";

export interface TransitionItem {
  id: number;
  session_id: string;
  kind: TransitionKind | string;
  old_updated_at: string | null;
  new_updated_at: string | null;
  detected_at: string;
  detail: string | null;
}

export async function fetchTransitions(limit = 100): Promise<TransitionItem[]> {
  const data = await request<{ transitions: TransitionItem[] }>(
    `/api/transitions?limit=${limit}`
  );
  return Array.isArray(data.transitions) ? data.transitions : [];
}

export async function fetchHistory(
  sessionId?: string,
  limit = 100,
  kind?: string
): Promise<TransitionItem[]> {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  if (kind) params.set("kind", kind);
  params.set("limit", String(limit));
  const data = await request<{ transitions: TransitionItem[] }>(
    `/api/history?${params.toString()}`
  );
  return Array.isArray(data.transitions) ? data.transitions : [];
}

/** P4: spec drift check result (always HTTP 200; ok=false on drift/offline). */
export interface SpecCheckResponse {
  ok: boolean;
  reachable: boolean;
  warnings: string[];
  missing?: string[];
  extra?: string[];
  endpoint_count?: number;
  snapshot_endpoints?: number;
  required?: string[];
  snapshot_created?: boolean;
}

export function fetchSpecCheck(signal?: AbortSignal): Promise<SpecCheckResponse> {
  return request<SpecCheckResponse>("/api/spec-check", { signal });
}
