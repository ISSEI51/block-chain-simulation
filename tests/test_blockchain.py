import copy
import hashlib

import pytest
from conftest import make_tx

from blockchain import (
    Block,
    Blockchain,
    InvalidChainError,
    Transaction,
    canonical_json,
    create_genesis_block,
    meets_difficulty,
    mine,
)
from blockchain.block import GENESIS_PREVIOUS_HASH

# ---- Genesis Block ----


def test_genesis_block_is_fixed_and_deterministic():
    g = create_genesis_block()
    assert g.index == 0
    assert g.previous_hash == GENESIS_PREVIOUS_HASH
    assert g.transactions == []
    assert g.hash == g.compute_hash()
    # どの環境で作っても同じ Genesis Block になる
    assert create_genesis_block().to_dict() == g.to_dict()
    assert Blockchain().chain[0].hash == Blockchain(difficulty=5).chain[0].hash


def test_new_chain_has_only_genesis_and_is_valid():
    c = Blockchain()
    assert len(c.chain) == 1
    assert c.validate() == []


def test_altered_genesis_is_detected():
    c = Blockchain(difficulty=1)
    c.chain[0].timestamp = 123
    c.chain[0].hash = c.chain[0].compute_hash()  # ハッシュを再計算しても Genesis としては不正
    assert any("Genesis" in e for e in c.validate())


# ---- ブロック追加 ----


def test_mine_adds_linked_block_and_clears_pending():
    c = Blockchain(difficulty=2)
    c.add_transaction(make_tx(0))
    block, result = c.mine_pending_transactions()
    assert len(c.chain) == 2
    assert block.index == 1
    assert block.previous_hash == c.chain[0].hash
    assert block.transactions[0].payload["text"] == "hello"
    assert c.pending_transactions == []
    assert result.attempts == block.nonce + 1
    assert c.is_valid()


def test_add_block_rejects_wrong_index(chain):
    block = Block(
        index=99,
        timestamp=20_000,
        transactions=[],
        previous_hash=chain.last_block.hash,
        nonce=0,
        difficulty=1,
        hash="",
    )
    mine(block)
    with pytest.raises(InvalidChainError, match="index"):
        chain.add_block(block)


# ---- previous_hash の不一致 ----


def test_add_block_rejects_previous_hash_mismatch(chain):
    block = Block(
        index=len(chain.chain),
        timestamp=20_000,
        transactions=[],
        previous_hash="f" * 64,
        nonce=0,
        difficulty=1,
        hash="",
    )
    mine(block)  # PoW は正しく満たしていても、つながりが正しくなければ拒否する
    before = len(chain.chain)
    with pytest.raises(InvalidChainError, match="previous_hash"):
        chain.add_block(block)
    assert len(chain.chain) == before  # チェーンは変更されない


def test_validate_detects_broken_link(chain):
    chain.chain[2].previous_hash = "0" * 64
    mine(chain.chain[2])  # PoW をやり直しても、前ブロックとのつながりは壊れたまま
    errors = chain.validate()
    assert len(errors) == 1
    assert "ブロック#2" in errors[0] and "previous_hash" in errors[0]


# ---- ハッシュ計算の再現性 ----


def test_hash_is_reproducible(chain):
    block = chain.chain[1]
    assert block.compute_hash() == block.compute_hash() == block.hash
    clone = Block.from_dict(copy.deepcopy(block.to_dict()))
    assert clone.compute_hash() == block.hash


def test_hash_does_not_depend_on_dict_key_order():
    a = Transaction.create("s", "r", {"x": 1, "y": {"b": 2, "a": 1}}, timestamp=0)
    b = Transaction.create("s", "r", {"y": {"a": 1, "b": 2}, "x": 1}, timestamp=0)
    assert a.transaction_id == b.transaction_id


def test_any_field_change_changes_hash(chain):
    block = chain.chain[1]
    original = block.compute_hash()
    for field, value in [
        ("index", 5),
        ("timestamp", 1),
        ("nonce", block.nonce + 1),
        ("difficulty", 9),
        ("previous_hash", "1" * 64),
    ]:
        changed = copy.deepcopy(block)
        setattr(changed, field, value)
        assert changed.compute_hash() != original, field


