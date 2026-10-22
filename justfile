set shell := ["bash", "-c"]
set dotenv-load := true
set dotenv-filename := ".env"

# このリポジトリは Docker やサーバーを使わないため up / down / logs / port は置かない。

# レシピ一覧
default:
    @just --list --unsorted

# 依存関係をインストール（グラフ用の matplotlib を含む）
setup:
    uv sync --extra plot

# CLI を実行する（例: just cli show / just cli mine）
cli *args:
    uv run blockchain {{ args }}

# data/chain.json を消し、Genesis Block だけの決定的な初期状態に戻す
reset:
    rm -f data/chain.json
    uv run blockchain init

# 初期化してからサンプルデータを投入する（3 トランザクション × 2 ブロック）
seed: reset
    uv run blockchain add-sample --count 3
    uv run blockchain mine
    uv run blockchain add-sample --count 3
    uv run blockchain mine

# テスト一式
test:
    uv run pytest

# テストを1つだけ実行（例: just test-one tests/test_blockchain.py::test_pow_meets_difficulty）
test-one target:
    uv run pytest {{ target }}

# 型チェック（experiments の型解決に matplotlib が必要）
typecheck:
    uv run --extra plot mypy

# lint とフォーマット確認
lint:
    uv run ruff check . --output-format concise
    uv run ruff format --check .

# 自動整形と lint の自動修正
fmt:
    uv run ruff format .
    uv run ruff check . --fix

# CI 相当（lint / typecheck / test）を並列実行し、ジョブごとの結果を JSON Lines で出力する
ci:
    #!/usr/bin/env bash
    set -uo pipefail
    uv sync --extra plot --quiet
    logdir=$(mktemp -d)
    jobs=(lint typecheck test)
    pids=()
    for job in "${jobs[@]}"; do
        just "$job" > "$logdir/$job.log" 2>&1 &
        pids+=($!)
    done
    failed=()
    for i in "${!jobs[@]}"; do
        if wait "${pids[$i]}"; then status=pass; else status=fail; failed+=("${jobs[$i]}"); fi
        printf '{"job":"%s","status":"%s","log":"%s"}\n' "${jobs[$i]}" "$status" "$logdir/${jobs[$i]}.log"
    done
    # 空配列でも set -u で落ちないように展開する（macOS 標準の bash 3.2 対策）
    for job in ${failed[@]+"${failed[@]}"}; do
        printf '\n===== %s =====\n' "$job"
        tail -n 40 "$logdir/$job.log"
    done
    [ ${#failed[@]} -eq 0 ]

# 実験1: PoW 難易度と計算量（引数は experiments/pow_benchmark.py にそのまま渡す）
exp-pow *args:
    uv run --extra plot python experiments/pow_benchmark.py {{ args }}

# 実験2: 改ざんの検出
exp-tamper *args:
    uv run python experiments/tampering_demo.py {{ args }}

# 実験1と実験2をまとめて実行
experiments: exp-pow exp-tamper

# worktree を作成する（ブランチが既にあれば再利用）。ポートを使わないため採番はしない
wt name:
    #!/usr/bin/env bash
    set -euo pipefail
    root=$(git rev-parse --show-toplevel)
    dir="$root/../$(basename "$root")-worktrees/{{ name }}"
    if git show-ref --verify --quiet "refs/heads/{{ name }}"; then
        git worktree add "$dir" "{{ name }}"
    else
        git worktree add -b "{{ name }}" "$dir"
    fi
    printf '{"worktree":"%s","branch":"%s"}\n' "$dir" "{{ name }}"

# worktree を削除する（ブランチは残す）
wt-rm name:
    #!/usr/bin/env bash
    set -euo pipefail
    root=$(git rev-parse --show-toplevel)
    git worktree remove "$root/../$(basename "$root")-worktrees/{{ name }}"

# worktree の一覧
wt-ls:
    git worktree list --porcelain
