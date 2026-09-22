# TASK-3 正式設計 (Hermes確定・plan案採用)

## 決定事項
- plan案をほぼそのまま採用。照合は「assistant text partsの行単位完全一致」(最終行限定への厳格化は誤検知実績が出たら別タスク化)。
- frontend表示分岐 (marker確定 vs 完了の可能性) を実装に含める。
- `verify_marker.py`新規作成。既存verify群・既存フィールドは不変。
- 無効化スイッチ `MARKER_ENABLED=0` を必ず残す (性能回帰時の即時停止用)。

## Backend実装仕様
- `opencode_client.py`: `get_session_messages(session_id, limit=10)`追加 (`_get("/session/{id}/message", {"limit": limit})` + `_coerce_list`)。例外は送出。
- `detect.py` (純粋関数のみ追加、`diff_snapshots`不変): `MARKER`定数、`iter_text_parts(msg)` (形状差異に寛容)、`has_marker(messages)` (行strip後完全一致)、`is_active(updated_epoch, now_epoch, idle_sec)`。
- `config.py`: `MARKER_ENABLED`(1)、`MARKER_STRING`、`MARKER_MSG_LIMIT`(10)、`MARKER_MAX_SESSIONS`(20)、`MARKER_TIMEOUT`(3.0)。
- `main.py api_sync`: 既存diff後に挿入。active候補 (上限20・直近更新順) に同一Clientで順次取得、失敗はwarnings化。hit時はfinished合成 (`detail=marker:{MARKER} (即時確定)`)、epoch±1s重複排除 (`get_last_finished_map` + 今回recorded内)。応答に`marker:{checked,hit,skipped}`追加。
- `store.py` / `spec_check.py`: 変更なし。

## Frontend実装仕様 (最小)
- `useTransitionNotify.ts`: `lastFinished`をマーカー優先 (`find(finished && detail includes marker) ?? find(finished)`)。
- `App.tsx`: Alert/通知文言をdetail分岐 (`marker:`→「完了を検知 (マーカー確定)」、else従来文言)。
- `lib.ts`: 変更なし。

## 検証
- `verify_marker.py` + `verify_p1/p3/p4` 全OK。
- Live test (Hermesが実施): 疑似短時間run新規実行→active検知→marker-finished検知の遅延計測 (目標≦2 sync周期)。対照にマーカーなしrunの180秒フォールバック維持も確認。
- TASK-2受入 (2.1秒sync・表示・回帰) 維持。`MARKER_ENABLED=0`で無効化可。

## 非スコープ
永続カラム追加、SSE新種別、ポーリング周期変更、Hermesスキル改修 (規約化済み)。
