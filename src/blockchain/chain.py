"""ブロックチェーン本体：トランザクションの追加、採掘、検証、JSON保存・読み込み。"""

import json
from pathlib import Path
from typing import Any, Self

from blockchain.block import Block, create_genesis_block
from blockchain.mining import MiningResult, check_difficulty, meets_difficulty, mine
from blockchain.serialization import InvalidDataError, parse_fields
from blockchain.transaction import Transaction, now_ms

DEFAULT_DIFFICULTY = 3


class InvalidChainError(ValueError):
    """チェーンやブロックが検証に失敗したときに送出する。"""


def _reject_constant(name: str) -> Any:
    raise InvalidDataError(f"JSON標準外の値は使えません: {name}")


def validate_genesis(block: Block) -> list[str]:
    """Genesis Block は固定値なので、既定の Genesis Block と完全に一致するかで検証する。"""
    if block.to_dict() != create_genesis_block().to_dict():
        return ["ブロック#0: Genesis Block が既定の内容と一致しません"]
    return []


def validate_block(block: Block, previous: Block, position: int) -> list[str]:
    """position 番目のブロックを、1つ前のブロック previous と照らし合わせて検証する。

    戻り値はエラーメッセージのリスト（空なら正しい）。
    """
    p = f"ブロック#{position}"
    errors = []
    if block.index != previous.index + 1:
        errors.append(f"{p}: index={block.index} が連続していません（期待値 {previous.index + 1}）")
    if block.previous_hash != previous.hash:
        errors.append(f"{p}: previous_hash が前ブロックのハッシュと一致しません")
    if block.timestamp < previous.timestamp:
        errors.append(f"{p}: timestamp が前ブロックより過去です")
    try:
        check_difficulty(block.difficulty)
    except ValueError as e:
        errors.append(f"{p}: {e}")
    for tx in block.transactions:
        if tx.transaction_id != tx.compute_id():
            errors.append(
                f"{p}: トランザクション {tx.transaction_id[:12]}… の内容が "
                "transaction_id と一致しません"
            )
    if block.hash != block.compute_hash():
        errors.append(f"{p}: 保存された hash が内容から再計算した値と一致しません")
    elif not meets_difficulty(block.hash, block.difficulty):
        errors.append(f"{p}: hash が difficulty={block.difficulty} の PoW 条件を満たしません")
    return errors


class Blockchain:
    def __init__(self, difficulty: int = DEFAULT_DIFFICULTY) -> None:
        check_difficulty(difficulty)
        self.difficulty = difficulty  # 次に採掘するブロックの difficulty
        self.chain: list[Block] = [create_genesis_block()]
        self.pending_transactions: list[Transaction] = []  # まだブロックに入っていないもの

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def set_difficulty(self, difficulty: int) -> None:
        """difficulty を変更する。既存のブロックには影響せず、次のブロックから適用される。"""
        check_difficulty(difficulty)
        self.difficulty = difficulty

    def add_transaction(self, tx: Transaction) -> None:
        if tx.transaction_id != tx.compute_id():
            raise InvalidChainError("transaction_id が内容と一致しません")
        self.pending_transactions.append(tx)

    def mine_pending_transactions(self, timestamp: int | None = None) -> tuple[Block, MiningResult]:
        """未承認トランザクションをすべて新しいブロックに入れて採掘し、チェーンに追加する。"""
        last = self.last_block
        block = Block(
            index=last.index + 1,
            timestamp=max(now_ms() if timestamp is None else timestamp, last.timestamp),
            transactions=list(self.pending_transactions),
            previous_hash=last.hash,
            nonce=0,
            difficulty=self.difficulty,
            hash="",
        )
        result = mine(block)
        self.add_block(block)
        self.pending_transactions = []
        return block, result

    def add_block(self, block: Block) -> None:
        """ブロックを検証してから末尾に追加する。

        previous_hash が現在の最後のブロックの hash と一致しない場合などは
        InvalidChainError を送出し、チェーンは変更しない。
        """
        errors = validate_block(block, self.last_block, position=len(self.chain))
        if errors:
            raise InvalidChainError("; ".join(errors))
        self.chain.append(block)

    def validate(self) -> list[str]:
        """チェーン全体を検証し、エラーメッセージのリストを返す（空なら正しい）。"""
        if not self.chain:
            return ["チェーンが空です"]
        errors = validate_genesis(self.chain[0])
        for position in range(1, len(self.chain)):
            errors += validate_block(self.chain[position], self.chain[position - 1], position)
        for tx in self.pending_transactions:
            if tx.transaction_id != tx.compute_id():
                errors.append(
                    f"未承認トランザクション {tx.transaction_id[:12]}… が改ざんされています"
                )
        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    # ---- JSON 保存・読み込み ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "difficulty": self.difficulty,
            "chain": [b.to_dict() for b in self.chain],
            "pending_transactions": [tx.to_dict() for tx in self.pending_transactions],
        }

    @classmethod
    def from_dict(cls, data: Any, verify: bool = True) -> Self:
        """辞書から復元する。

        形式が不正なら InvalidDataError、verify=True で内容の検証に失敗したら
        InvalidChainError を送出する。verify=False は検証コマンドや改ざん実験で使う。
        """
        d = parse_fields(
            data, {"difficulty": int, "chain": list, "pending_transactions": list}, "blockchain"
        )
        if not d["chain"]:
            raise InvalidDataError("chain が空です（Genesis Block が必要）")
        obj = cls()
        obj.difficulty = d["difficulty"]
        obj.chain = [Block.from_dict(b) for b in d["chain"]]
        obj.pending_transactions = [Transaction.from_dict(t) for t in d["pending_transactions"]]
        if verify:
            try:
                check_difficulty(obj.difficulty)
            except ValueError as e:
                raise InvalidChainError(str(e)) from e
            errors = obj.validate()
            if errors:
                raise InvalidChainError("チェーンの検証に失敗しました: " + "; ".join(errors))
        return obj

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path, verify: bool = True) -> Self:
        try:
            # NaN / Infinity はJSON標準外なので読み込み時点で拒否する
            data = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
        except json.JSONDecodeError as e:
            raise InvalidDataError(f"JSONとして読み込めません: {e}") from e
        return cls.from_dict(data, verify=verify)
