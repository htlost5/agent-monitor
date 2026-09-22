# TASK-1 P3 設計 (Hermes確定)

## 成果物
Backend:
- store.py: transitions DDL + insert/list/search追加のみ
- detect.py 新規 (純関数約80行。新規・更新・終了・異常の遷移検出)
- main.py: api_syncに旧snapshot→diff→記録→SSE拡張、GET /api/transitions・GET /api/history追加。既存5エンドポイント不変
- scripts/verify_p3.py 新規
Frontend:
- api.ts: TransitionItem/HistoryParams + 2 fetch追加
- SessionGrid.tsx: transitions prop→Chip表示
- HistoryPanel.tsx 新規 (検索UI)
- hooks/useTransitionNotify.ts 新規 (Notification API)
- App.tsx: HistoryPanel組込+hook接続
- DetailPanel.tsx: 遷移履歴セクション追加

## 完了定義
- FINISH_IDLE_SEC: 本番180秒。検証時のみ30秒に一時変更可 (検証後180秒に戻すこと)
- 終了は初回1回のみ通知。再更新が来たら復活表示
- 時刻比較はepochで比較 (ISO文字列比較禁止)

## 受入条件
- run終了時にブラウザNotification + 完了バッジ(緑)
- 履歴検索ヒット。/api/sessions形状はP2と同一

## 禁止
- git commit/push。Discord通知 (対象外)。既存API破壊。
