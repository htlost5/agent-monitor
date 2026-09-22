import { useMemo, useState } from "react";
import type { SessionItem, TransitionItem } from "../api";
import { getSessionAgent, getSessionStatus, parseRaw, type SessionStatus } from "../lib";

export type StatusFilter = "all" | SessionStatus;

export interface SessionGroups {
  active: SessionItem[];
  idle: SessionItem[];
  done: SessionItem[];
  unknown: SessionItem[];
}

export interface SessionFilterState {
  project: string;
  setProject: (v: string) => void;
  status: StatusFilter;
  setStatus: (v: StatusFilter) => void;
  agent: string;
  setAgent: (v: string) => void;
  query: string;
  setQuery: (v: string) => void;
  reset: () => void;
  filtered: SessionItem[];
  groups: SessionGroups;
  counts: { total: number; filtered: number; active: number; idle: number; done: number; unknown: number };
  agentOptions: string[];
}

/** Project/status/agent/query フィルタ + active/idle/done グループ派生。 */
export function useSessionFilter(
  sessions: SessionItem[],
  now: number,
  latestBySession?: Map<string, TransitionItem>
): SessionFilterState {
  const [project, setProject] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [agent, setAgent] = useState("");
  const [query, setQuery] = useState("");

  const agentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of sessions) {
      const a = getSessionAgent(parseRaw(s.raw));
      if (a) set.add(a);
    }
    return [...set].sort();
  }, [sessions]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sessions.filter((s) => {
      if (project && (s.project_id ?? "") !== project) return false;
      if (agent) {
        const a = getSessionAgent(parseRaw(s.raw));
        if ((a ?? "") !== agent) return false;
      }
      if (status !== "all") {
        const st = getSessionStatus(s.updated_at, now, latestBySession?.get(s.id));
        if (st !== status) return false;
      }
      if (q) {
        const hay = `${s.title ?? ""} ${s.id}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [sessions, project, agent, status, query, now, latestBySession]);

  const groups = useMemo<SessionGroups>(() => {
    const g: SessionGroups = { active: [], idle: [], done: [], unknown: [] };
    for (const s of filtered) {
      const st = getSessionStatus(s.updated_at, now, latestBySession?.get(s.id));
      g[st].push(s);
    }
    return g;
  }, [filtered, now, latestBySession]);

  const counts = useMemo(
    () => ({
      total: sessions.length,
      filtered: filtered.length,
      active: groups.active.length,
      idle: groups.idle.length,
      done: groups.done.length,
      unknown: groups.unknown.length,
    }),
    [sessions.length, filtered.length, groups]
  );

  const reset = () => {
    setProject("");
    setStatus("all");
    setAgent("");
    setQuery("");
  };

  return {
    project,
    setProject,
    status,
    setStatus,
    agent,
    setAgent,
    query,
    setQuery,
    reset,
    filtered,
    groups,
    counts,
    agentOptions,
  };
}
