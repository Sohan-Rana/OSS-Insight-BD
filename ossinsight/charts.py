"""Interactive Plotly charts used by the Streamlit dashboard.

Colours follow a fixed categorical order (blue, orange, aqua). Colour belongs to
the entity (a repository keeps its colour), never to its rank. Comparisons are
limited to three repositories so these colours always stay easy to tell apart.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slots 1-3
GRID = "rgba(128,128,128,0.22)"
MUTED = "#898781"


def _layout(fig: go.Figure, title: str, height: int = 380, legend: bool = False) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=16)),
        height=height,
        margin=dict(l=10, r=10, t=64, b=10),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def _no_data(title: str, message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color=MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _layout(fig, title, height=260)


def activity_chart(monthly: pd.DataFrame, title: str, opened: str = "Opened", closed: str = "Closed") -> go.Figure:
    if monthly.empty:
        return _no_data(title)
    fig = go.Figure()
    for col, label, color in (("opened", opened, SERIES[0]), ("closed", closed, SERIES[1])):
        fig.add_trace(
            go.Scatter(
                x=monthly["month"],
                y=monthly[col],
                name=label,
                mode="lines",
                line=dict(color=color, width=2.5),
                hovertemplate="%{y}<extra>" + label + "</extra>",
            )
        )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(tickformat="%b %Y")
    fig.update_yaxes(title_text="Items per month", rangemode="tozero")
    return _layout(fig, title, legend=True)


def resolution_chart(buckets: pd.DataFrame, title: str) -> go.Figure:
    if buckets.empty or buckets["count"].sum() == 0:
        return _no_data(title, "No closed items in this sample")
    fig = go.Figure(
        go.Bar(
            x=buckets["bucket"],
            y=buckets["count"],
            marker_color=SERIES[0],
            text=[f"{s:.0%}" for s in buckets["share"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y} items<extra></extra>",
        )
    )
    fig.update_yaxes(title_text="Closed items", rangemode="tozero")
    return _layout(fig, title)


def contributors_chart(contributors: pd.DataFrame, title: str, top_n: int = 10) -> go.Figure:
    if contributors.empty:
        return _no_data(title, "Contributor data unavailable")
    top = contributors.head(top_n)
    fig = go.Figure(
        go.Bar(
            x=top["contributions"],
            y=top["login"],
            orientation="h",
            marker_color=SERIES[0],
            text=top["contributions"],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x} commits<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(title_text="Commits", showgrid=True, gridcolor=GRID)
    return _layout(fig, title, height=max(300, 34 * len(top) + 110))


def languages_chart(languages: dict, title: str, top_n: int = 6) -> go.Figure:
    total = sum(languages.values())
    if not total:
        return _no_data(title, "Language data unavailable")
    items = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    names = [k for k, _ in items]
    shares = [v / total for _, v in items]
    fig = go.Figure(
        go.Bar(
            x=shares,
            y=names,
            orientation="h",
            marker_color=SERIES[0],
            text=[f"{s:.1%}" for s in shares],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:.1%}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=GRID, range=[0, max(shares) * 1.2])
    return _layout(fig, title, height=max(260, 40 * len(names) + 110))


def compare_chart(table: pd.DataFrame, column: str, title: str, percent: bool = False, decimals: int = 1) -> go.Figure:
    """One bar per repository; each repository keeps its own colour."""
    data = table.dropna(subset=[column])
    if data.empty:
        return _no_data(title)
    values = data[column] * 100 if percent else data[column]
    suffix = "%" if percent else ""
    fig = go.Figure(
        go.Bar(
            x=data["full_name"],
            y=values,
            marker_color=[SERIES[i % len(SERIES)] for i in range(len(data))],
            text=[f"{v:,.{decimals}f}{suffix}" for v in values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y:,." + str(decimals) + "f}" + suffix + "<extra></extra>",
        )
    )
    fig.update_yaxes(rangemode="tozero")
    return _layout(fig, title, height=340)
