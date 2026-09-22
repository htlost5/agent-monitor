import { useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  IconButton,
  Link,
  TextField,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { fetchHistory, type ProjectItem, type SessionItem, type TransitionItem } from "../api";
import {
  OCODE_WEB_URL,
  buildSessionUrl,
  formatCost,
  formatDateTime,
  formatElapsed,
  formatTokens,
  getSessionCost,
  getSessionDirectory,
  getSessionModel,
  getSessionTokens,
  isHttpBaseUrl,
  parseRaw,
  sessionShareKey,
} from "../lib";

interface Props {
  session: SessionItem | null;
  project: ProjectItem | undefined;
  now: number;
  open: boolean;
  onClose: () => void;
  lastSync?: string | null;
}

function kindColor(kind: string): "success" | "info" | "primary" | "error" | "default" {
  if (kind === "finished") return "success";
  if (kind === "created") return "info";
  if (kind === "updated") return "primary";
  if (kind === "anomaly") return "error";
  return "default";
}

export default function DetailPanel({ session, project, now, open, onClose, lastSync }: Props) {
  const [copied, setCopied] = useState<string | null>(null);
  const [history, setHistory] = useState<TransitionItem[]>([]);

  // P3: per-session transition history (session全体ではなくidでdeps狭窄)
  useEffect(() => {
    let cancelled = false;
    if (!open || !session) {
      setHistory([]);
      return;
    }
    const sessionId = session.id;
    void (async () => {
      try {
        const items = await fetchHistory(sessionId, 50);
        if (!cancelled) setHistory(items);
      } catch {
        if (!cancelled) setHistory([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, session?.id]);

  const raw = parseRaw(session?.raw);
  const model = session ? getSessionModel(raw) : null;
  const tokens = session ? getSessionTokens(raw) : { input: null, output: null, total: null };
  const cost = session ? getSessionCost(raw) : null;
  const directUrl = session
    ? buildSessionUrl(
        OCODE_WEB_URL,
        session.id,
        getSessionDirectory(raw) ?? project?.path ?? null
      )
    : "";
  const isDirectUrlLinkable = directUrl !== "" && isHttpBaseUrl(OCODE_WEB_URL);
  const shareKey = session ? sessionShareKey(session.id) : "";

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      // clipboard不可でもクラッシュさせない
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        setCopied(label);
        window.setTimeout(() => setCopied(null), 1500);
      } catch {
        /* ignore */
      }
      document.body.removeChild(ta);
    }
  };

  return (
    <Drawer anchor="right" open={open} onClose={onClose}>
      <Box sx={{ width: 360, p: 2 }} role="presentation">
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="h6">セッション詳細</Typography>
          <IconButton onClick={onClose} aria-label="close">
            <CloseIcon />
          </IconButton>
        </Box>
        <Divider sx={{ my: 1 }} />
        {!session ? (
          <Typography color="text.secondary">カードを選択してください。</Typography>
        ) : (
          <>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {session.title || session.id}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {session.id}
            </Typography>

            <Box sx={{ mt: 2, display: "grid", gap: 1 }}>
              <Typography variant="body2">
                プロジェクト: {project?.name ?? project?.path ?? session.project_id ?? "-"}
              </Typography>
              <Typography variant="body2">モデル: {model ?? "-"}</Typography>
              <Typography variant="body2">
                経過: {formatElapsed(session.updated_at, now)}（更新:{" "}
                {formatDateTime(session.updated_at)}）
              </Typography>
              <Typography variant="body2">トークン: {formatTokens(tokens)}</Typography>
              <Typography variant="body2">コスト: {formatCost(cost)}</Typography>
              <Typography variant="body2">
                同期: {formatDateTime(session.synced_at)}
                {lastSync ? ` (最終sync: ${formatDateTime(lastSync)})` : ""}
              </Typography>
            </Box>

            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2">直接リンク</Typography>
            <TextField
              fullWidth
              size="small"
              value={directUrl}
              InputProps={{ readOnly: true }}
              sx={{ mt: 1 }}
            />
            <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<ContentCopyIcon />}
                onClick={() => void copyText(directUrl, "link")}
              >
                {copied === "link" ? "コピー済み" : "リンクをコピー"}
              </Button>
              {isDirectUrlLinkable ? (
                <Link href={directUrl} target="_blank" rel="noreferrer" sx={{ alignSelf: "center" }}>
                  開く
                </Link>
              ) : (
                <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center" }}>
                  ベースURLがhttp(s)ではないためリンクを開けません
                </Typography>
              )}
            </Box>

            <Typography variant="subtitle2" sx={{ mt: 2 }}>
              共有キー (base64url)
            </Typography>
            <TextField
              fullWidth
              size="small"
              value={shareKey}
              InputProps={{ readOnly: true }}
              sx={{ mt: 1 }}
            />
            <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<ContentCopyIcon />}
                onClick={() => void copyText(shareKey, "key")}
              >
                {copied === "key" ? "コピー済み" : "キーをコピー"}
              </Button>
            </Box>

            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2">遷移履歴 ({history.length})</Typography>
            <Box sx={{ mt: 1, display: "grid", gap: 1 }}>
              {history.length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  履歴はまだありません。
                </Typography>
              ) : (
                history.slice(0, 20).map((t) => (
                  <Box key={t.id} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                    <Chip size="small" color={kindColor(t.kind)} label={t.kind} />
                    <Typography variant="caption" color="text.secondary">
                      {formatDateTime(t.detected_at)}
                    </Typography>
                  </Box>
                ))
              )}
            </Box>
          </>
        )}
      </Box>
    </Drawer>
  );
}
