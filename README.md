# 教育用ブロックチェーン・シミュレーター

物理学科の卒業研究として、ブロックチェーンの基本構造（ハッシュによるブロックの連結、Proof of Work、改ざん検出）を理解し、簡単な数値実験を行うための Python 実装です。

> **注意**
> - 実用的な暗号資産システムではありません。送金・残高・電子署名・手数料は実装していません。
> - Ethereum を忠実に再実装したものではありません。Ethereum Yellow Paper の概念との対応と、簡略化した点は [docs/yellow-paper-comparison.md](docs/yellow-paper-comparison.md) にまとめています。

## 実装したもの / 実装しないもの

| 実装したもの | 実装しないもの |
|---|---|
| 汎用トランザクション（payload は任意の JSON） | 暗号資産の送金・残高管理 |
| SHA-256 によるブロックハッシュ（決定論的シリアライズ） | 電子署名・アカウント・手数料（gas） |
| Genesis Block、ブロックの追加と連結の検証 | P2P ネットワーク、合意形成（フォーク選択） |
| 簡易 Proof of Work（difficulty は変更可能） | スマートコントラクト（EVM） |
| チェーン全体の検証、JSON 保存・読み込み | GUI・Web アプリ・API サーバー |
| CLI、2つの実験スクリプト | 難易度の自動調整、ブロック報酬 |

