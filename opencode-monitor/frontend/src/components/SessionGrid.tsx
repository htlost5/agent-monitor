import { memo, useState } from "react";
import { Badge, Box, Button, Card, CardActionArea, CardContent, Chip, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import type { ProjectItem, SessionItem, TransitionItem } from "../api";
import { formatElapsed, getSessionAgent, getSessionModel, parseRaw } from "../lib";
import type { SessionGroups } from "../hooks/useSessionFilter";

interface Props {
  groups: SessionGroups;
  projectMap: Map<string, ProjectItem>;
  now: number;
  selectedId: string | null;
  onSelect: (s: SessionItem) => void;
  latestBySession?: Map<string, TransitionItem>;
}

const PAGE_SIZE = 50;

function transitionChip(t: TransitionItem | undefined) {
  if (!t) return null;
  if (t.kind === "finished")
    return <Chip size="small" color="success" label="完了の可能性" title={t.detected_at} />;
  if (t.kind === "created")
    return (
      <Chip size="small" color="info" label="新規" variant="outlined" title={t.detected_at} />
    );
  if (t.kind === "updated")
    return (
      <Chip
        size="small"
        color="primary"
        label="更新"
        variant="outlined"
        title={t.detected_at}
      />
    );
  if (t.kind === "anomaly")
    return <Chip size="small" color="error" label="異常" title={t.detail ?? t.detected_at} />;
  return null;
}

function projectLabel(p: ProjectItem | undefined, projectId: string | null): string {
  if (p?.name) return p.name;
  if (p?.path) {
    const parts = p.path.split(/[/\\]/).filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : p.path;
  }
  if (projectId) return projectId.slice(0, 8);
  return "-";
}

function SessionCard({
  s,
  projectMap,
  now,
  selected,
  onSelect,
  latestBySession,
}: {
  s: SessionItem;
  projectMap: Map<string, ProjectItem>;
  now: number;
  selected: boolean;
  onSelect: (s: SessionItem) => void;
  latestBySession?: Map<string, TransitionItem>;
}) {
  const raw = parseRaw(s.raw);
  const model = getSessionModel(raw);
  const agent = getSessionAgent(raw);
  const project = s.project_id ? projectMap.get(s.project_id) : undefined;
  return (
    <Grid key={s.id} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
      <Card
        variant={selected ? "elevation" : "outlined"}
        sx={selected ? { borderColor: "primary.main", borderWidth: 2 } : undefined}
      >
        <CardActionArea onClick={() => onSelect(s)}>
          <CardContent>
            <Typography variant="subtitle1" noWrap title={s.title ?? s.id}>
              {s.title || s.id.slice(0, 12)}
            </Typography>
            <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
              <Chip size="small" label={projectLabel(project, s.project_id)} />
              {agent && <Chip size="small" color="secondary" variant="outlined" label={agent} />}
              {model && !agent && (
                <Chip size="small" color="primary" variant="outlined" label={model} />
              )}
              {transitionChip(latestBySession?.get(s.id))}
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              経過: {formatElapsed(s.updated_at, now)}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap title={s.id}>
              {s.id.slice(0, 12)}
            </Typography>
          </CardContent>
        </CardActionArea>
      </Card>
    </Grid>
  );
}

function Section({
  title,
  items,
  headerSx,
  badgeCount,
  badgeColor = "success",
  projectMap,
  now,
  selectedId,
  onSelect,
  latestBySession,
  paginate = false,
}: {
  title: string;
  items: SessionItem[];
  headerSx?: Record<string, unknown>;
  badgeCount?: number;
  badgeColor?: "default" | "primary" | "secondary" | "success" | "error" | "info" | "warning";
  projectMap: Map<string, ProjectItem>;
  now: number;
  selectedId: string | null;
  onSelect: (s: SessionItem) => void;
  latestBySession?: Map<string, TransitionItem>;
  paginate?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (items.length === 0) return null;
  const visible = paginate && !expanded ? items.slice(0, PAGE_SIZE) : items;
  return (
    <Box sx={{ mb: 3 }}>
      {badgeCount !== undefined ? (
        <Badge badgeContent={badgeCount} color={badgeColor} sx={{ mr: 2, mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, ...headerSx }}>
            {title}
          </Typography>
        </Badge>
      ) : (
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1, ...headerSx }}>
          {title} ({items.length})
        </Typography>
      )}
      <Grid container spacing={2}>
        {visible.map((s) => (
          <SessionCard
            key={s.id}
            s={s}
            projectMap={projectMap}
            now={now}
            selected={selectedId === s.id}
            onSelect={onSelect}
            latestBySession={latestBySession}
          />
        ))}
      </Grid>
      {paginate && !expanded && items.length > PAGE_SIZE && (
        <Button size="small" variant="outlined" sx={{ mt: 1 }} onClick={() => setExpanded(true)}>
          もっと見る (残り{items.length - PAGE_SIZE}件)
        </Button>
      )}
    </Box>
  );
}

export default memo(function SessionGrid({
  groups,
  projectMap,
  now,
  selectedId,
  onSelect,
  latestBySession,
}: Props) {
  const total = groups.active.length + groups.idle.length + groups.done.length + groups.unknown.length;
  if (total === 0) {
    return (
      <Typography color="text.secondary" sx={{ p: 2 }}>
        セッションがありません。opencode で run を開始すると5〜10秒でここに表示されます。
      </Typography>
    );
  }
  return (
    <Box>
      <Section
        title="稼働中"
        items={groups.active}
        headerSx={{ color: "success.main" }}
        badgeCount={groups.active.length}
        badgeColor="success"
        projectMap={projectMap}
        now={now}
        selectedId={selectedId}
        onSelect={onSelect}
        latestBySession={latestBySession}
      />
      <Section
        title="Idle"
        items={groups.idle}
        headerSx={{ color: "text.secondary" }}
        projectMap={projectMap}
        now={now}
        selectedId={selectedId}
        onSelect={onSelect}
        latestBySession={latestBySession}
        paginate={groups.idle.length > PAGE_SIZE}
      />
      <Section
        title="完了の可能性"
        items={groups.done}
        headerSx={{ color: "text.secondary" }}
        projectMap={projectMap}
        now={now}
        selectedId={selectedId}
        onSelect={onSelect}
        latestBySession={latestBySession}
        paginate={groups.done.length > PAGE_SIZE}
      />
      <Section
        title="その他"
        items={groups.unknown}
        headerSx={{ color: "text.secondary" }}
        projectMap={projectMap}
        now={now}
        selectedId={selectedId}
        onSelect={onSelect}
        latestBySession={latestBySession}
        paginate
      />
    </Box>
  );
});
