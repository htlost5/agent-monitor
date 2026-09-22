import {
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
import type { ProjectItem } from "../api";
import type { StatusFilter } from "../hooks/useSessionFilter";

interface Props {
  projects: ProjectItem[];
  project: string;
  onProjectChange: (v: string) => void;
  status: StatusFilter;
  onStatusChange: (v: StatusFilter) => void;
  agentOptions: string[];
  agent: string;
  onAgentChange: (v: string) => void;
  query: string;
  onQueryChange: (v: string) => void;
  counts: { total: number; filtered: number; active: number; idle: number; done: number };
  onReset: () => void;
}

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部表示" },
  { value: "active", label: "稼働中" },
  { value: "idle", label: "Idle" },
  { value: "done", label: "完了の可能性" },
  { value: "unknown", label: "不明" },
];

export default function FilterBar({
  projects,
  project,
  onProjectChange,
  status,
  onStatusChange,
  agentOptions,
  agent,
  onAgentChange,
  query,
  onQueryChange,
  counts,
  onReset,
}: Props) {
  return (
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center", mb: 2 }}>
      <FormControl size="small" sx={{ minWidth: 180 }}>
        <InputLabel id="filter-project-label">プロジェクト</InputLabel>
        <Select
          labelId="filter-project-label"
          label="プロジェクト"
          value={project}
          onChange={(e) => onProjectChange(e.target.value)}
        >
          <MenuItem value="">すべて</MenuItem>
          {projects.map((p) => (
            <MenuItem key={p.id} value={p.id}>
              {p.name ?? p.path ?? p.id.slice(0, 8)}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <FormControl size="small" sx={{ minWidth: 140 }}>
        <InputLabel id="filter-agent-label">エージェント</InputLabel>
        <Select
          labelId="filter-agent-label"
          label="エージェント"
          value={agent}
          onChange={(e) => onAgentChange(e.target.value)}
        >
          <MenuItem value="">すべて</MenuItem>
          {agentOptions.map((a) => (
            <MenuItem key={a} value={a}>
              {a}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
        {STATUS_OPTIONS.map((o) => (
          <Chip
            key={o.value}
            size="small"
            label={o.label}
            color={status === o.value ? "primary" : "default"}
            variant={status === o.value ? "filled" : "outlined"}
            onClick={() => onStatusChange(o.value)}
            clickable
          />
        ))}
      </Box>
      <TextField
        size="small"
        label="検索 (title/id)"
        placeholder="検索"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        sx={{ minWidth: 180 }}
      />
      <Typography variant="body2" color="text.secondary">
        {counts.filtered}/{counts.total} (稼働中{counts.active}・Idle{counts.idle}・完了{counts.done})
      </Typography>
      <Button size="small" variant="outlined" onClick={onReset}>
        リセット
      </Button>
    </Box>
  );
}
