import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  CssBaseline,
  IconButton,
  ThemeProvider,
  Toolbar,
  Typography,
  createTheme,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import SyncIcon from "@mui/icons-material/Sync";
import NotificationsIcon from "@mui/icons-material/Notifications";
import Brightness4Icon from "@mui/icons-material/Brightness4";
import Brightness7Icon from "@mui/icons-material/Brightness7";
import { useSessions } from "./useSessions";
import type { SessionItem } from "./api";
import { formatDateTime } from "./lib";
import SessionGrid from "./components/SessionGrid";
import DetailPanel from "./components/DetailPanel";
import HistoryPanel from "./components/HistoryPanel";
import OfflineBanner from "./components/OfflineBanner";
import FilterBar from "./components/FilterBar";
import { useSessionFilter } from "./hooks/useSessionFilter";
import { useTransitionNotify } from "./hooks/useTransitionNotify";
import { useSpecCheck } from "./hooks/useSpecCheck";
import { useBrowserNotification } from "./hooks/useBrowserNotification";
import { useColorMode } from "./hooks/useColorMode";

// P4レビュー: spec警告が大量時(10件超)は先頭10件+省略件数表示に抑える。
const MAX_SPEC_WARNINGS = 10;

export default function App() {
  const {
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
    refresh,
    manualSync,
  } = useSessions();

  const [selected, setSelected] = useState<SessionItem | null>(null);
  const { mode, toggle } = useColorMode();
  const theme = useMemo(() => createTheme({ palette: { mode } }), [mode]);
  const { transitions, latestBySession, lastFinished } = useTransitionNotify();
  const { warnings: specWarnings, ok: specOk } = useSpecCheck();
  const { permission, request, notify } = useBrowserNotification();
  const notifiedIdRef = useRef<number | null>(null);
  const filter = useSessionFilter(sessions, filterNow, latestBySession);

  const connLabel = !backendReachable
    ? "backend offline"
    : !opencodeReachable
      ? "opencode offline"
      : connected
        ? "live (SSE)"
        : "standby";
  const connColor = !backendReachable ? "error" : !opencodeReachable ? "warning" : "success";

  const notifyLabel =
    permission === "granted"
      ? "通知: ON"
      : permission === "denied"
        ? "通知: OFF (拒否)"
        : permission === "unsupported"
          ? "通知: 未対応"
          : "通知: 未許可";
  const notifyColor =
    permission === "granted" ? "success" : permission === "denied" ? "error" : "default";

  // finished検知 -> Browser Notification (granted時のみ)。deny/default/unsupported時は
  // 既存のアプリ内Alertにフォールバック (下のAlertが常に表示される)。
  // TASK-3: detailにmarker:を含むfinishedはマーカー確定として文言分岐。
  const isMarkerFinished =
    typeof lastFinished?.detail === "string" && lastFinished.detail.includes("marker:");
  useEffect(() => {
    if (!lastFinished) return;
    if (notifiedIdRef.current === lastFinished.id) return;
    notifiedIdRef.current = lastFinished.id;
    const marker =
      typeof lastFinished.detail === "string" && lastFinished.detail.includes("marker:");
    if (marker) {
      notify(
        "完了を検知 (マーカー確定) (oc-monitor)",
        `${lastFinished.session_id.slice(0, 12)} の完了を検知 (マーカー確定)。`
      );
    } else {
      notify(
        "完了の可能性を検知 (oc-monitor)",
        `${lastFinished.session_id.slice(0, 12)} が180秒以上idle。長考runの誤検知の可能性あり。`
      );
    }
  }, [lastFinished, notify]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ flexGrow: 1 }}>
      <AppBar position="static">
        <Toolbar sx={{ gap: 2 }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            oc-monitor
          </Typography>
          <IconButton
            color="inherit"
            size="small"
            onClick={toggle}
            title={mode === "light" ? "ダークモードに切替" : "ライトモードに切替"}
            aria-label={mode === "light" ? "ダークモードに切替" : "ライトモードに切替"}
          >
            {mode === "light" ? <Brightness4Icon /> : <Brightness7Icon />}
          </IconButton>
          <Chip
            size="small"
            color={connColor as "error" | "warning" | "success"}
            label={connLabel}
            title={error ?? ""}
          />
          <Chip
            size="small"
            color={notifyColor as "success" | "error" | "default"}
            icon={<NotificationsIcon />}
            label={notifyLabel}
            title={
              permission === "granted"
                ? "ブラウザ通知が有効です"
                : permission === "denied"
                  ? "ブラウザ通知が拒否されています。アプリ内Alertでお知らせします"
                  : "クリックでブラウザ通知の権限を要求します"
            }
            onClick={() => {
              if (permission !== "granted") void request();
            }}
            clickable={permission !== "granted"}
          />
          <Typography variant="body2" sx={{ opacity: 0.9 }}>
            最終sync: {lastSync ? formatDateTime(lastSync) : "-"}
          </Typography>
          <Button
            color="inherit"
            variant="outlined"
            size="small"
            startIcon={syncing ? <CircularProgress size={14} color="inherit" /> : <SyncIcon />}
            disabled={syncing || loading}
            onClick={() => void manualSync()}
          >
            {syncing ? "Sync中" : "手動Sync"}
          </Button>
          <Button
            color="inherit"
            size="small"
            startIcon={<RefreshIcon />}
            disabled={loading}
            onClick={() => void refresh()}
          >
            更新
          </Button>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: 3 }}>
        <OfflineBanner backendReachable={backendReachable} opencodeReachable={opencodeReachable} />
        {error && (
          <Alert severity={!backendReachable ? "error" : "warning"} sx={{ mb: 2 }}>
            {error}（opencode停止時も一覧は保持されます）
          </Alert>
        )}
        {!specOk && specWarnings.length > 0 && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            spec差分: {specWarnings.slice(0, MAX_SPEC_WARNINGS).join(" / ")}
            {specWarnings.length > MAX_SPEC_WARNINGS
              ? ` / 他${specWarnings.length - MAX_SPEC_WARNINGS}件省略`
              : ""}
          </Alert>
        )}
        {permission === "denied" && (
          <Alert severity="info" sx={{ mb: 2 }}>
            ブラウザ通知が拒否されているため、アプリ内Alertでお知らせします。
          </Alert>
        )}
        {loading ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 4 }}>
            <CircularProgress size={24} />
            <Typography>初回sync中…</Typography>
          </Box>
        ) : (
          <>
            <FilterBar
              projects={projects}
              project={filter.project}
              onProjectChange={filter.setProject}
              status={filter.status}
              onStatusChange={filter.setStatus}
              agentOptions={filter.agentOptions}
              agent={filter.agent}
              onAgentChange={filter.setAgent}
              query={filter.query}
              onQueryChange={filter.setQuery}
              counts={filter.counts}
              onReset={filter.reset}
            />
            {lastFinished && (
              <Alert severity="success" sx={{ mb: 2 }}>
                {isMarkerFinished ? (
                  <>
                    完了を検知 (マーカー確定): {lastFinished.session_id.slice(0, 12)}（
                    {formatDateTime(lastFinished.detected_at)}）— マーカー確定。
                  </>
                ) : (
                  <>
                    完了の可能性を検知: {lastFinished.session_id.slice(0, 12)}（
                    {formatDateTime(lastFinished.detected_at)}）— 180秒以上idle。
                    長考runの誤検知の可能性あり。
                  </>
                )}
              </Alert>
            )}
            <SessionGrid
              groups={filter.groups}
              projectMap={projectMap}
              now={now}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
              latestBySession={latestBySession}
            />
            <HistoryPanel transitions={transitions} />
          </>
        )}
      </Container>

      <DetailPanel
        session={selected}
        project={selected?.project_id ? projectMap.get(selected.project_id) : undefined}
        now={now}
        open={selected !== null}
        onClose={() => setSelected(null)}
        lastSync={lastSync}
      />
      </Box>
    </ThemeProvider>
  );
}
