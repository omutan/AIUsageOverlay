# AI Usage Overlay

A tiny always-on-top desktop overlay (Windows) that shows the **5‑hour** and
**weekly** usage of multiple AI assistants at a glance — no API keys, no tokens,
no login. It just reads the usage files those apps already write on your PC.

日本語は下 → [日本語](#日本語)

![themes](docs/themes.png)

---

## Disclaimer
- This is an **unofficial** desktop overlay UI / tool.
- Not affiliated with, endorsed by, or sponsored by OpenAI, Anthropic, or any
  other AI service provider.
- All icons are original abstract symbols created for this project.
- Brand names are used only for identification purposes.

## How it works
It reads local usage files each app writes for itself (lock‑free, read‑only):

| Provider | Source file | 5‑hour | Weekly |
|---|---|---|---|
| Claude | `%APPDATA%\Claude\plan-usage-history.json` | `fh` | `sd` |
| ChatGPT / Codex | newest `~/.codex/sessions/**/rollout-*.jsonl` → last `rate_limits` | `primary` (300 min) | `secondary` (10080 min) |
| others | — (add your own, see below) | — | — |

Only the AIs you actually use will show data; disable the rest in Settings.

## Requirements
- Windows 10/11
- Python 3.9+ with Tkinter (standard), and: `pip install -r requirements.txt`
  (`pywin32`, `pillow`, `pystray`)

## Run
- Double‑click **`start.vbs`** (no console window), or run `start.bat`.
- Stop: `stop.vbs`. Auto‑start on boot: `install_autostart.vbs`
  (undo with `remove_autostart.vbs`).

## Use
- **Move**: drag the window (position is saved).
- **Switch AI**: the dropdown top‑left (All / a single one).
- **⚙ Settings → Theme**: Simple / Pastel / Pop / Neon (applies instantly).
- **⚙ Settings**: enable/disable AIs, rename them, per‑AI color, display mode,
  color‑by‑usage, opacity, size, refresh interval.
- **🕐 next to a name**: click to see time until each window resets.
- **✕**: hide to the system tray; click the tray icon → Show to bring it back.

## Add another AI
1. In `providers.py`, add a function returning
   `{ok, five, week, plan, reset_five, reset_week, note}` and register it in
   `REGISTRY`.
2. In `badge_config.json`, add
   `{"id","name","type","enabled","icon","color"}` to `providers`.
   `icon` is one of the abstract motifs (moon, star, crystal, bolt, hex, wave,
   ring, triangle, square, orb, orbit, dots).

## Build a standalone .exe (optional)
```
pip install pyinstaller
pyinstaller --onefile --noconsole --name AIUsageOverlay ^
  --hidden-import pystray._win32 badge.py
```
The `.exe` appears in `dist\`. It keeps `badge_config.json` next to the exe.

---

## 日本語

複数AIの **5時間枠 / 週間枠** を、画面の隅に常時最前面で小さく表示する
Windows用オーバーレイです。**APIキーもトークンもログインも不要** — 各アプリが
自分でPCに書き出している使用量ファイルを読むだけ。

### 非公式ツールについて
- 本プロジェクトは**非公式**のデスクトップオーバーレイUI / ツールです。
- OpenAI、Anthropic、その他AIサービス提供元とは提携・承認・協賛関係はありません。
- アイコンは本プロジェクト用に作成したオリジナルの抽象記号です。
- サービス名は識別のためにのみ使用しています。

### しくみ
各アプリがローカルに書き出すファイルを読み取ります（読み取り専用・ロックなし）。

| 対応 | 読むファイル | 5時間枠 | 週間枠 |
|---|---|---|---|
| Claude | `%APPDATA%\Claude\plan-usage-history.json` | `fh` | `sd` |
| ChatGPT / Codex | 最新 `~/.codex/sessions/**/rollout-*.jsonl` の `rate_limits` | `primary`(300分) | `secondary`(10080分) |
| その他 | —（自分で追加可） | — | — |

使っているAIだけ数値が出ます。使っていないものは設定でOFFに。

### 必要なもの
- Windows 10/11
- Python 3.9+（Tkinter同梱）＋ `pip install -r requirements.txt`

### 起動
- **`start.vbs`** をダブルクリック（コンソール無し）／ または `start.bat`
- 停止: `stop.vbs`／自動起動: `install_autostart.vbs`（解除: `remove_autostart.vbs`）

### 使い方
- **移動**: 窓をドラッグ（位置保存）
- **AI切替**: 左上ドロップダウン（すべて / 個別）
- **⚙ 設定 → テーマ**: シンプル / パステル / ポップ / ネオン（即時反映）
- **⚙ 設定**: AIのON/OFF・名前変更・AI別カラー・表示モード・使用率で色分け・
  不透明度・サイズ・更新間隔
- **🕐（名前の右）**: クリックで各枠の回復までの時間
- **✕**: トレイに格納。トレイのアイコン→「表示」で復帰

### AIを追加する
`providers.py` に読み取り関数を足して `REGISTRY` に登録 →
`badge_config.json` の `providers` に1件追加するだけ。

### ライセンス
MIT License（`LICENSE` 参照）
