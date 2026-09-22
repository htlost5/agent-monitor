# TASK-2: oc-monitor 表示再設計 + 同期高速化

## 目的
- 表示: 件数・種類のフィルタ、項目・配置の再評価。過去履歴より現在のエージェント稼働状況を最優先に確認できる画面にする。
- 性能: 同期が長い原因を分析し、ロジック再構築でブラッシュアップする。

## 制約
- Backend: Python+FastAPI+SSE+SQLite / Frontend: React+Vite+MUI / データ源: opencode server APIのみ
- opencode 1.18.x固定。Windows動作必須
- コミット・プッシュはユーザー明示指示までしない

## 現状把握 (Hermes実測 2026-09-22)
- backend/app: config/store/opencode_client/detect/main/spec_check (計約1100行)。frontend/src: App/useSessions/api/lib + components(Detail/History/Offline/SessionGrid) + hooks×3 (計約900行)。
- 表示: SessionGridが全件(200件上限)フラット表示、フィルタなし。HistoryPanelが常時下部。稼働中/Idle/完了の視覚優先度なし。
- 同期: frontendが5秒毎にPOST /api/sync→毎回フル取得。backendは legacy GET /session のoffsetループ+probe + webui /api/session カーソル走査(各最大20ページ)の二重取得後に和集合。150件で実測数秒〜十数秒。
- 性能 suspect: (1) `_get`が毎回httpx.Client生成でkeep-aliveなし (2) 二重取得の重複走査 (3) 全件upsert(raw全文JSON付)毎回 (4) finished重複排除で件数分のlist_history都度クエリ (5) 5秒自動syncと相乗で常時高負荷。sessions.updated_at等にindexなし。

## フェーズと受け入れ条件
- [x] plan: opencode plan案→Hermesが設計化 (design-t2.md確定。plan §7の5点は全てHermes決定済み)
- [x] implement(build): 表示再設計 + 同期高速化を実装 (自己検証: tsc/vite通過、sync 15秒→約2.1秒、冪等OK)
- [x] implement-r2: レビュー指摘5件修正 (中-1 filterNow15秒バケット、中-3 with化、低-4/5/6。tsc/py_compile通過)
- [x] review(general): 条件付き承認 (指摘: 中3・低5。性能主張は機構上plausible、再現はtestへ申送り)
- [x] test(general): 条件付き合格→Hermes実機確認で承認に格上げ (稼働中先頭・フィルタ122/155変動・リセット復帰・履歴既定閉を実機操作で確認。目視で配色・件数・カード項目OK、中-1の体感問題なし)
- 受入(表示): 稼働中セクション最上位、フィルタ(プロジェクト/状態/エージェント種別)+件数表示、履歴は縮小・二の次
- 受入(性能): 同期時間の改善を計測値で示す(現状ベースライン→改善後)。5秒自動sync継続でも負荷低減
- 受入(回帰): P1/P4 verify相当(冪等・オフライン時の一覧保持・build通過)

## 実行ログ
- 2026-09-22: TASK-2作成。Hermesが現状把握(全ファイル読込は最小限・要点のみ)。

## Problems (status: open/resolved)
- resolved: syncベースライン計測済み (2026-09-22): POST /api/sync 3回とも15秒。5秒自動sync間隔より長く、常時重複skip/キュー状態のはず。改善目標は5秒未満。
- open: フィルタ既定値・レイアウト詳細はplan案を見てHermesが決定する

## Knowledge
- なし
