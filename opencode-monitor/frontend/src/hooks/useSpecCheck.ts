import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSpecCheck, type SpecCheckResponse } from "../api";

export interface SpecCheckState {
  spec: SpecCheckResponse | null;
  ok: boolean;
  reachable: boolean;
  warnings: string[];
  missing: string[];
  refresh: () => Promise<void>;
}

/**
 * P4 hook: poll GET /api/spec-check + keep previous on backend-offline.
 * - in-flight guard (inflightRef) で重複fetchをskip
 * - backend停止時は前回値を保持しクラッシュしない
 */
export function useSpecCheck(pollMs = 30000): SpecCheckState {
  const [spec, setSpec] = useState<SpecCheckResponse | null>(null);
  const mountedRef = useRef(true);
  const inflightRef = useRef(false); // in-flight guard

  const refresh = useCallback(async () => {
    if (inflightRef.current) return; // 重複skip
    inflightRef.current = true;
    try {
      const res = await fetchSpecCheck();
      if (!mountedRef.current) return;
      setSpec(res);
    } catch {
      /* keep previous spec on backend-offline */
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

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return {
    spec,
    ok: spec?.ok ?? true,
    reachable: spec?.reachable ?? true,
    warnings: spec?.warnings ?? [],
    missing: spec?.missing ?? [],
    refresh,
  };
}
