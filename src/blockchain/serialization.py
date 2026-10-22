"""決定論的なシリアライズ、SHA-256、JSON読み込み時の型チェック。

ハッシュは「バイト列」に対して計算される。同じ内容のデータが常に同じバイト列に
なること（決定論的シリアライズ）が、ハッシュの再現性の前提になる。
"""

import hashlib
import json
from typing import Any


class InvalidDataError(ValueError):
    """JSONから読み込んだデータの形式が不正なときに送出する。"""


def canonical_json(obj: Any) -> str:
    """同じ内容なら常に同じ文字列になるJSONを返す。

    - sort_keys=True      : 辞書のキーの挿入順に依存しない
    - separators=(",",":"): 空白を入れない
    - ensure_ascii=False  : 日本語をそのまま出力する（ハッシュ時はUTF-8でバイト列化）
    - allow_nan=False     : NaN / Infinity はJSON標準外なので拒否する
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(text: str) -> str:
    """文字列をUTF-8でバイト列にし、SHA-256の16進数表記（64文字）を返す。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_fields(data: Any, schema: dict[str, type], name: str) -> dict[str, Any]:
    """JSONから読んだ辞書が schema（キー名 → 型）どおりかを検査する。

    キーの不足・余分なキー・型の違いがあれば InvalidDataError を送出する。
    余分なキーを黙って無視すると、ハッシュに含まれない情報が紛れ込むため拒否する。
    """
    if not isinstance(data, dict):
        raise InvalidDataError(f"{name} はJSONオブジェクトである必要があります")
    missing, extra = schema.keys() - data.keys(), data.keys() - schema.keys()
    if missing or extra:
        raise InvalidDataError(
            f"{name} のフィールドが不正です（不足: {sorted(missing)}, 余分: {sorted(extra)}）"
        )
    for key, expected in schema.items():
        value = data[key]
        # bool は int のサブクラスなので、int を期待する場所では明示的に除外する
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise InvalidDataError(
                f"{name}.{key} の型が不正です（期待: {expected.__name__}, "
                f"実際: {type(value).__name__}）"
            )
    return data
