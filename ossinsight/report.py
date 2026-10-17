"""Static PNG charts (matplotlib) for the README, reports and the CLI script."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .analysis import monthly_activity, resolution_buckets  # noqa: E402
from .charts import SERIES  # noqa: E402
from .pipeline import RepoBundle  # noqa: E402

INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"


def _slug(name: str) -> str:
    return name.replace("/", "__")


def _footer(fig, bundle: RepoBundle | None) -> None:
    if bundle is None:
        return
    if bundle.is_demo:
        text = "DEMO DATA - synthetic, not real GitHub data"
    else:
        text = f"Source: GitHub REST API - fetched {bundle.fetched_at:%Y-%m-%d}"
    fig.text(0.01, 0.01, text, fontsize=8, color=MUTED, ha="left", va="bottom")


def _style(ax, title: str, grid_axis: str = "y") -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold", pad=14)


def _new_fig(width: float = 8.5, height: float = 4.4, left: float = 0.08, right: float = 0.86):
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    fig.subplots_adjust(left=left, right=right, top=0.86, bottom=0.14)
    return fig, ax


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path


def _activity_png(monthly: pd.DataFrame, title: str, labels: tuple[str, str], path: Path, bundle) -> Path:
    fig, ax = _new_fig()
    _style(ax, title)
    for col, label, color in (("opened", labels[0], SERIES[0]), ("closed", labels[1], SERIES[1])):
        ax.plot(monthly["month"], monthly[col], color=color, linewidth=2.4, label=label)
        # direct label at the end of each line, in text colour (not series colour)
        ax.text(monthly["month"].iloc[-1], monthly[col].iloc[-1], "  " + label, color=MUTED,
                va="center", fontsize=9)
    ax.set_ylabel("Items per month", color=MUTED, fontsize=9)
    ax.set_ylim(bottom=0)
    # legend sits above the plot area so it never covers a line
    ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), fontsize=9,
              labelcolor=MUTED, ncol=2)
    _footer(fig, bundle)
    return _save(fig, path)


def _bar_png(labels, values, title: str, path: Path, bundle, colors=None, fmt="{:,.0f}",
             horizontal: bool = False, xlabel: str = "", axis_suffix: str = "") -> Path:
    # horizontal bars have long names on the left, so they need a wider left margin
    fig, ax = _new_fig(left=0.2 if horizontal else 0.08, right=0.9 if horizontal else 0.86)
    _style(ax, title, grid_axis="x" if horizontal else "y")
    if axis_suffix:
        formatter = FuncFormatter(lambda v, _: f"{v:g}{axis_suffix}")
        (ax.xaxis if horizontal else ax.yaxis).set_major_formatter(formatter)
    colors = colors or SERIES[0]
    if horizontal:
        bars = ax.barh(labels, values, color=colors, height=0.62)
        ax.invert_yaxis()
        ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    else:
        bars = ax.bar(labels, values, color=colors, width=0.62)
        ax.set_ylabel(xlabel, color=MUTED, fontsize=9)
    ax.bar_label(bars, labels=[fmt.format(v) for v in values], color=MUTED, fontsize=9, padding=4)
    ax.margins(y=0.12) if not horizontal else ax.margins(x=0.12)
    _footer(fig, bundle)
    return _save(fig, path)


def save_repo_charts(bundle: RepoBundle, out_dir: str | Path, prefix: str = "") -> list[Path]:
    """Write the standard set of PNG charts for one repository."""
    out = Path(out_dir)
    base = f"{prefix}{_slug(bundle.full_name)}"
    saved: list[Path] = []

    issues_m = monthly_activity(bundle.issues, "closed_at", bundle.issues_truncated)
    if not issues_m.empty:
        saved.append(_activity_png(issues_m, f"{bundle.full_name} - issues per month",
                                   ("Opened", "Closed"), out / f"{base}_issues_activity.png", bundle))

    pulls_m = monthly_activity(bundle.pulls, "merged_at", bundle.pulls_truncated)
    if not pulls_m.empty:
        saved.append(_activity_png(pulls_m, f"{bundle.full_name} - pull requests per month",
                                   ("Opened", "Merged"), out / f"{base}_pulls_activity.png", bundle))

    buckets = resolution_buckets(bundle.issues["resolution_days"])
    if buckets["count"].sum() > 0:
        saved.append(_bar_png(buckets["bucket"], buckets["count"],
                              f"{bundle.full_name} - how long issues took to close",
                              out / f"{base}_resolution.png", bundle, xlabel="Closed issues"))

    if not bundle.contributors.empty:
        top = bundle.contributors.head(10)
        saved.append(_bar_png(top["login"], top["contributions"],
                              f"{bundle.full_name} - top contributors (commits)",
                              out / f"{base}_contributors.png", bundle, horizontal=True, xlabel="Commits"))
    return saved


def save_comparison_chart(table: pd.DataFrame, column: str, title: str, path: str | Path,
                          bundles: list[RepoBundle] | None = None, percent: bool = False,
                          decimals: int = 1) -> Path:
    """One bar per repository, each repository keeps its own colour."""
    data = table.dropna(subset=[column])
    values = list(data[column] * 100) if percent else list(data[column])
    suffix = "%" if percent else ""
    colors = [SERIES[i % len(SERIES)] for i in range(len(data))]
    footer_bundle = bundles[0] if bundles else None
    return _bar_png(list(data["full_name"]), values, title, Path(path), footer_bundle, colors=colors,
                    fmt="{:,.%df}%s" % (decimals, suffix), axis_suffix=suffix)
