"""実験スクリプトが小さな設定で最後まで動き、期待どおりの結果を出すことを確認する。"""

import csv
import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "experiments" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pow_benchmark_small(tmp_path: Path):
    bench = load("pow_benchmark")
    args = [
        "--max-difficulty",
        "2",
        "--runs",
        "5",
        "--hist-runs",
        "20",
        "--no-plot",
        "--out-dir",
        str(tmp_path),
    ]
    assert bench.main(args) == 0
    with (tmp_path / "pow_benchmark_trials.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10
    summary = json.loads((tmp_path / "pow_benchmark_summary.json").read_text(encoding="utf-8"))
    assert [s["theory_attempts"] for s in summary["summary"]] == [16, 256]

    # ハッシュ計算回数は決定論的（同じ設定なら毎回同じ）
    first = [r["attempts"] for r in rows]
    assert bench.main(args) == 0
    with (tmp_path / "pow_benchmark_trials.csv").open(encoding="utf-8") as f:
        assert [r["attempts"] for r in csv.DictReader(f)] == first


def test_tampering_demo(tmp_path: Path):
    demo = load("tampering_demo")
    out = tmp_path / "tampering.json"
    assert demo.main(["--difficulty", "2", "--blocks", "4", "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert [s["detected"] for s in result["scenarios"]] == [True, True, True, False]
    assert result["original_valid"] and result["original_unchanged"]
