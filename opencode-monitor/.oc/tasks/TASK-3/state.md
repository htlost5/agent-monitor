# TASK-3: 完了マーカー規約 + oc-monitor明示完了検知 + リアルタイム検知テスト

## 目的
- Hermes→opencode指令時に完了マーカー出力を義務付け、Hermesが明示的に完了を受け取れるようにする。
- oc-monitorがマーカー検出で完了(finished)と即時判定できるようにする (180秒idle待ちのフォールバックは維持)。
- 稼働中タスクのリアルタイム検知ができているか、疑似タスク実行で実証する。

## 制約
- Backend: Python+FastAPI+SSE+SQLite / Frontend: React+Vite+MUI / データ源: opencode server APIのみ
- マーカー文字列: `__HERMES_TASK_DONE__` (最終行に単独出力)
- 180秒idle検知・文言「完了の可能性」は維持 (マーカー検出は即時finishedの追加経路)
- opencode 1.18.x固定。Windows動作必須。コミット・プッシュはユーザー明示指示までしない

## 技術確認済み (Hermes実測 2026-09-22)
- `GET /session/:id/message?limit=N` で直近メッセージ取得可。assistant text partsに本文あり。マーカー照合が可能。
- 検知ポーリングは稼働中(active)セッションのみ対象に限定し、負荷増を抑える方針。

## フェーズと受け入れ条件
- [x] 規約化(Hermes): opencode-commanderスキルに完了マーカー指示を標準付与 (全runパターン末尾)
- [x] plan: opencode plan案→Hermesが設計化 (design-t3.md確定。plan案をほぼ採用)
- [x] implement(build): oc-monitorのマーカー検知 (message取得+照合、transitions kind=finished即時化、detailにmarker明記)
- [x] implement-r2: レビュー指摘2件修正 ([高]MARKER_TIMEOUT per-request適用、[中]無効化パーサ。verify_marker 6/6 OK)
- [x] live test: 疑似タスク(MARKER-PROBE)で実証。created 23:03:15→marker-finished 23:03:22 (遅延約7秒、180秒待ちなし)。detail=marker:__HERMES_TASK_DONE__ (即時確定)
- 受入: マーカー付きrunが180秒待ちなしでfinished判定される / 検知遅延の計測値あり / TASK-2受入(表示・性能・回帰)を維持

## 実行ログ
- 2026-09-22: TASK-3作成。技術可否確認済み。スキル規約化とTASK-2 testを並行開始。

## Problems (status: open/resolved)
- なし

## Knowledge
- なし
