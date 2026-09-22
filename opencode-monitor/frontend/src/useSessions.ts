import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchHealth,
  fetchProjects,
  listSessions,
  triggerSync,
  type ProjectItem,
  type SessionItem,
} from "./api";

export interface SessionsState {
  sessions: SessionItem[];
  projects: ProjectItem[];
  projectMap: Map<string, ProjectItem>;
  loading: boolean;
  syncing: boolean;
  connected: boolean;
  backendReachable: boolean;
  opencodeReachable: boolean;
  lastSync: string | null;
  error: string | null;
  now: number;
  /** フィルタ判定用 (nowを15秒バケット化。1秒tickによるmemo無効化を回避)。 */
  filterNow: number;
  refresh: () => Promise<void>;
  manualSync: () => Promise<void>;
}

/**
 * P5 hook: 初回 sync→list、EventSource主導 + 60秒セーフティネット + 1秒ローカルtick。
 * - 旧5秒インターバルは廃止。backendがopencodeイベント購読で自動syncし、
 *   /api/events の sync 通知でlist/healthを更新する。
 * - 60秒セーフティネット doSync は取りこぼし・スキーマ漂流・停止空白の保険。
 * - isSyncing 重複 skip (syncingRef)
 * - opencode停止時もクラッシュしない (try/catch + reachable flag)
 */
export function useSessions(): SessionsState {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [connected, setConnected] = useState(false);
  const [backendReachable, setBackendReachable] = useState(true);
  const [opencodeReachable, setOpencodeReachable] = useState(false);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState<number>(() => Date.now());

  const syncingRef = useRef(false);
  const mountedRef = useRef(true);
  const listInflightRef = useRef(false); // P4: in-flightガード
  const healthInflightRef = useRef(false); // P4: in-flightガード

  const refreshList = useCallback(async () => {
    if (listInflightRef.current) return; // 重複skip
    listInflightRef.current = true;
    try {
      const [s, p] = await Promise.all([listSessions(200), fetchProjects()]);
      if (!mountedRef.current) return;
      setSessions(s);
      setProjects(p);
      setBackendReachable(true);
      setError(null);
    } catch (e) {
      if (!mountedRef.current) return;
      setBackendReachable(false);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      listInflightRef.current = false;
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    if (healthInflightRef.current) return; // 重複skip
    healthInflightRef.current = true;
    try {
      const h = await fetchHealth();
      if (!mountedRef.current) return;
      setBackendReachable(true);
      setOpencodeReachable(Boolean(h?.opencode?.reachable));
    } catch {
      if (!mountedRef.current) return;
      setBackendReachable(false);
      setOpencodeReachable(false);
    } finally {
      healthInflightRef.current = false;
    }
  }, []);

  const doSync = useCallback(async () => {
    if (syncingRef.current) return; // 重複skip
    syncingRef.current = true;
    if (mountedRef.current) setSyncing(true);
    try {
      const r = await triggerSync();
      if (!mountedRef.current) return;
      setLastSync(new Date().toISOString());
      setBackendReachable(true);
      setOpencodeReachable(true);
      setError(null);
      void r;
      await refreshList();
      await refreshHealth();
    } catch (e) {
      if (!mountedRef.current) return;
      // 503 (opencode停止) でもクラッシュせず一覧は残す
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      await refreshList();
      await refreshHealth();
    } finally {
      syncingRef.current = false;
      if (mountedRef.current) setSyncing(false);
    }
  }, [refreshHealth, refreshList]);

  // 初回: sync → list (+health)。失敗してもlist/healthは試す。
  useEffect(() => {
    mountedRef.current = true;
    (async () => {
      if (mountedRef.current) setLoading(true);
      await doSync();
      if (mountedRef.current) setLoading(false);
    })();
    return () => {
      mountedRef.current = false;
    };
  }, [doSync]);

  // P5: 5秒インターバル廃止。backendのイベント駆動sync + 下のEventSourceが主経路。
  // 60秒セーフティネット doSync は取りこぼしの保険。doSync側のsyncingRefガードで重複skip。
  // opencode停止時も一覧保持。
  useEffect(() => {
    const id = window.setInterval(() => {
      void doSync();
    }, 60000);
    return () => window.clearInterval(id);
  }, [doSync]);

  // EventSource: /api/events の sync 通知でlist更新
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource("/api/events");
      es.onopen = () => {
        if (mountedRef.current) setConnected(true);
      };
      es.onerror = () => {
        if (mountedRef.current) setConnected(false);
      };
      es.addEventListener("sync", () => {
        if (syncingRef.current) return;
        void refreshList();
        void refreshHealth();
      });
    } catch {
      if (mountedRef.current) setConnected(false);
    }
    return () => {
      try {
        es?.close();
      } catch {
        /* ignore */
      }
      if (mountedRef.current) setConnected(false);
    };
  }, [refreshHealth, refreshList]);

  // P5: タブ復帰時は backend がイベント駆動で既にsync済みの想定なので
  // list/health の軽量refreshのみ (重い doSync は60秒セーフティネットに任せる)。
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && mountedRef.current) {
        void refreshList();
        void refreshHealth();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refreshHealth, refreshList]);

  // 1秒ローカルtick (経過時間表示用)
  useEffect(() => {
    const id = window.setInterval(() => {
      if (mountedRef.current) setNow(Date.now());
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  const projectMap = useMemo(() => {
    const m = new Map<string, ProjectItem>();
    for (const p of projects) m.set(p.id, p);
    return m;
  }, [projects]);

  // [中-1] フィルタ用時刻は15秒バケット化: now(1秒更新)は経過表示専用にし、
  // useSessionFilterのmemoが毎秒無効化されないようにする。
  const filterNow = useMemo(() => Math.floor(now / 15000) * 15000, [now]);

  return {
    sessions,
    projects,
    projectMap,
    loading,
    syncing,
    connected,
    backendReachable,
    opencodeReachable,
    lastSync,
    error,
    now,
    filterNow,
    refresh: refreshList,
    manualSync: doSync,
  };
}
