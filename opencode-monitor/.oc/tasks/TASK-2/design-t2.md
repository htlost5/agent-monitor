# TASK-2 正式設計 (Hermes確定・plan案の修正改良版)

## 決定事項 (plan §7への回答)
1. 稼働中定義: 180秒 (`FINISH_IDLE_SEC`と一致)。`latestBySession=anomaly`はactive側に残す。
2. フィルタ既定: 全部表示 + 稼働中セクション最上位 (稼働中のみ絞りは既定にしない)。
3. 履歴: 既定閉Accordion、下部配置、検索機能は維持。
4. `synced_at`: 不変行は更新しない (書き込み削減を優先)。Detailの「同期:」表示は最終sync時刻(グローバル)を参照する形に変更可。sync応答への`duration_ms, fetched, upserted`追加フィールドは承認 (既存フィールド不変)。
5. `max_pages`既定8、frontend `listSessions(200)`上限は据置。

## Backend実装仕様
- `opencode_client.py`: `list_sessions`をwebui `/api/session`正系統に再構築。legacy `GET /session`はwebuiが0件/例外時のみfallback。probe・limitエスカレーション削除。`httpx.Client`はsync1回で1個を使い回し (Client注入: `OpenCodeClient(base, client=None)`で外部Client受付、なければ内部生成)。
- `main.py api_sync`: 旧`old_map`比較でchanged行のみ`upsert_session`/`upsert_project` (`json.dumps`もchangedのみ)。finished重複排除は`store.get_last_finished_map()`一括取得+メモリ判定に変更。`count_projects/count_sessions`のCOUNT×2は`len()`代替。計測フィールド追加。`detect.py`不変。
- `store.py`: index追加 (`idx_sessions_updated`, `idx_sessions_project`) + `get_last_finished_map()`追加のみ。既存シグネチャ不変。
- `config.py`: `SYNC_MAX_PAGES`(既定8)、`SYNC_TIMEOUT`のenv化は任意 (build判断で省略可)。
- 受け入れ: 同条件3回計測でベースライン15秒→5秒未満。2回連続syncで件数・transitions重複なし (冪等)。

## Frontend実装仕様
- `lib.ts`: `getSessionAgent(raw)` + `getSessionStatus(updated_at, nowMs, transition?)` (active/idle/done/unknown) 追加。
- `hooks/useSessionFilter.ts` (新規): project/status/agent/query + useMemo派生 (active/idle/doneグループ+counts)。
- `components/FilterBar.tsx` (新規): プロジェクトSelect + 状態Chip + エージェントSelect + 検索 + 件数`N/M` + リセット。
- `components/SessionGrid.tsx`: セクション分割 (稼働中全件常時展開・色付きヘッダ+Badge / Idle・完了の可能性は二の次配色 / その他は初期50件+もっと見る)。カードからtoken・cost・生ID全文・synced_atを外しDetailのみに。
- `components/HistoryPanel.tsx`: Accordion化 (既定閉)。
- `App.tsx`: FilterBar組込・セクション配置・件数表示。sync周期・SSEは不変。
- 受け入れ: active先頭表示の目視、フィルタ操作で件数変動・リセット復帰、履歴既定閉、`tsc --noEmit`+`vite build`通過。

## 非スコープ (plan踏襲)
detect.py/spec_check.py変更なし、閾値180s変更なし、SSE→WS化なし、DBマイグレーションなし、無限スクロールなし、opencodeバージョン上げなし、コミット・プッシュなし。

## 検証 (build自己検証→general test)
- backend: `verify_p1.py`相当の冪等確認 + sync3回計測 (自動sync停止状態、ベースラインと同一条件)。
- frontend: `tsc --noEmit` + `vite build` + 実機200確認 + フィルタ操作試験。
