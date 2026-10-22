"""コマンドラインインターフェース。

例:
    blockchain init --difficulty 3
    blockchain add-sample --count 3
    blockchain mine
    blockchain show
    blockchain validate
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from blockchain.chain import DEFAULT_DIFFICULTY, Blockchain
from blockchain.transaction import Transaction

DEFAULT_PATH = Path("data/chain.json")
SLOW_DIFFICULTY = 7  # これ以上は Python では1ブロックに数分〜数時間かかる

# サンプルトランザクションのひな形（sender, recipient, payload）。
# 何を取引するかは未定なので、payload は「任意のJSON」の例として複数の形を用意する。
SAMPLES: list[tuple[str, str, dict[str, Any]]] = [
    ("alice", "bob", {"type": "message", "text": "こんにちは"}),
    (
        "sensor-01",
        "lab-server",
        {"type": "measurement", "quantity": "temperature", "value": 295.15, "unit": "K"},
    ),
    ("bob", "carol", {"type": "record", "title": "実験ノート", "tags": ["PoW", "SHA-256"]}),
]


def format_time(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="seconds")


def sample_transaction(seq: int) -> Transaction:
    sender, recipient, payload = SAMPLES[seq % len(SAMPLES)]
    return Transaction.create(sender, recipient, {**payload, "seq": seq})


def cmd_init(args: argparse.Namespace) -> int:
    if args.file.exists() and not args.force:
        print(
            f"エラー: {args.file} は既に存在します。上書きするには --force を付けてください",
            file=sys.stderr,
        )
        return 1
    chain = Blockchain(difficulty=args.difficulty)
    chain.save(args.file)
    print(f"初期化しました: {args.file}（difficulty={chain.difficulty}）")
    print(f"Genesis Block hash: {chain.chain[0].hash}")
    return 0


def cmd_add_sample(args: argparse.Namespace) -> int:
    chain = Blockchain.load(args.file)
    start = sum(len(b.transactions) for b in chain.chain) + len(chain.pending_transactions)
    for seq in range(start, start + args.count):
        tx = sample_transaction(seq)
        chain.add_transaction(tx)
        print(f"追加: {tx.transaction_id[:16]}…  {tx.sender} → {tx.recipient}  {tx.payload}")
    chain.save(args.file)
    print(f"未承認トランザクション: {len(chain.pending_transactions)} 件")
    return 0


def cmd_add_tx(args: argparse.Namespace) -> int:
    chain = Blockchain.load(args.file)
    tx = Transaction.create(args.sender, args.recipient, json.loads(args.payload))
    chain.add_transaction(tx)
    chain.save(args.file)
    print(f"追加: {tx.transaction_id}")
    return 0


def cmd_mine(args: argparse.Namespace) -> int:
    chain = Blockchain.load(args.file)
    if not chain.pending_transactions:
        print("注意: 未承認トランザクションがないため、空のブロックを採掘します")
    print(
        f"採掘中…（difficulty={chain.difficulty}、期待試行回数 16^{chain.difficulty}"
        f" = {16**chain.difficulty:,}）"
    )
    block, result = chain.mine_pending_transactions()
    chain.save(args.file)
    print(f"ブロック#{block.index} を追加しました")
    print(f"  トランザクション数: {len(block.transactions)}")
    print(f"  nonce:              {result.nonce}")
    print(f"  ハッシュ計算回数:   {result.attempts:,}")
    print(f"  採掘時間:           {result.elapsed_seconds:.4f} 秒")
    print(f"  ハッシュレート:     {result.hash_rate:,.0f} 回/秒")
    print(f"  hash:               {block.hash}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    chain = Blockchain.load(args.file, verify=False)
    if args.json:
        print(json.dumps(chain.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(
        f"ブロック数: {len(chain.chain)}（Genesis Block を含む）  "
        f"未承認トランザクション: {len(chain.pending_transactions)} 件  "
        f"次のブロックの difficulty: {chain.difficulty}"
    )
    for b in chain.chain:
        print(
            f"\n#{b.index}  {format_time(b.timestamp)}  tx={len(b.transactions)}  "
            f"difficulty={b.difficulty}  nonce={b.nonce}"
        )
        print(f"  previous_hash: {b.previous_hash}")
        print(f"  hash:          {b.hash}")
        for tx in b.transactions:
            print(
                f"    - {tx.transaction_id[:16]}…  {tx.sender} → {tx.recipient}  "
                f"{json.dumps(tx.payload, ensure_ascii=False)}"
            )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    chain = Blockchain.load(
        args.file, verify=False
    )  # 検証結果を詳しく表示するため読み込み時は検証しない
    errors = chain.validate()
    if errors:
        print(f"NG: {len(errors)} 件の問題が見つかりました")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK: チェーンは正しい形式です（{len(chain.chain)} ブロック）")
    return 0


def cmd_set_difficulty(args: argparse.Namespace) -> int:
    chain = Blockchain.load(args.file)
    old = chain.difficulty
    chain.set_difficulty(args.difficulty)
    chain.save(args.file)
    print(f"difficulty を {old} → {chain.difficulty} に変更しました（次のブロックから適用）")
    if chain.difficulty >= SLOW_DIFFICULTY:
        print(f"注意: 期待試行回数は {16**chain.difficulty:,} 回です。採掘に長時間かかります")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    """メモリ上で新しいチェーンを作り、複数ブロックを連続で採掘する。"""
    chain = Blockchain(difficulty=args.difficulty)
    seq = 0
    print(
        f"difficulty={args.difficulty}, ブロック数={args.blocks}, "
        f"1ブロックあたりのトランザクション数={args.txs_per_block}"
    )
    print(f"{'block':>5} {'tx':>3} {'nonce':>10} {'attempts':>10} {'seconds':>9}  hash")
    total_attempts, total_seconds = 0, 0.0
    for _ in range(args.blocks):
        for _ in range(args.txs_per_block):
            chain.add_transaction(sample_transaction(seq))
            seq += 1
        block, r = chain.mine_pending_transactions()
        total_attempts += r.attempts
        total_seconds += r.elapsed_seconds
        print(
            f"{block.index:>5} {len(block.transactions):>3} {r.nonce:>10} {r.attempts:>10} "
            f"{r.elapsed_seconds:>9.4f}  {block.hash[:24]}…"
        )
    print(
        f"\n合計ハッシュ計算回数: {total_attempts:,}（1ブロック平均 "
        f"{total_attempts / args.blocks:,.0f}、理論値 16^{args.difficulty} = "
        f"{16**args.difficulty:,}）"
    )
    print(f"合計採掘時間: {total_seconds:.3f} 秒")
    print("検証結果: " + ("OK" if chain.is_valid() else "NG " + "; ".join(chain.validate())))
    if args.save:
        chain.save(args.save)
        print(f"保存しました: {args.save}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blockchain", description="教育用ブロックチェーン")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_PATH,
        help=f"チェーンの保存先JSON（既定: {DEFAULT_PATH}）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="ブロックチェーンを初期化（Genesis Block のみ）")
    p.add_argument("--difficulty", type=int, default=DEFAULT_DIFFICULTY)
    p.add_argument("--force", action="store_true", help="既存ファイルを上書きする")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add-sample", help="サンプルトランザクションを追加")
    p.add_argument("--count", type=int, default=3)
    p.set_defaults(func=cmd_add_sample)

    p = sub.add_parser("add-tx", help="任意のトランザクションを追加")
    p.add_argument("--sender", required=True)
    p.add_argument("--recipient", required=True)
    p.add_argument("--payload", required=True, help='JSONオブジェクト。例: \'{"text": "hi"}\'')
    p.set_defaults(func=cmd_add_tx)

    sub.add_parser("mine", help="未承認トランザクションからブロックを生成").set_defaults(
        func=cmd_mine
    )

    p = sub.add_parser("show", help="チェーンを表示")
    p.add_argument("--json", action="store_true", help="JSONをそのまま表示")
    p.set_defaults(func=cmd_show)

    sub.add_parser("validate", help="チェーン全体を検証").set_defaults(func=cmd_validate)

    p = sub.add_parser("set-difficulty", help="PoW の difficulty を変更")
    p.add_argument("difficulty", type=int)
    p.set_defaults(func=cmd_set_difficulty)

    p = sub.add_parser("simulate", help="メモリ上で複数ブロックを連続採掘する")
    p.add_argument("--blocks", type=int, default=5)
    p.add_argument("--difficulty", type=int, default=DEFAULT_DIFFICULTY)
    p.add_argument("--txs-per-block", type=int, default=2)
    p.add_argument("--save", type=Path, default=None, help="結果のチェーンを保存するJSONパス")
    p.set_defaults(func=cmd_simulate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except FileNotFoundError as e:
        print(
            f"エラー: ファイルがありません: {e.filename}（先に init を実行してください）",
            file=sys.stderr,
        )
    except (ValueError, TypeError, OSError) as e:  # InvalidDataError / InvalidChainError を含む
        print(f"エラー: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
