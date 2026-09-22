/** Shared helpers (P2): elapsed formatting + base64url (TextEncoder) + session extractors. */

export const OCODE_WEB_URL =
  (import.meta.env.VITE_OCODE_WEB_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:4096";

/** base64url encode (UTF-8). Uses TextEncoder as required. */
export function base64UrlEncode(input: string): string {
  const bytes = new TextEncoder().encode(input);
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    const sub = bytes.subarray(i, i + CHUNK);
    bin += String.fromCharCode(...sub);
  }
  const b64 = btoa(bin);
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Parse DB `raw` column (stringified JSON or object) without throwing. */
export function parseRaw(
  raw: string | Record<string, unknown> | null | undefined
): Record<string, unknown> {
  if (!raw) return {};
  if (typeof raw === "object") return raw as Record<string, unknown>;
  try {
    const v: unknown = JSON.parse(raw);
    if (v && typeof v === "object" && !Array.isArray(v)) {
      return v as Record<string, unknown>;
    }
    return {};
  } catch {
    return {};
  }
}

function pickDeep(obj: Record<string, unknown>, paths: string[][]): unknown {
  for (const path of paths) {
    let cur: unknown = obj;
    let ok = true;
    for (const k of path) {
      if (cur && typeof cur === "object" && k in (cur as Record<string, unknown>)) {
        cur = (cur as Record<string, unknown>)[k];
      } else {
        ok = false;
        break;
      }
    }
    if (ok && cur !== null && cur !== undefined && cur !== "") return cur;
  }
  return undefined;
}

function asString(v: unknown): string | null {
  if (typeof v === "string" && v !== "") return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return null;
}

/** Model name from various possible raw shapes. */
export function getSessionModel(raw: Record<string, unknown>): string | null {
  const v = pickDeep(raw, [
    ["model", "id"],
    ["model", "modelID"],
    ["model"],
    ["modelID"],
    ["modelId"],
    ["provider", "model"],
    ["share", "model"],
    ["summary", "model"],
    ["time", "model"],
  ]);
  const s = asString(v);
  if (s) return s;
  // nested message-ish shape
  const msg = raw["message"];
  if (msg && typeof msg === "object") {
    const m = pickDeep(msg as Record<string, unknown>, [["model"], ["modelID"]]);
    const ms = asString(m);
    if (ms) return ms;
  }
  return null;
}

export interface TokenUsage {
  input: number | null;
  output: number | null;
  total: number | null;
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) {
    return Number(v);
  }
  return null;
}

/** Token usage from various possible raw shapes. */
export function getSessionTokens(raw: Record<string, unknown>): TokenUsage {
  const direct = pickDeep(raw, [
    ["tokens"],
    ["tokenUsage"],
    ["usage", "tokens"],
    ["summary", "tokens"],
  ]);
  if (typeof direct === "number") {
    const n = asNumber(direct);
    return { input: null, output: null, total: n };
  }
  if (direct && typeof direct === "object") {
    const o = direct as Record<string, unknown>;
    const input = asNumber(o["input"] ?? o["inputTokens"] ?? o["promptTokens"]);
    const output = asNumber(o["output"] ?? o["outputTokens"] ?? o["completionTokens"]);
    const total = asNumber(o["total"] ?? o["totalTokens"]);
    if (input !== null || output !== null || total !== null) {
      return {
        input,
        output,
        total: total ?? (input !== null || output !== null ? (input ?? 0) + (output ?? 0) : null),
      };
    }
  }
  const input = asNumber(
    pickDeep(raw, [["inputTokens"], ["promptTokens"], ["usage", "input"], ["usage", "promptTokens"]])
  );
  const output = asNumber(
    pickDeep(raw, [
      ["outputTokens"],
      ["completionTokens"],
      ["usage", "output"],
      ["usage", "completionTokens"],
    ])
  );
  const total = asNumber(
    pickDeep(raw, [["totalTokens"], ["usage", "total"], ["usage", "totalTokens"]])
  );
  if (input === null && output === null && total === null) {
    return { input: null, output: null, total: null };
  }
  return {
    input,
    output,
    total: total ?? (input !== null || output !== null ? (input ?? 0) + (output ?? 0) : null),
  };
}

/** Cost from various possible raw shapes. */
export function getSessionCost(raw: Record<string, unknown>): number | null {
  const v = pickDeep(raw, [
    ["cost"],
    ["totalCost"],
    ["usage", "cost"],
    ["summary", "cost"],
    ["tokenUsage", "cost"],
  ]);
  return asNumber(v);
}

