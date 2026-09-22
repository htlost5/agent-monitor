# agent-monitor

エージェント稼働監視ツール群。監視対象ごとに1フォルダ。

- opencode-monitor/ : OpenCode セッション監視 (backend FastAPI + frontend React)。
  opencode serve のイベントを購読し、セッション作成・更新・完了を検知する。
- (予定) hermes-monitor/ : Hermes 側の監視。

各フォルダが独立して起動・管理できる構成にする。共通化が必要になった時点で
共通ライブラリの切り出しを検討する。
