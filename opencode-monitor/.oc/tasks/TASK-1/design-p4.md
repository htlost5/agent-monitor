# TASK-1 P4 設計 (Hermes確定)

## 決定事項
1. /docはOpenAPI 3.1 JSON (実測478KB)。到達不可時は警告1件に留めok=falseでも200。
2. GET /api/spec-check を独立endpoint (health不変)。
3. start-oc-monitor.batはルート配置、venvはbackend/.venv前提。
4. vite preview注記は.env.example末尾。snapshotはdata/配下+gitignore 1行追記可。

## 成果物
Backend: spec_snapshot.json(初回生成)、app/spec_check.py新規、main.pyにGET /api/spec-check追加(既存7不変)、scripts/verify_p4.py新規
Frontend: api.ts型+fetch追加、hooks/useSpecCheck.ts新規、App.tsx警告+バナー、OfflineBanner新規、useSessions/useTransitionNotify/SessionGrid最小修正(ガード・memo)、.env.example注記
ルート: start-oc-monitor.bat新規 (backend venv+uvicorn 4100とfrontend dev 5173を2窓起動、/kで窓残す)

## 受入条件
- opencode停止→黄バナー+一覧保持。backend停止→赤バナー+一覧保持。復帰後5〜10秒でlive復帰。
- batダブルクリックで両起動。

## 繰越反映 (P2/P3低優先)
- in-flightガード、再レンダmemo化、vite preview注記

## 禁止
- git commit/push。既存API破壊。
