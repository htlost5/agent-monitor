# TASK-1 P1 設計 (Hermes確定。opencode plan案をブラッシュアップ)

## 決定事項 (planの確認点への回答)
1. Backendポート4100 (4096はopencode占有)。変更なし。
2. プロジェクト専用venv `.venv` を作る。hermes venvを汚さない。
3. P1でmessageは保存対象外。sessions/projects/sync_stateのみ。

## 成果物
- backend/requirements.txt (fastapi, uvicorn, httpx のみ)
- backend/app/config.py (OPENCODE_BASE_URL=http://localhost:4096, APP_PORT=4100, DB_PATH=backend/data/oc_monitor.db)
- backend/app/store.py (sqlite3直書き。projects/sessions/sync_state。上記スキーマ)
- backend/app/opencode_client.py (httpx。/api/session・/project・/global/health取得。ConnectError時は例外化)
- backend/app/main.py (FastAPI。GET /api/health, POST /api/sync, GET /api/sessions, GET /api/projects, GET /api/events(SSE heartbeat+sync通知))
- backend/scripts/verify_p1.py (件数一致・冪等upsertを検証し0/非0で終了)
- backend/data/.gitkeep + root .gitignoreに *.db 追加

## 受入条件
- POST /api/sync 後に sessions件数 == GET /session件数。再実行で件数不変。
- opencode停止時は503 + {"opencode_reachable":false} を返しプロセスは落ちない。

## 禁止
- git commit/push。message取得の実装。プラグイン導入。
