"""ブロックとブロックハッシュの計算。

ブロックハッシュ = SHA-256( 正規化JSON(ヘッダ) )
ヘッダ = index, timestamp, transactions_hash, previous_hash, nonce, difficulty

トランザクション本体はヘッダに直接入れず、その一覧のハッシュ（transactions_hash）を
ヘッダに入れる。Ethereum がヘッダに transactionsRoot（H_t）を持つのと同じ考え方だが、
本実装は Merkle Patricia Trie ではなく一覧全体の単純なSHA-256を使う。
"""

from dataclasses import dataclass
from typing import Any, Self

from blockchain.serialization import canonical_json, parse_fields, sha256_hex
from blockchain.transaction import Transaction

GENESIS_PREVIOUS_HASH = "0" * 64
GENESIS_TIMESTAMP = 0  # 決定論的にするため固定値（どの環境でも同じ Genesis Block になる）


def transactions_hash(transactions: list[Transaction]) -> str:
    """トランザクション一覧全体のSHA-256。1件でも内容や順序が変わると値が変わる。"""
    return sha256_hex(canonical_json([tx.to_dict() for tx in transactions]))


def hash_header(header: dict[str, Any]) -> str:
    """ヘッダ（辞書）のSHA-256。採掘ループからも直接呼ぶ。"""
    return sha256_hex(canonical_json(header))


@dataclass
class Block:
    index: int
    timestamp: int  # Unix時間（ミリ秒）
    transactions: list[Transaction]
    previous_hash: str  # 1つ前のブロックの hash。これでブロック同士が鎖状につながる
    nonce: int  # PoW で変化させる値
    difficulty: int  # ハッシュ先頭に必要な16進数の '0' の個数
    hash: str  # このブロックのハッシュ（採掘後に確定する）

    def header(self) -> dict[str, Any]:
        """ハッシュ計算の対象。hash 自身は含めない。"""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions_hash": transactions_hash(self.transactions),
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
        }

    def compute_hash(self) -> str:
        """現在の内容からハッシュを再計算する。保存された hash との比較で改ざんを検出する。"""
        return hash_header(self.header())

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        """JSONから復元する。形式が不正なら InvalidDataError（内容の正しさは chain で検証）。"""
        d = parse_fields(
            data,
            {
                "index": int,
                "timestamp": int,
                "transactions": list,
                "previous_hash": str,
                "nonce": int,
                "difficulty": int,
                "hash": str,
            },
            "block",
        )
        return cls(
            index=d["index"],
            timestamp=d["timestamp"],
            transactions=[Transaction.from_dict(t) for t in d["transactions"]],
            previous_hash=d["previous_hash"],
            nonce=d["nonce"],
            difficulty=d["difficulty"],
            hash=d["hash"],
        )


def create_genesis_block() -> Block:
    """Genesis Block（最初のブロック）を作る。

    Genesis Block は採掘しない特別なブロックで、内容はすべて固定値。
    そのため、どの環境で作っても同じハッシュになる。検証時はこの関数の
    戻り値と完全に一致するかどうかで確認する。
    """
    block = Block(
        index=0,
        timestamp=GENESIS_TIMESTAMP,
        transactions=[],
        previous_hash=GENESIS_PREVIOUS_HASH,
        nonce=0,
        difficulty=0,
        hash="",
    )
    block.hash = block.compute_hash()
    return block
