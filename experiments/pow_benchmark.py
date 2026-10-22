"""実験1: PoW の difficulty と計算量（ハッシュ計算回数・採掘時間）の関係。

difficulty = 1〜5 のそれぞれで runs 回ブロックを採掘し、平均値を理論値 16^difficulty と比べる。
あわせて、ある difficulty で多数回採掘し、試行回数の分布を幾何分布と比べる。

再現性: ブロックの内容（timestamp を含む）は固定し、試行ごとに payload の trial 番号だけを
変える。nonce は 0 から順に試すので、ハッシュ計算回数は何度実行しても同じ値になる。
実行環境に依存して変わるのは時間だけである。

実行例:
    uv run python experiments/pow_benchmark.py              # 既定（各 difficulty 30 回）
    uv run python experiments/pow_benchmark.py --runs 100   # 回数を増やす
"""

import argparse
import csv
import json
import math
import platform
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from blockchain import Block, Transaction, create_genesis_block, mine

FIXED_TIMESTAMP = 1_700_000_000_000  # 再現性のためブロック内容の時刻を固定（ミリ秒）
ROOT = Path(__file__).resolve().parent.parent

# グラフの色（実測 = 青、理論 = 橙。色覚多様性に配慮して検証済みの2色）
MEASURED = "#2a78d6"
THEORY = "#eb6834"
INK, INK_2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


@dataclass(frozen=True)
class Trial:
    difficulty: int
    trial: int
    attempts: int  # ハッシュ計算回数（= 見つかった nonce + 1）
    seconds: float


def make_block(difficulty: int, trial: int, seed: int, tag: str) -> Block:
    """実験用のブロックを作る。trial 番号が違えばハッシュの列はまったく別物になる。"""
    payload = {"experiment": tag, "seed": seed, "difficulty": difficulty, "trial": trial}
    tx = Transaction.create("experiment", "chain", payload, timestamp=FIXED_TIMESTAMP)
    return Block(
        index=1,
        timestamp=FIXED_TIMESTAMP,
        transactions=[tx],
        previous_hash=create_genesis_block().hash,
        nonce=0,
        difficulty=difficulty,
        hash="",
    )


def run_trials(difficulty: int, runs: int, seed: int, tag: str) -> list[Trial]:
    trials = []
    for t in range(runs):
        result = mine(make_block(difficulty, t, seed, tag))
        trials.append(Trial(difficulty, t, result.attempts, result.elapsed_seconds))
    return trials


def summarize(trials: list[Trial]) -> dict[str, Any]:
    """平均・標準偏差などを計算し、理論値（幾何分布）と比べる。

    1回の成功確率 p = 16^(-d) のとき、成功までの試行回数は幾何分布に従い
        期待値 = 1/p = 16^d,   標準偏差 = sqrt(1-p)/p ≒ 16^d
    つまり標準偏差が平均とほぼ同じ大きさになるため、ばらつきが大きい。
    n 回の平均の標準誤差は 標準偏差/sqrt(n) なので、平均の相対誤差はおよそ 1/sqrt(n)。
    また右に裾の長い分布なので、中央値（≒ ln2 × 16^d）は平均より小さい。
    """
    d = trials[0].difficulty
    n = len(trials)
    attempts = [t.attempts for t in trials]
    seconds = [t.seconds for t in trials]
    p = 16.0**-d
    theory_mean = 16**d
    theory_std = math.sqrt(1 - p) / p
    mean = statistics.fmean(attempts)
    std = statistics.stdev(attempts) if n > 1 else 0.0
    return {
        "difficulty": d,
        "runs": n,
        "mean_attempts": mean,
        "std_attempts": std,
        "sem_attempts": std / math.sqrt(n),
        "min_attempts": min(attempts),
        "max_attempts": max(attempts),
        "theory_attempts": theory_mean,
        "theory_std_attempts": theory_std,
        "ratio_to_theory": mean / theory_mean,
        "median_attempts": statistics.median(attempts),
        # 幾何分布の中央値: P(K <= k) >= 1/2 となる最小の k
        "theory_median_attempts": math.ceil(-math.log(2) / math.log1p(-p)),
        # 理論値からのずれが「理論上の標準誤差」の何倍か（|z| < 2 なら理論と矛盾しない目安）
        "z_score": (mean - theory_mean) / (theory_std / math.sqrt(n)),
        "mean_seconds": statistics.fmean(seconds),
        "std_seconds": statistics.stdev(seconds) if n > 1 else 0.0,
        "hash_rate": sum(attempts) / sum(seconds),
    }


