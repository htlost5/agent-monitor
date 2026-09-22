import { memo } from "react";
import { Alert } from "@mui/material";

interface Props {
  backendReachable: boolean;
  opencodeReachable: boolean;
}

/**
 * P4 offline banner (memo化):
 * - backend停止 -> 赤バナー + 一覧保持
 * - opencode停止 -> 黄バナー + 一覧保持
 * - 両方reachable -> null (復帰後5〜10秒でlive復帰は既存5秒pollが担う)
 */
function OfflineBanner({ backendReachable, opencodeReachable }: Props) {
  if (!backendReachable) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        backend (4100) に接続できません。`uvicorn app.main:app --port
        4100` が起動しているか確認してください。一覧は保持されます。
      </Alert>
    );
  }
  if (!opencodeReachable) {
    return (
      <Alert severity="warning" sx={{ mb: 2 }}>
        opencode (4096) に接続できません。起動後に5〜10秒でlive復帰します。一覧は保持されます。
      </Alert>
    );
  }
  return null;
}

export default memo(OfflineBanner);
