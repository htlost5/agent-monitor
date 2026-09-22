# backend/data 配下の扱い

- `spec_snapshot.json`: ベースラインとしてコミット対象。
  - opencode `/doc` (OpenAPI JSON) のエンドポイント一覧スナップショット。
  - `/api/spec-check` がこのスナップショットと live の `/doc` を比較して drift を警告する。
  - 意図的な仕様変更以外は更新しないこと。差分が出たらまず drift か snapshot 陳腐化かを確認する。
- `oc_monitor.db*`: 実行時のローカル成果物。コミット対象外 (`.gitignore` で `*.db` / `*.db-wal` / `*.db-shm` / `*.db-journal` を除外)。
- `.gitkeep`: 空ディレクトリ維持用。

## snapshot 更新手順

1. opencode を起動する (既定 `http://localhost:4096`)。
2. live の `/doc` が正しいことを確認する (意図した opencode バージョンであること)。
3. backend 側で snapshot を再生成する:
   - 初回は `/api/spec-check` アクセス時に自動生成されるが、意図的更新時は既存ファイルを削除せず内容を確認の上で更新する。
   - 手動再生成の例 (repo root から):
     - `backend/data/spec_snapshot.json` を退避し、opencode 起動状態で `GET /api/spec-check` を叩いて再生成させるか、
       `app.spec_check.save_snapshot(app.spec_check.extract_paths(app.spec_check.fetch_doc()))` 相当で保存する。
4. `backend/scripts/verify_p4.py` を通す。
5. `git diff backend/data/spec_snapshot.json` で差分が意図的変更のみであることを確認してから commit する。
   - required (`/global/health`, `/project`, `/session`) の消失は drift 警告になるため、opencode 側の仕様変更でなければ snapshot を更新しない。