def display_path(path: Path) -> str:
    """結果ファイルに記録するパス。リポジトリ内なら相対パスにする（個人のディレクトリ名を残さない）。"""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(summary: list[dict[str, Any]]) -> str:
    lines = [
        "| difficulty | 回数 | 平均試行回数 | 標準偏差 | 理論値 16^d | 平均/理論 | z "
        "| 中央値 | 理論中央値 | 平均時間 [ms] |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summary:
        lines.append(
            f"| {s['difficulty']} | {s['runs']} | {s['mean_attempts']:,.1f} | "
            f"{s['std_attempts']:,.1f} | {s['theory_attempts']:,} | {s['ratio_to_theory']:.3f} | "
            f"{s['z_score']:+.2f} | {s['median_attempts']:,.0f} | "
            f"{s['theory_median_attempts']:,.0f} | {s['mean_seconds'] * 1000:,.4g} |"
        )
    return "\n".join(lines)


# ---- グラフ（matplotlib がある場合のみ） ----


def plot_all(
    trials: list[Trial], summary: list[dict[str, Any]], hist: list[Trial], fig_dir: Path
) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    plt.rcParams.update(
        {
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
        }
    )
    fig_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    def save(fig: Any, name: str) -> None:
        for ext in ("png", "pdf"):
            path = fig_dir / f"{name}.{ext}"
            fig.savefig(path)
            saved.append(path)
        plt.close(fig)

    ds = [s["difficulty"] for s in summary]
    hash_rate = sum(t.attempts for t in trials) / sum(t.seconds for t in trials)
    smooth = [min(ds) + i / 50 * (max(ds) - min(ds)) for i in range(51)]

    # 図1・図2: 試行回数と時間（個々の試行を薄い点、平均±標準誤差を濃い点で表示）
    for name, key, ylabel, theory, theory_label in [
        (
            "pow_attempts",
            "attempts",
            "Hash computations until success",
            [16**x for x in smooth],
            r"Theory $16^d$",
        ),
        (
            "pow_time",
            "seconds",
            "Mining time [s]",
            [16**x / hash_rate for x in smooth],
            rf"Theory $16^d / R$  ($R$ = {hash_rate:,.0f} H/s)",
        ),
    ]:
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        for s in summary:
            values = [getattr(t, key) for t in trials if t.difficulty == s["difficulty"]]
            jitter = [s["difficulty"] + 0.18 * ((i % 7) - 3) / 3 for i in range(len(values))]
            ax.scatter(
                jitter,
                values,
                s=9,
                color=MEASURED,
                alpha=0.25,
                linewidths=0,
                label="Individual trials" if s is summary[0] else None,
            )
        means = [s[f"mean_{key}"] for s in summary]
        sems = [s[f"std_{key}"] / math.sqrt(s["runs"]) for s in summary]
        ax.plot(
            smooth,
            theory,
            color=THEORY,
            linewidth=1.5,
            label=theory_label,
            zorder=2,
        )
        ax.errorbar(
            ds,
            means,
            yerr=sems,
            fmt="o",
            color=MEASURED,
            markersize=6,
            markeredgecolor="white",
            markeredgewidth=1.2,
            elinewidth=1.5,
            capsize=3,
            label=f"Mean ± standard error (n = {summary[0]['runs']})",
            zorder=3,
        )
        ax.set_yscale("log")
        ax.set_xticks(ds)
        ax.set_xlabel("Difficulty $d$ (number of leading hex zeros)")
        ax.set_ylabel(ylabel)
        ax.legend(loc="upper left", fontsize=8.5)
        save(fig, name)

    # 図3: 試行回数の分布と幾何分布の比較（左: 線形軸、右: 片対数軸）
    if hist:
        d = hist[0].difficulty
        p = 16.0**-d
        n = len(hist)
        attempts = [t.attempts for t in hist]
        width = 16**d // 8
        edges = list(range(0, max(attempts) + width, width))
        # 区間 (a, b] に入る理論上の件数 = n * [(1-p)^a - (1-p)^b]
        expected = [
            n * ((1 - p) ** a - (1 - p) ** b) for a, b in zip(edges, edges[1:], strict=False)
        ]
        centers = [(a + b) / 2 for a, b in zip(edges, edges[1:], strict=False)]
        bins = [e + 0.5 for e in edges]  # 整数 a+1..b が同じ区間に入るよう境界を0.5ずらす
        fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6))
        for ax, log in zip(axes, (False, True), strict=True):
            ax.hist(
                attempts,
                bins=bins,
                color=MEASURED,
                alpha=0.85,
                edgecolor="white",
                linewidth=0.8,
                label=f"Measured (n = {n})",
            )
            ax.plot(
                centers,
                expected,
                color=THEORY,
                linewidth=2,
                label=rf"Geometric distribution, $p = 16^{{-{d}}}$",
            )
            ax.axvline(statistics.fmean(attempts), color=INK_2, linewidth=1)
            ax.annotate(
                f"mean = {statistics.fmean(attempts):,.0f}\n(theory {16**d:,})",
                xy=(statistics.fmean(attempts), 0.97),
                xycoords=("data", "axes fraction"),
                xytext=(6, 0),
                textcoords="offset points",
                va="top",
                fontsize=8.5,
                color=INK_2,
            )
            ax.set_xlabel(f"Hash computations until success (d = {d})")
            ax.set_ylabel("Number of trials" + (" (log scale)" if log else ""))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))
            if log:
                ax.set_yscale("log")
                ax.set_ylim(
                    bottom=0.5
                )  # 1件未満は描かない（理論曲線は期待値なので1未満もありうる）
        axes[0].legend(loc="center right", fontsize=8.5)
        save(fig, "pow_histogram")
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--min-difficulty", type=int, default=1)
    parser.add_argument("--max-difficulty", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30, help="各 difficulty での採掘回数")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="ブロック内容に含める標本番号。変えると別の標本で実験できる",
    )
    parser.add_argument("--hist-difficulty", type=int, default=3)
    parser.add_argument("--hist-runs", type=int, default=2000, help="0 で分布の実験を省略")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "results")
    parser.add_argument("--fig-dir", type=Path, default=ROOT / "docs" / "figures")
    parser.add_argument("--no-plot", action="store_true", help="グラフを作らない")
    args = parser.parse_args(argv)

    trials: list[Trial] = []
    summary = []
    for d in range(args.min_difficulty, args.max_difficulty + 1):
        rows = run_trials(d, args.runs, args.seed, "pow_benchmark")
        trials += rows
        summary.append(summarize(rows))
        s = summary[-1]
        print(
            f"difficulty={d}: 平均 {s['mean_attempts']:,.1f} 回（理論 {16**d:,}）、"
            f"平均 {s['mean_seconds'] * 1000:,.4g} ミリ秒",
            flush=True,
        )

    hist = run_trials(args.hist_difficulty, args.hist_runs, args.seed, "pow_histogram")
    if hist:
        h = summarize(hist)
        print(
            f"分布の実験 difficulty={args.hist_difficulty} × {args.hist_runs} 回: "
            f"平均 {h['mean_attempts']:,.1f}（理論 {h['theory_attempts']:,}）、"
            f"標準偏差 {h['std_attempts']:,.1f}（理論 {h['theory_std_attempts']:,.1f}）"
        )

    out = args.out_dir
    write_csv(out / "pow_benchmark_trials.csv", [asdict(t) for t in trials])
    write_csv(out / "pow_benchmark_summary.csv", summary)
    if hist:
        write_csv(out / "pow_histogram_trials.csv", [asdict(t) for t in hist])
    meta = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "args": {k: display_path(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "summary": summary,
        "histogram": summarize(hist) if hist else None,
    }
    (out / "pow_benchmark_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("\n" + markdown_table(summary))
    print(f"\n結果を保存しました: {out}")

    if not args.no_plot:
        try:
            saved = plot_all(trials, summary, hist, args.fig_dir)
        except ImportError:
            print("matplotlib がないためグラフは作りません（uv sync --extra plot で導入）")
        else:
            print("グラフを保存しました: " + ", ".join(str(p) for p in saved if p.suffix == ".png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