export function formatTokens(t: TokenUsage): string {
  if (t.total === null && t.input === null && t.output === null) return "-";
  if (t.input !== null || t.output !== null) {
    const i = t.input ?? 0;
    const o = t.output ?? 0;
    const tot = t.total ?? i + o;
    return `${tot.toLocaleString()} (in ${i.toLocaleString()} / out ${o.toLocaleString()})`;
  }
  return (t.total ?? 0).toLocaleString();
}

export function formatCost(cost: number | null): string {
  if (cost === null) return "-";
  if (cost === 0) return "$0";
  if (Math.abs(cost) < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

/** Elapsed time formatting: time since updatedAt until now. */
export function formatElapsed(
  updatedAt: string | null | undefined,
  nowMs: number = Date.now()
): string {
  if (!updatedAt) return "-";
  const t = Date.parse(updatedAt);
  if (Number.isNaN(t)) return "-";
  const diffSec = Math.max(0, Math.floor((nowMs - t) / 1000));
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) {
    const s = diffSec % 60;
    return s === 0 ? `${diffMin}m ago` : `${diffMin}m ${s}s ago`;
  }
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) {
    const m = diffMin % 60;
    return m === 0 ? `${diffHour}h ago` : `${diffHour}h ${m}m ago`;
  }
  const diffDay = Math.floor(diffHour / 24);
  const h = diffHour % 24;
  return h === 0 ? `${diffDay}d ago` : `${diffDay}d ${h}h ago`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  try {
    return new Date(t).toLocaleString();
  } catch {
    return value;
  }
}

/** Base URLがリンク化可能なhttp(s) URLかどうか。 */
export function isHttpBaseUrl(baseUrl: string | null | undefined): boolean {
  return /^https?:\/\/[^/]+/i.test((baseUrl || "").trim());
}

/** Session working directory from various possible raw shapes. */
export function getSessionDirectory(raw: Record<string, unknown>): string | null {
  const v = pickDeep(raw, [["directory"], ["location", "directory"], ["session", "directory"]]);
  return asString(v);
}

/** Direct link to opencode web for a session.
 * opencode webの正規形式は /<base64url(directory)>/session/<id>。
 * 旧形式 /session/<id> はAPIにシャドウされJSONを返すため使わない。
 * directory不明時はwebルートにフォールバック (壊れたリンクを作らない)。 */
export function buildSessionUrl(
  baseUrl: string,
  sessionId: string,
  directory: string | null | undefined
): string {
  const base = (baseUrl || OCODE_WEB_URL).replace(/\/$/, "");
  if (!directory) return `${base}/`;
  return `${base}/${base64UrlEncode(directory)}/session/${encodeSessionIdForUrl(sessionId)}`;
}

/** Session idをURLパスセグメントとして安全に埋め込むためのエンコード。 */
function encodeSessionIdForUrl(sessionId: string): string {
  return encodeURIComponent(sessionId);
}

/** Opaque share key for a session (base64url of session id, TextEncoder-based). */
export function sessionShareKey(sessionId: string): string {
  return base64UrlEncode(sessionId);
}

/** 稼働中判定の閾値 (秒)。backend FINISH_IDLE_SEC=180 と一致させる。 */
export const ACTIVE_IDLE_SEC = 180;

export type SessionStatus = "active" | "idle" | "done" | "unknown";

/** Agent name from various possible raw shapes (webui: agent). */
export function getSessionAgent(raw: Record<string, unknown>): string | null {
  const v = pickDeep(raw, [
    ["agent"],
    ["agentName"],
    ["agent_name"],
    ["session", "agent"],
  ]);
  const s = asString(v);
  if (s) return s;
  const msg = raw["message"];
  if (msg && typeof msg === "object") {
    const m = pickDeep(msg as Record<string, unknown>, [["agent"], ["agentName"]]);
    const ms = asString(m);
    if (ms) return ms;
  }
  return null;
}

interface StatusTransition {
  kind?: string;
}

/** Session status: anomalyはactive側に残す。finishedはdone。 */
export function getSessionStatus(
  updatedAt: string | null | undefined,
  nowMs: number = Date.now(),
  transition?: StatusTransition | null
): SessionStatus {
  const kind = transition?.kind;
  if (kind === "finished") return "done";
  if (kind === "anomaly") return "active";
  if (!updatedAt) return "unknown";
  const t = Date.parse(updatedAt);
  if (Number.isNaN(t)) return "unknown";
  const ageSec = (nowMs - t) / 1000;
  if (ageSec < 0) return "active";
  return ageSec < ACTIVE_IDLE_SEC ? "active" : "idle";
}
