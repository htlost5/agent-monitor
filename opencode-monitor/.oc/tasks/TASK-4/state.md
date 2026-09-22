# TASK-4: ダークモード

## 目的
- oc-monitor frontendにダークモードを追加する (ライト/ダーク切替)。

## 制約
- Frontend: React+Vite+MUI のみで実現 (新規依存なし)。Backend変更なし。
- 既定は現状維持 (ライト)。切替は localStorage に永続化。
- Windows動作必須。コミット・プッシュはユーザー明示指示までしない

## フェーズと受け入れ条件
- [x] plan: opencode plan案→Hermesが設計化 (design-t4.md確定。plan案をそのまま採用)
- [x] implement(build): Theme切替実装 (tsc + vite build通過)
- [x] test: Hermes実機確認で承認 (既定ライト→切替→再読込維持→復帰、両モード目視で判別可、コンソールエラーなし。マーカー確定バナーもダーク表示で確認)
- 受入: AppBar等からワンクリック切替、再読込後も維持、既存の配色(稼働中=緑等の状態色)が両モードで判別可、TASK-2/3回帰なし

## 実行ログ
- 2026-09-22: TASK-4作成。
- 2026-09-22: ダークモード実装・実機承認・Discord通知済み。
- 2026-09-22: follow-up(r2) 既定テーマをライト→ダークに変更 (保存済み設定の尊重は維持)。

## Problems (status: open/resolved)
- なし

## Knowledge
- なし
