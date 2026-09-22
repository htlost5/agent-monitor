import { useCallback, useState } from "react";

export type BrowserNotifyPermission = NotificationPermission | "unsupported";

function initialPermission(): BrowserNotifyPermission {
  try {
    if (typeof Notification === "undefined") return "unsupported";
    return Notification.permission;
  } catch {
    return "unsupported";
  }
}

/**
 * Browser Notification API wrapper.
 * - permission state for Chip display
 * - request(): permission request (must be called from user gesture)
 * - notify(): granted時のみNotification発行、deny/default/unsupported時はfalseを返し
 *   呼び出し側がアプリ内Alertにフォールバックする
 */
export function useBrowserNotification() {
  const [permission, setPermission] = useState<BrowserNotifyPermission>(() =>
    initialPermission()
  );

  const request = useCallback(async (): Promise<BrowserNotifyPermission> => {
    try {
      if (typeof Notification === "undefined") {
        setPermission("unsupported");
        return "unsupported";
      }
      const p = await Notification.requestPermission();
      setPermission(p);
      return p;
    } catch {
      return permission;
    }
  }, [permission]);

  const notify = useCallback(
    (title: string, body?: string): boolean => {
      try {
        if (typeof Notification === "undefined") return false;
        if (Notification.permission !== "granted") return false;
        const n = new Notification(title, body ? { body } : undefined);
        // auto-close after 8s to avoid lingering
        window.setTimeout(() => {
          try {
            n.close();
          } catch {
            /* ignore */
          }
        }, 8000);
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  return { permission, request, notify };
}
