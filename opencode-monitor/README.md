# opencode-monitor

OpenCode (`opencode serve`) のセッション稼働監視。
backend が opencode の `/global/event` (SSE) を購読し、イベント駆動で
opencode→DB 同期→frontend 通知を行う。5秒ポーリングは廃止済み
(60秒セーフティネットのみ残存)。

構成: `backend/` (FastAPI, 4100) + `frontend/` (Vite+React, 5173)。

起動 (Windows):

  start-oc-monitor.bat

をダブルクリック。opencode serve (4096) + backend + frontend が別窓で起動する。

手動起動:

  opencode serve --port 4096 --hostname 127.0.0.1
  cd backend && python -m venv .venv && .venv\Scripts\activate.bat
  pip install -r requirements.txt
  uvicorn app.main:app --port 4100
  cd ..\frontend && npm install && npm run dev -- --port 5173

環境変数 (主なもの): `OPENCODE_BASE_URL`, `EVENTWATCH_ENABLED=0` で
イベント購読を無効化 (セーフティネット+手動syncにフォールバック),
`EVENT_DEBOUNCE_SEC`, `EVENT_SAFETY_SEC`, `FINISH_IDLE_SEC`,
`MARKER_ENABLED`, `DB_PATH`。

検証:

  cd backend && .venv\Scripts\python.exe scripts/verify_eventwatch.py
  cd ..\frontend && npm run build
