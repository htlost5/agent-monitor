# TASK-1 P2 設計 (Hermes確定)

## 決定事項
1. 直接リンクベースURL http://localhost:4096 (.env VITE_OCODE_WEB_URLで切替可)。
2. ポーリング5秒 (isSyncing重複skip)。
3. 詳細は右Drawer。

## 成果物 (frontend新規)
- package.json, vite.config.ts (proxy /api→4100 + CORS二重保険), tsconfig, index.html, .env.example
- src/main.tsx, App.tsx (ヘッダー: 接続状態・最終sync・手動Sync), api.ts, lib.ts (elapsed整形・base64url), useSessions.ts (初回sync→list、5s interval+EventSource、1sローカルtick)
- src/components/SessionGrid.tsx (MUI Grid+Card), DetailPanel.tsx (MUI Drawer: トークン・コスト・直接リンク+コピー)

## backend変更 (1点のみ)
- backend/app/main.py にCORS追加 (約5行)

## 受入条件
- 手動runが5〜10秒でカード先頭に出現。Drawerにtokens・cost・直接リンク表示+コピー可。
- opencode停止時もUIがクラッシュしないこと。

## 禁止
- git commit/push。store/client/configの変更。
