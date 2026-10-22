"""実験2: 改ざんの検出。

既存ブロックのトランザクションを書き換え、検証で不正が検出されることを示す。
元のチェーンは壊さないよう、各シナリオは copy.deepcopy したコピーに対して行う。

改ざんする側の「手間」を4段階に分けて、どこで検出されるかを確認する:
  1. payload を書き換えるだけ
  2. さらに transaction_id とブロックの hash を再計算する（PoW はやり直さない）
  3. さらに改ざんしたブロックだけ PoW をやり直す
  4. 改ざんしたブロック以降をすべて PoW でやり直す

実行例:
    uv run python experiments/tampering_demo.py
"""

import argparse
import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from blockchain import Blockchain, Transaction, mine

ROOT = Path(__file__).resolve().parent.parent
BASE_TIMESTAMP = 1_700_000_000_000  # 再現性のため時刻を固定（ミリ秒）
TARGET = 2  # 改ざんするブロックの番号

CONCLUSION = """
考察: シナリオ1〜3はハッシュの連鎖によって検出できる。シナリオ4は検証を通過する。
      つまり検証で分かるのは「チェーンが内部的に整合しているか」までである。
      どちらのチェーンが正当かは、ネットワーク上の合意で決まる
      （PoW では累積仕事量が最大のチェーン、Ethereum の PoS ではバリデータの投票とファイナリティ）。
      本実装は P2P ネットワークと合意形成を実装していないため、この部分は扱わない。"""


def build_chain(difficulty: int, blocks: int) -> Blockchain:
    """改ざん前の正しいチェーンを作る（内容は固定なので毎回同じチェーンになる）。"""
    chain = Blockchain(difficulty=difficulty)
    for i in range(1, blocks + 1):
        for j in range(2):
            chain.add_transaction(
                Transaction.create(
                    f"lab-member-{j}",
                    "lab-log",
                    {
                        "type": "measurement",
                        "block": i,
                        "item": j,
                        "value_mK": 295_150 + 10 * i + j,
                    },
                    timestamp=BASE_TIMESTAMP + 1000 * i + j,
                )
            )
        chain.mine_pending_transactions(timestamp=BASE_TIMESTAMP + 1000 * i + 500)
    return chain


def edit_payload(chain: Blockchain) -> Blockchain:
    """シナリオ1: 対象ブロックの最初のトランザクションの値を書き換える（コピーに対して）。"""
    c = copy.deepcopy(chain)
    c.chain[TARGET].transactions[0].payload["value_mK"] = 999_999
    return c


def edit_and_rehash(chain: Blockchain) -> Blockchain:
    """シナリオ2: 書き換えた上で、transaction_id とブロックの hash を辻褄が合うよう再計算する。"""
    c = edit_payload(chain)
    block = c.chain[TARGET]
    for tx in block.transactions:
        tx.transaction_id = tx.compute_id()
    block.hash = block.compute_hash()  # nonce は元のまま。PoW 条件はほぼ確実に満たさない
    return c


def edit_and_remine_one(chain: Blockchain) -> Blockchain:
    """シナリオ3: 書き換えたブロックだけ PoW をやり直す。"""
    c = edit_and_rehash(chain)
    mine(c.chain[TARGET])
    return c


def edit_and_remine_all(chain: Blockchain) -> tuple[Blockchain, int]:
    """シナリオ4: 書き換えたブロック以降を、つながりを付け替えながらすべて掘り直す。"""
    c = edit_and_rehash(chain)
    attempts = 0
    for i in range(TARGET, len(c.chain)):
        c.chain[i].previous_hash = c.chain[i - 1].hash
        attempts += mine(c.chain[i]).attempts
    return c, attempts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="実験2: 改ざんの検出")
    parser.add_argument("--difficulty", type=int, default=4)
    parser.add_argument("--blocks", type=int, default=5, help="Genesis 以外のブロック数")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data" / "results" / "tampering_demo.json"
    )
    args = parser.parse_args(argv)
    if args.blocks < TARGET + 1:
        parser.error(f"--blocks は {TARGET + 1} 以上にしてください")

    original = build_chain(args.difficulty, args.blocks)
    before = json.dumps(original.to_dict(), sort_keys=True)
    print(f"元のチェーン: Genesis + {args.blocks} ブロック、difficulty={args.difficulty}")
    print(f"  検証: {'OK' if original.is_valid() else 'NG'}")
    print(
        f"  改ざん対象: ブロック#{TARGET} の payload "
        f"{original.chain[TARGET].transactions[0].payload}"
    )

    results: list[dict[str, Any]] = []
    scenarios: list[tuple[str, Callable[[Blockchain], Blockchain]]] = [
        ("1. payload を書き換えるだけ", edit_payload),
        ("2. transaction_id と hash も再計算（PoW なし）", edit_and_rehash),
        ("3. 改ざんしたブロックだけ PoW をやり直す", edit_and_remine_one),
    ]
    for title, scenario in scenarios:
        errors = scenario(original).validate()
        results.append({"scenario": title, "detected": bool(errors), "errors": errors})

    rewritten, attempts = edit_and_remine_all(original)
    errors = rewritten.validate()
    blocks_redone = len(rewritten.chain) - TARGET
    results.append(
        {
            "scenario": "4. 改ざんしたブロック以降をすべて PoW でやり直す",
            "detected": bool(errors),
            "errors": errors,
            "remined_blocks": blocks_redone,
            "remine_attempts": attempts,
            "expected_attempts": blocks_redone * 16**args.difficulty,
        }
    )

    for r in results:
        print(f"\n[{r['scenario']}]")
        print("  → " + ("不正を検出" if r["detected"] else "検証を通過（検出できない）"))
        for e in r["errors"]:
            print(f"     - {e}")
    last = results[-1]
    print(
        f"\n  シナリオ4 で掘り直したブロック数: {last['remined_blocks']}、"
        f"ハッシュ計算回数: {last['remine_attempts']:,}"
        f"（期待値 {last['remined_blocks']} × 16^{args.difficulty} = "
        f"{last['expected_attempts']:,}）"
    )

    unchanged = json.dumps(original.to_dict(), sort_keys=True) == before
    print(
        f"\n元のチェーンは変更されていないか: {'はい' if unchanged else 'いいえ'}"
        f"（検証: {'OK' if original.is_valid() else 'NG'}）"
    )
    print(CONCLUSION)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "difficulty": args.difficulty,
                "blocks": args.blocks,
                "target_block": TARGET,
                "original_valid": original.is_valid(),
                "original_unchanged": unchanged,
                "scenarios": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n結果を保存しました: {args.out}")
    return 0 if unchanged and original.is_valid() else 1


if __name__ == "__main__":
    raise SystemExit(main())
