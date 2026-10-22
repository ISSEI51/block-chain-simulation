"""CLI の一連の操作が動くことを確認する。"""

import json
from pathlib import Path

import pytest

from blockchain.cli import main


def run(path: Path, *args: str) -> int:
    return main(["--file", str(path), *args])


def test_cli_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = tmp_path / "chain.json"
    assert run(path, "init", "--difficulty", "1") == 0
    assert run(path, "init") == 1  # 既存ファイルは --force なしでは上書きしない
    assert run(path, "add-sample", "--count", "2") == 0
    assert run(path, "add-tx", "--sender", "a", "--recipient", "b", "--payload", '{"k": 1}') == 0
    assert run(path, "mine") == 0
    assert run(path, "set-difficulty", "2") == 0
    assert run(path, "mine") == 0
    assert run(path, "show") == 0
    assert run(path, "validate") == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [b["difficulty"] for b in data["chain"]] == [0, 1, 2]
    assert len(data["chain"][1]["transactions"]) == 3

    capsys.readouterr()
    assert run(path, "show", "--json") == 0
    assert json.loads(capsys.readouterr().out) == data


def test_cli_validate_reports_tampering(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = tmp_path / "chain.json"
    run(path, "init", "--difficulty", "1")
    run(path, "add-sample", "--count", "1")
    run(path, "mine")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["chain"][1]["transactions"][0]["recipient"] = "mallory"
    path.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    assert run(path, "validate") == 1
    assert "NG" in capsys.readouterr().out
    assert run(path, "mine") == 1  # 不正なチェーンには追加できない


def test_cli_errors(tmp_path: Path):
    path = tmp_path / "chain.json"
    assert run(path, "show") == 1  # ファイルがない
    run(path, "init", "--difficulty", "1")
    assert run(path, "set-difficulty", "0") == 1
    assert run(path, "add-tx", "--sender", "a", "--recipient", "b", "--payload", "[1]") == 1
    assert run(path, "add-tx", "--sender", "a", "--recipient", "b", "--payload", "{bad") == 1


def test_cli_simulate(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    out = tmp_path / "sim.json"
    assert main(["simulate", "--blocks", "3", "--difficulty", "1", "--save", str(out)]) == 0
    assert "検証結果: OK" in capsys.readouterr().out
    assert len(json.loads(out.read_text(encoding="utf-8"))["chain"]) == 4
