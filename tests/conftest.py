import pytest

from blockchain import Blockchain, Transaction


def make_tx(seq: int = 0) -> Transaction:
    return Transaction.create("alice", "bob", {"text": "hello", "seq": seq}, timestamp=1_000 + seq)


@pytest.fixture
def chain() -> Blockchain:
    """difficulty=2 で3ブロック（Genesis + 2）を持つチェーン。テストを速くするため低難易度。"""
    c = Blockchain(difficulty=2)
    for i in range(2):
        c.add_transaction(make_tx(2 * i))
        c.add_transaction(make_tx(2 * i + 1))
        c.mine_pending_transactions(timestamp=10_000 + i)
    return c