def test_canonical_serialization_is_exact():
    """ハッシュ対象のバイト列を文字列で固定し、シリアライズ方法の意図しない変更を検出する。"""
    tx = Transaction.create("alice", "bob", {"text": "hello"}, timestamp=0)
    expected = '{"payload":{"text":"hello"},"recipient":"bob","sender":"alice","timestamp":0}'
    assert canonical_json(tx.content()) == expected
    assert tx.transaction_id == hashlib.sha256(expected.encode("utf-8")).hexdigest()


def test_genesis_hash_known_value():
    assert create_genesis_block().hash == (
        "7492d36950ffb1940a217580e56cd0ba6eac733e0ebb826dd2f4914f9188555f"
    )


# ---- PoW の成立 ----


@pytest.mark.parametrize("difficulty", [1, 2, 3])
def test_pow_meets_difficulty(difficulty):
    block = Block(
        index=1,
        timestamp=0,
        transactions=[make_tx()],
        previous_hash=create_genesis_block().hash,
        nonce=0,
        difficulty=difficulty,
        hash="",
    )
    result = mine(block)
    assert block.hash.startswith("0" * difficulty)
    assert block.hash == block.compute_hash() == result.hash
    assert result.attempts == result.nonce + 1
    # 見つかった nonce より小さい nonce はすべて条件を満たさない（最初の解である）
    for n in range(result.nonce):
        block.nonce = n
        assert not meets_difficulty(block.compute_hash(), difficulty)


def test_meets_difficulty():
    assert meets_difficulty("000abc", 3)
    assert not meets_difficulty("00abc0", 3)


@pytest.mark.parametrize("bad", [0, -1, 65])
def test_invalid_difficulty_is_rejected(bad):
    with pytest.raises(ValueError):
        Blockchain(difficulty=bad)
    with pytest.raises(ValueError):
        Blockchain().set_difficulty(bad)


def test_difficulty_change_applies_to_next_block_only(chain):
    chain.set_difficulty(3)
    block, _ = chain.mine_pending_transactions()
    assert [b.difficulty for b in chain.chain] == [0, 2, 2, 3]
    assert block.hash.startswith("000")
    assert chain.is_valid()


# ---- 改ざんの検知 ----


def test_tampered_payload_is_detected(chain):
    tampered = copy.deepcopy(chain)
    tampered.chain[1].transactions[0].payload["text"] = "tampered"
    errors = tampered.validate()
    assert any("transaction_id" in e for e in errors)
    assert any("hash が内容から再計算した値と一致しません" in e for e in errors)
    assert chain.is_valid()  # コピーなので元のチェーンは壊れていない


def test_rehash_without_pow_is_detected(chain):
    tampered = copy.deepcopy(chain)
    block = tampered.chain[1]
    block.transactions[0].payload["text"] = "tampered"
    block.transactions[0].transaction_id = block.transactions[0].compute_id()
    block.nonce = 0
    block.hash = block.compute_hash()
    # 内容とハッシュは整合するが、PoW を満たさず、次のブロックとのつながりも切れる
    # （fixture の内容は固定なので結果は決定論的）
    assert tampered.validate() == [
        "ブロック#1: hash が difficulty=2 の PoW 条件を満たしません",
        "ブロック#2: previous_hash が前ブロックのハッシュと一致しません",
    ]


def test_tampered_pending_transaction_is_detected():
    c = Blockchain(difficulty=1)
    c.add_transaction(make_tx())
    c.pending_transactions[0].recipient = "mallory"
    assert any("未承認" in e for e in c.validate())


def test_add_transaction_rejects_inconsistent_id():
    tx = make_tx()
    tx.payload["text"] = "changed"
    with pytest.raises(InvalidChainError):
        Blockchain().add_transaction(tx)


def test_payload_must_be_object():
    with pytest.raises(TypeError):
        Transaction.create("a", "b", ["not", "object"], timestamp=0)  # type: ignore[arg-type]