## 必要な環境

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)（推奨。`brew install uv`）
- [just](https://just.systems/)（任意。`brew install just`。コマンドを短く書くためのタスクランナー）

実行時に必要なのは Python の標準ライブラリだけです。グラフ作成（実験1）にだけ matplotlib を使います。

## セットアップ

```bash
just setup              # = uv sync --extra plot
```

uv を使わない場合:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[plot]" pytest
```

以下では `uv run blockchain ...` と書きます。pip で導入した場合は、仮想環境を有効にしたうえで `blockchain ...`（または `python -m blockchain ...`）と読み替えてください。

## 使い方（CLI）

チェーンは既定で `data/chain.json` に保存されます。別のファイルを使うときは `--file パス` をサブコマンドの前に付けます。

```bash
uv run blockchain init --difficulty 3     # 初期化（Genesis Block のみ）。既存ファイルは --force で上書き
uv run blockchain add-sample --count 3    # サンプルトランザクションを3件追加（未承認として保持）
uv run blockchain add-tx --sender alice --recipient bob --payload '{"text": "hello"}'
uv run blockchain mine                    # 未承認トランザクションをまとめてブロックを採掘
uv run blockchain show                    # チェーンを表示（--json で JSON をそのまま表示）
uv run blockchain validate                # チェーン全体を検証（問題があれば内容を表示し、終了コード 1）
uv run blockchain set-difficulty 4        # difficulty を変更（次のブロックから適用）
uv run blockchain simulate --blocks 5 --difficulty 3   # メモリ上で連続採掘するシミュレーション
```

`mine` の出力例（実際の出力）:

```text
採掘中…（difficulty=3、期待試行回数 16^3 = 4,096）
ブロック#2 を追加しました
  トランザクション数: 3
  nonce:              3522
  ハッシュ計算回数:   3,523
  採掘時間:           0.0055 秒
  ハッシュレート:     635,768 回/秒
  hash:               0003e0b37217f76ceb1d8a51c5f59eaa9a1dc05e5cfaf718d0b76d5c893608f0
```

difficulty を 1 増やすと、採掘にかかる時間の期待値は 16 倍になります。開発環境（Apple M5 Pro、約63万回/秒）での期待値は、difficulty 5 で約1.7秒、6 で約27秒、7 で約7分です（16^d ÷ ハッシュレートで計算）。

`just` を使う場合は `just cli show` のように書けます。`just seed` を実行すると、初期化したうえで 2 ブロック分のサンプルデータを投入します。

## 実験

```bash
just exp-pow       # 実験1: PoW 難易度と計算量（約1分）
just exp-tamper    # 実験2: 改ざんの検出
```

| 実験 | 内容 | 出力 |
|---|---|---|
| 実験1 `experiments/pow_benchmark.py` | difficulty 1〜5 で各30回採掘し、ハッシュ計算回数と時間の平均を理論値 16^d と比較する。difficulty 3 で2000回採掘し、試行回数の分布を幾何分布と比較する | `data/results/pow_benchmark_*.csv` / `.json`、`docs/figures/pow_*.png` / `.pdf` |
| 実験2 `experiments/tampering_demo.py` | チェーンのコピーに4段階の改ざんを加え、検証で検出されるかを確認する | `data/results/tampering_demo.json` |

オプションの例: `just exp-pow --runs 100`（回数を増やす）、`just exp-pow --seed 1`（別の標本で実験する）。

実験1ではブロックの内容（時刻を含む）を固定しているため、ハッシュ計算回数は何度実行しても同じ値になります。実行環境によって変わるのは時間だけです。

結果と考察は [docs/experiment-results.md](docs/experiment-results.md) にまとめています。

## テストと品質チェック

```bash
just test        # pytest（50件）
just lint        # ruff
just typecheck   # mypy（strict）
just ci          # 上の3つを並列実行（GitHub Actions と同じ内容）
```

テストで確認している項目: Genesis Block の生成、ブロック追加、ハッシュ計算の再現性、PoW の成立、改ざんの検知、previous_hash の不一致、JSON 保存・復元、不正なデータの読み込み拒否、CLI、実験スクリプト。

## ディレクトリ構成

```text
.
├── README.md
├── CLAUDE.md                 # AI エージェント向けの作業規約
├── pyproject.toml
├── justfile                  # すべての操作の入口
├── src/blockchain/
│   ├── serialization.py      # 決定論的 JSON、SHA-256、読み込み時の型チェック
│   ├── transaction.py        # Transaction
│   ├── block.py              # Block、ブロックハッシュ、Genesis Block
│   ├── mining.py             # Proof of Work
│   ├── chain.py              # Blockchain（追加・検証・保存・読み込み）
│   └── cli.py                # CLI
├── experiments/
│   ├── pow_benchmark.py      # 実験1
│   └── tampering_demo.py     # 実験2
├── tests/
├── data/
│   ├── chain.json            # CLI の保存先（git 管理外）
│   └── results/              # 実験結果（CSV / JSON）
└── docs/
    ├── architecture.md       # 設計の説明
    ├── yellow-paper-comparison.md
    ├── experiment-results.md # 実験結果と考察
    └── figures/              # 実験1のグラフ
```

指定の構成に加えて、ハッシュ計算と JSON の型チェックを1か所にまとめるため `serialization.py` を追加しています。

## 設計の要点

- **ブロックハッシュ** = SHA-256(正規化した JSON(ヘッダ))。ヘッダは `index`, `timestamp`, `transactions_hash`, `previous_hash`, `nonce`, `difficulty` からなります。
- **決定論的シリアライズ**: キーを辞書順に並べ、空白を入れず、UTF-8 でバイト列にします。時刻はミリ秒単位の整数で扱い、ハッシュ対象に浮動小数点数が入らないようにしています。
- **Genesis Block** は採掘しない固定のブロックです。検証では、既定の Genesis Block と全フィールドが一致するかを確認します。
- **読み込み時の検査**: キーの不足や余分なキー、型の違いがある JSON は拒否します（`bool` を `int` として受け付けることもしません）。さらに、チェーンの検証に失敗した場合も拒否します。

詳しくは [docs/architecture.md](docs/architecture.md) を参照してください。

## 簡略化している主な点

- 電子署名がないため、`sender` は自己申告です。誰でも任意の送信者を名乗れます。
- 同じ内容のトランザクションを二重に取り込むこと（リプレイ）を防ぐ仕組みはありません。
- トランザクション一覧のハッシュは、Merkle 木ではなく一覧全体の単純な SHA-256 です。
- difficulty は利用者が設定する値です。ネットワークの状況に応じた自動調整はありません。
- 検証で確認できるのは「チェーンが内部的に整合しているか」までです。改ざんしたブロック以降をすべて採掘し直したチェーンは検証を通過します（実験2のシナリオ4）。どちらのチェーンが正当かを決める合意形成は実装していません。
