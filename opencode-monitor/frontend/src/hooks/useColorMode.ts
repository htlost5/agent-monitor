import { useCallback, useState } from "react";

export type ColorMode = "light" | "dark";

export const COLOR_MODE_STORAGE_KEY = "oc-monitor:theme";

function getInitialMode(): ColorMode {
  try {
    const saved = localStorage.getItem(COLOR_MODE_STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return "dark";
  } catch {
    return "dark";
  }
}

export function useColorMode() {
  const [mode, setMode] = useState<ColorMode>(getInitialMode);

  const toggle = useCallback(() => {
    setMode((prev) => {
      const next: ColorMode = prev === "light" ? "dark" : "light";
      try {
        localStorage.setItem(COLOR_MODE_STORAGE_KEY, next);
      } catch {
        // localStorage利用不可時はメモリ上の切替のみ維持
      }
      return next;
    });
  }, []);

  return { mode, toggle };
}
