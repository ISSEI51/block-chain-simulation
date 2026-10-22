"""JSON 保存・復元と、不正なデータの読み込み拒否。"""

import json
from pathlib import Path

import pytest
from conftest import make_tx

from blockchain import Blockchain, InvalidChainError, InvalidDataError

# ---- 保存・復元 ----


def test_save_and_load_roundtrip(chain, tmp_path: Path):
    chain.add_transaction(make_tx(99))  # 未承認トランザクションも保存される
    path = tmp_path / "chain.json"
    chain.save(path)
    loaded = Blockchain.load(path)
    assert loaded.to_dict() == chain.to_dict()
    assert loaded.difficulty == chain.difficulty
    assert [b.hash for b in loaded.chain] == [b.hash for b in chain.chain]
    assert loaded.is_valid()
    # 読み込んだチェーンにそのままブロックを追加できる
    loaded.mine_pending_transactions()
    assert loaded.is_valid()


def test_roundtrip_keeps_unicode_and_nested_payload(tmp_path: Path):
    c = Blockchain(difficulty=1)
    from blockchain import Transaction

    c.add_transaction(
        Transaction.create("太郎", "花子", {"本文": "日本語", "list": [1, {"a": None}]})
    )
    c.mine_pending_transactions()
    path = tmp_path / "chain.json"
    c.save(path)
    assert Blockchain.load(path).chain[1].hash == c.chain[1].hash


# ---- 不正なデータの読み込み拒否 ----


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_reject_broken_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidDataError, match="JSON"):
        Blockchain.load(path)


def test_reject_nan(tmp_path: Path, chain):
    data = chain.to_dict()
    data["chain"][1]["transactions"][0]["payload"]["v"] = float("nan")
    with pytest.raises(InvalidDataError, match="NaN"):
        Blockchain.load(write(tmp_path, data))


@pytest.mark.parametrize("data", [[], "chain", None, {}])
def test_reject_non_chain_top_level(tmp_path: Path, data):
    with pytest.raises(InvalidDataError):
        Blockchain.load(write(tmp_path, data))


def test_reject_empty_chain(tmp_path: Path):
    with pytest.raises(InvalidDataError, match="空"):
        Blockchain.load(write(tmp_path, {"difficulty": 2, "chain": [], "pending_transactions": []}))


def test_reject_missing_field(tmp_path: Path, chain):
    data = chain.to_dict()
    del data["chain"][1]["nonce"]
    with pytest.raises(InvalidDataError, match="不足"):
        Blockchain.load(write(tmp_path, data))


def test_reject_extra_field(tmp_path: Path, chain):
    data = chain.to_dict()
    data["chain"][1]["miner"] = "mallory"  # ハッシュに含まれない情報は受け付けない
    with pytest.raises(InvalidDataError, match="余分"):
        Blockchain.load(write(tmp_path, data))


@pytest.mark.parametrize(
    ("key", "value"),
    [("index", "1"), ("nonce", 1.5), ("nonce", True), ("hash", 123), ("transactions", {})],
)
def test_reject_wrong_type(tmp_path: Path, chain, key, value):
    data = chain.to_dict()
    data["chain"][1][key] = value
    with pytest.raises(InvalidDataError, match="型"):
        Blockchain.load(write(tmp_path, data))


def test_reject_non_object_payload(tmp_path: Path, chain):
    data = chain.to_dict()
    data["chain"][1]["transactions"][0]["payload"] = [1, 2, 3]
    with pytest.raises(InvalidDataError, match="payload"):
        Blockchain.load(write(tmp_path, data))


def test_reject_tampered_file(tmp_path: Path, chain):
    data = chain.to_dict()
    data["chain"][1]["transactions"][0]["payload"]["text"] = "tampered"
    with pytest.raises(InvalidChainError, match="検証に失敗"):
        Blockchain.load(write(tmp_path, data))
    # verify=False なら読み込めて、validate() で問題点を確認できる
    assert Blockchain.load(write(tmp_path, data), verify=False).validate()


def test_reject_invalid_difficulty_setting(tmp_path: Path, chain):
    data = chain.to_dict()
    data["difficulty"] = 0
    with pytest.raises(InvalidChainError, match="difficulty"):
        Blockchain.load(write(tmp_path, data))
