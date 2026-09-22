# TASK-4 正式設計 (Hermes確定・plan案採用)

## 決定事項
- plan案をそのまま採用。追加判断なし (小規模・方向性明確のため)。
- 要点: MUI `createTheme({palette:{mode}})` + `ThemeProvider`+`CssBaseline`一元化、既定ライト・遅延初期化、localStorageキー`oc-monitor:theme`、AppBarに明暗アイコン切替、色ハードコードなし、初回フラッシュ完全排除は見送り。

## 検証 (build自己検証→Hermes実機)
- `tsc --noEmit` + `vite build`。
- Hermes実機: ライト既定→切替→再読込維持→復帰、両モード目視 (状態色判別)、コンソールエラーなし。

## 非スコープ
Backend変更、新規パッケージ、システム連動、3値切替。
