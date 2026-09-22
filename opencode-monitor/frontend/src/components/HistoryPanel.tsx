import { useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { fetchHistory, type TransitionItem } from "../api";
import { formatDateTime } from "../lib";

interface Props {
  transitions: TransitionItem[];
  title?: string;
  defaultExpanded?: boolean;
}

function kindColor(kind: string): "success" | "info" | "primary" | "error" | "default" {
  if (kind === "finished") return "success";
  if (kind === "created") return "info";
  if (kind === "updated") return "primary";
  if (kind === "anomaly") return "error";
  return "default";
}

function kindLabel(kind: string): string {
  if (kind === "finished") return "完了の可能性";
  if (kind === "created") return "新規";
  if (kind === "updated") return "更新";
  if (kind === "anomaly") return "異常";
  return kind;
}

const KIND_OPTIONS = ["", "created", "updated", "finished", "anomaly"] as const;

export default function HistoryPanel({ transitions, title, defaultExpanded = false }: Props) {
  const [sessionQuery, setSessionQuery] = useState("");
  const [kindQuery, setKindQuery] = useState<string>("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<TransitionItem[] | null>(null);

  const searching_active = searchResults !== null;
  const items = (searching_active ? (searchResults ?? []) : transitions).slice(0, 30);

  const handleSearch = async () => {
    setSearching(true);
    setSearchError(null);
    try {
      // GET /api/history を使用 (session_id/kind 任意)
      const sid = sessionQuery.trim() ? sessionQuery.trim() : undefined;
      const kind = kindQuery ? kindQuery : undefined;
      const res = await fetchHistory(sid, 100, kind);
      setSearchResults(res);
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : String(e));
    } finally {
      setSearching(false);
    }
  };

  const handleClear = () => {
    setSessionQuery("");
    setKindQuery("");
    setSearchResults(null);
    setSearchError(null);
  };

  return (
    <Box sx={{ mt: 3 }}>
      <Accordion defaultExpanded={defaultExpanded}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            {title ?? `遷移履歴 (${searching_active ? searchResults?.length ?? 0 : transitions.length})`}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 2, alignItems: "center" }}>
            <TextField
              size="small"
              label="session_id で検索"
              placeholder="session_id"
              value={sessionQuery}
              onChange={(e) => setSessionQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSearch();
              }}
              sx={{ minWidth: 220 }}
            />
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id="history-kind-label">kind</InputLabel>
              <Select
                labelId="history-kind-label"
                label="kind"
                value={kindQuery}
                onChange={(e) => setKindQuery(e.target.value)}
              >
                <MenuItem value="">すべて</MenuItem>
                {KIND_OPTIONS.filter((k) => k !== "").map((k) => (
                  <MenuItem key={k} value={k}>
                    {k === "finished" ? "finished (完了の可能性)" : k}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button
              size="small"
              variant="contained"
              disabled={searching}
              onClick={() => void handleSearch()}
            >
              {searching ? "検索中…" : "検索"}
            </Button>
            {searching_active && (
              <Button size="small" variant="outlined" onClick={handleClear}>
                クリア
              </Button>
            )}
          </Box>
          {searchError && (
            <Alert severity="warning" sx={{ mb: 1 }}>
              {searchError}
            </Alert>
          )}
          {searching_active && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              検索結果 ({searchResults?.length ?? 0} 件 / GET /api/history)
            </Typography>
          )}
          {items.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              遷移はまだありません。sync後に新規・更新・完了の可能性・異常がここに記録されます。
            </Typography>
          ) : (
            <Box sx={{ display: "grid", gap: 1 }}>
              {items.map((t) => (
                <Box
                  key={t.id}
                  sx={{
                    display: "flex",
                    gap: 1,
                    alignItems: "center",
                    flexWrap: "wrap",
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    pb: 1,
                  }}
                >
                  <Chip size="small" color={kindColor(t.kind)} label={kindLabel(t.kind)} />
                  <Typography variant="body2" sx={{ fontFamily: "monospace" }} noWrap>
                    {t.session_id.slice(0, 12)}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatDateTime(t.detected_at)}
                  </Typography>
                  {t.detail && (
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {t.detail}
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}
