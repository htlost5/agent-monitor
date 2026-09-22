import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchTransitions, type TransitionItem } from "../api";

export interface TransitionNotifyState {
  transitions: TransitionItem[];
  latestBySession: Map<string, TransitionItem>;
  lastFinished: TransitionItem | null;
  refresh: () => Promise<void>;
}

/**
 * P3 hook: SSE主導で /api/transitions 更新 + 60秒セーフティネットpoll。
 * App connects this hook and passes latestBySession to SessionGrid.
 * (P5: 旧5秒pollは廃止。SSE merge が主経路、poll は保険。)
 */
export function useTransitionNotify(pollMs = 60000): TransitionNotifyState {
  const [transitions, setTransitions] = useState<TransitionItem[]>([]);
  const mountedRef = useRef(true);
  const inflightRef = useRef(false); // P4: in-flightガード

  const refresh = useCallback(async () => {
    if (inflightRef.current) return; // 重複skip
    inflightRef.current = true;
    try {
      const items = await fetchTransitions(100);
      if (!mountedRef.current) return;
      setTransitions(items);
    } catch {
      /* keep previous list on backend-offline */
    } finally {
      inflightRef.current = false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    const id = window.setInterval(() => {
      void refresh();
    }, pollMs);
    return () => {
      window.clearInterval(id);
    };
  }, [refresh, pollMs]);

  // SSE merge: /api/events sync payload may carry `transitions`
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource("/api/events");
      es.addEventListener("sync", (ev) => {
        try {
          const payload = JSON.parse((ev as MessageEvent).data) as {
            transitions?: TransitionItem[];
          };
          const incoming = Array.isArray(payload.transitions)
            ? payload.transitions
            : [];
          if (incoming.length > 0 && mountedRef.current) {
            setTransitions((prev) => {
              const seen = new Set(prev.map((t) => t.id));
              const fresh = incoming.filter((t) => !seen.has(t.id));
              return [...fresh, ...prev].slice(0, 200);
            });
          } else {
            void refresh();
          }
        } catch {
          void refresh();
        }
      });
    } catch {
      /* EventSource unavailable: polling covers updates */
    }
    return () => {
      try {
        es?.close();
      } catch {
        /* ignore */
      }
    };
  }, [refresh]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // transitions are id-DESC; iterate oldest-first so newest wins per session
  const latestBySession = useMemo(() => {
    const m = new Map<string, TransitionItem>();
    for (const t of [...transitions].reverse()) {
      m.set(t.session_id, t);
    }
    return m;
  }, [transitions]);
  const lastFinished = useMemo(
    () =>
      transitions.find(
        (t) => t.kind === "finished" && typeof t.detail === "string" && t.detail.includes("marker:")
      ) ??
      transitions.find((t) => t.kind === "finished") ??
      null,
    [transitions]
  );

  return { transitions, latestBySession, lastFinished, refresh };
}
