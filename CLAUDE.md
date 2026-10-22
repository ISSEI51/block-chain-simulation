# CLAUDE.md

物理学科の卒業研究用の、教育用ブロックチェーン・シミュレーター（Python）。
利用者は Ethereum Yellow Paper を学習中であり、コードは「読んで理解できること」を最優先にする。

## スコープ（変更しないこと）

- 実用的な暗号資産システムにしない。送金・残高管理・金銭的価値を持つ機能は実装しない。
- GUI / Web アプリ / API サーバー / P2P ネットワーク / スマートコントラクトは実装しない。
- 実行時の依存は標準ライブラリのみ。matplotlib は実験1のグラフ作成（extra `plot`）だけで使う。
- 過剰設計を避ける。抽象化レイヤーや設定ファイルを増やさない。

## コマンド（すべて justfile 経由）

| 目的 | コマンド |
|---|---|
| 依存のインストール | `just setup` |
| テスト / 1件だけ | `just test` / `just test-one tests/test_blockchain.py::test_name` |
| lint / 型チェック / 整形 | `just lint` / `just typecheck` / `just fmt` |
| CI 相当（並列） | `just ci`（`.github/workflows/ci.yml` と同じ3ジョブ） |
| CLI | `just cli <subcommand>` |
| データ初期化 / サンプル投入 | `just reset` / `just seed` |
| 実験 | `just exp-pow` / `just exp-tamper` |

## コードの規約

- 重要な関数には、何をなぜ行うかを日本語の docstring で書く。
- ハッシュ対象のデータは `serialization.canonical_json` を通す。ハッシュ対象に浮動小数点数の時刻を入れない（時刻はミリ秒の整数）。
- ハッシュの計算方法（`Block.header()` や `Transaction.content()`）を変えると、既存の保存データと
  `tests/test_blockchain.py` の既知ハッシュ値のテストが変わる。変える場合は docs/architecture.md も更新する。
- JSON 読み込みは `parse_fields` でキーと型を厳密に確認する。不正なデータは黙って補正せず拒否する。
- 実験結果（`data/results/`、`docs/figures/`）はコミットする。`data/chain.json` はコミットしない。
- 実験スクリプトを変えたら `just exp-pow` / `just exp-tamper` を再実行し、`docs/experiment-results.md` の数値と合っているか確認する。

## ドキュメント

- `docs/architecture.md` … 設計（ハッシュ計算、検証ルール、JSON 形式）
- `docs/yellow-paper-comparison.md` … Yellow Paper との対応と簡略化した点。Ethereum を忠実に再実装したと誤解される表現を書かない
- `docs/experiment-results.md` … 実験結果と考察
