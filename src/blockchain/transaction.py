"""汎用トランザクション。

payload には任意のJSONオブジェクトを入れられる。何を取引するかは未定なので、
送金・残高・署名・手数料（gas）は扱わない。
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Self

from blockchain.serialization import canonical_json, parse_fields, sha256_hex


def now_ms() -> int:
    """現在時刻をUnix時間（ミリ秒、整数）で返す。

    ハッシュ対象に浮動小数点数を入れると、言語や実装によって文字列表現が
    異なりうるため、時刻は整数で扱う。
    """
    return time.time_ns() // 1_000_000


@dataclass
class Transaction:
    """1件のトランザクション。

    transaction_id は内容（sender, recipient, payload, timestamp）のSHA-256。
    内容を1文字でも変えると transaction_id と一致しなくなるので、改ざんを検出できる。

    注意: Ethereum のトランザクションと違い電子署名がないため、
    sender は自己申告であり、誰でも任意の sender を名乗れる。
    """

    transaction_id: str
    sender: str
    recipient: str
    payload: dict[str, Any]
    timestamp: int  # Unix時間（ミリ秒）

    @classmethod
    def create(
        cls, sender: str, recipient: str, payload: dict[str, Any], timestamp: int | None = None
    ) -> Self:
        """内容から transaction_id を計算してトランザクションを作る。"""
        if not isinstance(payload, dict):
            raise TypeError("payload はJSONオブジェクト（dict）である必要があります")
        # JSONとして一度往復させ、タプル等を含まない純粋なJSON値にそろえる。
        # こうしておくと、保存→読み込み後もメモリ上と同じハッシュになる。
        normalized = json.loads(canonical_json(payload))
        tx = cls("", sender, recipient, normalized, now_ms() if timestamp is None else timestamp)
        tx.transaction_id = tx.compute_id()
        return tx

    def content(self) -> dict[str, Any]:
        """transaction_id の計算対象（transaction_id 自身は含めない）。"""
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def compute_id(self) -> str:
        return sha256_hex(canonical_json(self.content()))

    def to_dict(self) -> dict[str, Any]:
        return {"transaction_id": self.transaction_id, **self.content()}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        """JSONから復元する。形式が不正なら InvalidDataError。"""
        d = parse_fields(
            data,
            {
                "transaction_id": str,
                "sender": str,
                "recipient": str,
                "payload": dict,
                "timestamp": int,
            },
            "transaction",
        )
        return cls(d["transaction_id"], d["sender"], d["recipient"], d["payload"], d["timestamp"])
