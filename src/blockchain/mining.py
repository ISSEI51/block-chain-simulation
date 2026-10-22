"""簡易 Proof of Work（PoW）。

条件: ブロックハッシュ（16進数64桁）の先頭に difficulty 個の '0' が並ぶこと。

16進数1桁は4ビットなので、この条件は「ハッシュを256ビット整数とみたとき
2^(256 - 4*difficulty) 未満」と同値。SHA-256 の出力が一様乱数のようにふるまうと
仮定すると、1回の試行で成功する確率は p = 16^(-difficulty)、
成功までの試行回数の期待値は 1/p = 16^difficulty になる。
"""

import time
from dataclasses import dataclass

from blockchain.block import Block, hash_header

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 64  # ハッシュは16進数64桁なので、これが理論上の上限


@dataclass(frozen=True)
class MiningResult:
    nonce: int
    hash: str
    attempts: int  # ハッシュ計算回数
    elapsed_seconds: float  # 採掘にかかった時間（秒）

    @property
    def hash_rate(self) -> float:
        """1秒あたりのハッシュ計算回数。"""
        return self.attempts / self.elapsed_seconds if self.elapsed_seconds > 0 else float("inf")


def meets_difficulty(block_hash: str, difficulty: int) -> bool:
    """ハッシュの先頭に difficulty 個の '0' が並んでいるか。"""
    return block_hash.startswith("0" * difficulty)


def check_difficulty(difficulty: int) -> None:
    if not MIN_DIFFICULTY <= difficulty <= MAX_DIFFICULTY:
        raise ValueError(
            f"difficulty は {MIN_DIFFICULTY}〜{MAX_DIFFICULTY} の整数で指定してください"
            f"（指定値: {difficulty}）"
        )


def mine(block: Block) -> MiningResult:
    """nonce を 0, 1, 2, ... と1ずつ増やし、PoW 条件を満たすハッシュを探す。

    見つかった nonce と hash を block に書き込み、計測結果を返す。
    nonce=0 から順に試すので、同じ内容のブロックなら試行回数は毎回同じになる
    （決定論的）。ばらつきはブロックの内容の違いから生じる。
    """
    header = block.header()  # トランザクションのハッシュはここで1回だけ計算する
    target_prefix = "0" * block.difficulty
    nonce = 0
    start = time.perf_counter()
    while True:
        header["nonce"] = nonce
        block_hash = hash_header(header)
        if block_hash.startswith(target_prefix):
            break
        nonce += 1
    elapsed = time.perf_counter() - start
    block.nonce, block.hash = nonce, block_hash
    return MiningResult(nonce=nonce, hash=block_hash, attempts=nonce + 1, elapsed_seconds=elapsed)
