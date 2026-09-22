# TASK-1: oc-monitor 構築 (opencode 並列監視Webツール)

## 目的
opencode のエージェント稼働状況・ステータス・完了可否・履歴を一括並列確認できる自前Webツールを作る。

## 制約
- Web UI / 当面ローカルのみ(将来マルチホスト拡張) / 監視+完了検知のみ(操作なし)
- Backend: Python+FastAPI+SSE+SQLite / Frontend: React+Vite+MUI / データ源: opencode server APIのみ(プラグイン不要)
- opencode 1.18.x固定。Windows動作必須
- コミット・プッシュはユーザー明示指示までしない

## フェーズと受け入れ条件
- [x] P1 骨格: FastAPIが /api/session を取得・正規化しSQLite保存。受入: 既存セッション60件前後がDBに入る (実績: live 72件一致・冪等確認。レビュー条件付き→5件修正→検証OK)
- [x] P2 画面: MUIカード一覧+SSE更新+詳細+直接リンク。受入: 手動runが数秒で一覧に現れる (実績: テスト4項目合格・レビュー指摘1件修正・Hermes目視で77件カード+SSELIVE確認)
- [x] P3 完了検知: 状態遷移検出+通知+履歴検索。受入: 終了時に通知が出る (実績: テスト4項目合格・レビュー4件修正・Hermes目視で通知Chip/完了の可能性Alert・バッジ確認)
- [x] P4 堅牢化: spec差分警告・サーバー断表示・起動bat化。受入: サーバー停止時もUIが壊れない (実績: テスト3/4合格+stale再起動で4/4、Hermes断線実証で警告+一覧保持、復旧live確認)

## 実行ログ
- 2026-09-21: TASK-1作成。P1着手。
- 2026-09-22: 5秒自動sync化 (useSessionsのintervalをrefreshList→doSync化。syncingRefガードで重複skip)。直接リンクをopencode web正規形式 /<base64url(directory)>/session/<id> に修正 (旧/session/<id>はAPIにシャドウされJSONを返す。directoryはraw→project.pathの順で解決、不明時はwebルート)。tsc+vite build通過、実機で200 text/html確認。
- 2026-09-22: 最新セッション欠落を修正。原因: 旧GET /sessionはlimit/startを無視し固定87件のみ返却 (実ストア126件)。sync元を/api/sessionカーソル全走査との和集合に変更 (opencode_client.list_sessions_webui追加、legacy優先マージ)。frontend getSessionModelにmodel.idパス追加。sync 87→126件、再sync冪等、P1/P3/P4 verify ALL OK、build通過。

## Problems (status: open/resolved)
- resolved: 4096番ゾンビは解消(再起動後にLISTENなしを確認)。2026-09-22にopencode web --port 4096で正常起動、health healthy (1.18.31)。backendは既定OPENCODE_BASE_URL=http://localhost:4096のまま4100で稼働、sync 87件確認。

## Knowledge
- TASK-1全フェーズ完了。P1→レビュー1周、P2→レビュー1周、P3→レビュー1周、P4→レビュー1周。全て受入達成。
- 運用注意: backend(4100)/frontend(5173)/opencode(4097)はHermesバックグラウンドで稼働中。マシン再起動時はstart-oc-monitor.bat + opencode web --port で上げ直し。

## Knowledge
- なし
