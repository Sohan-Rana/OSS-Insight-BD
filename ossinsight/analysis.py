"""Turn raw GitHub API data into clean DataFrames and summary metrics."""
from __future__ import annotations

import pandas as pd

ISSUE_COLS = ["number", "title", "state", "created_at", "closed_at", "comments", "author", "labels"]
PR_COLS = ["number", "title", "state", "created_at", "closed_at", "merged_at", "author", "draft"]

BUCKET_EDGES = [0, 1, 3, 7, 14, 30, 90, float("inf")]
BUCKET_LABELS = [
    "< 1 day", "1-3 days", "3-7 days", "1-2 weeks", "2-4 weeks", "1-3 months", "> 3 months",
]


# ------------------------------------------------------------ raw -> DataFrame
def _to_datetime(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def issues_to_df(raw: list[dict]) -> pd.DataFrame:
    rows = [
        {
            "number": i.get("number"),
            "title": i.get("title", ""),
            "state": i.get("state"),
            "created_at": i.get("created_at"),
            "closed_at": i.get("closed_at"),
            "comments": i.get("comments", 0),
            "author": (i.get("user") or {}).get("login", "ghost"),
            "labels": ", ".join(
                lbl.get("name", "") for lbl in i.get("labels", []) if isinstance(lbl, dict)
            ),
        }
        for i in raw
    ]
    df = pd.DataFrame(rows, columns=ISSUE_COLS)
    df = _to_datetime(df, ["created_at", "closed_at"])
    df["resolution_days"] = (df["closed_at"] - df["created_at"]).dt.total_seconds() / 86400
    return df.drop_duplicates("number").reset_index(drop=True)


def pulls_to_df(raw: list[dict]) -> pd.DataFrame:
    rows = [
        {
            "number": p.get("number"),
            "title": p.get("title", ""),
            "state": p.get("state"),
            "created_at": p.get("created_at"),
            "closed_at": p.get("closed_at"),
            "merged_at": p.get("merged_at"),
            "author": (p.get("user") or {}).get("login", "ghost"),
            "draft": bool(p.get("draft", False)),
        }
        for p in raw
    ]
    df = pd.DataFrame(rows, columns=PR_COLS)
    df = _to_datetime(df, ["created_at", "closed_at", "merged_at"])
    df["time_to_merge_days"] = (df["merged_at"] - df["created_at"]).dt.total_seconds() / 86400

    def outcome(row: pd.Series) -> str:
        if pd.notna(row["merged_at"]):
            return "merged"
        return "open" if row["state"] == "open" else "closed (not merged)"

    df["outcome"] = df.apply(outcome, axis=1) if len(df) else pd.Series(dtype="object")
    return df.drop_duplicates("number").reset_index(drop=True)


def contributors_to_df(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(
        [{"login": c.get("login", "unknown"), "contributions": c.get("contributions", 0)} for c in raw],
        columns=["login", "contributions"],
    )
    df = df.sort_values("contributions", ascending=False).reset_index(drop=True)
    total = df["contributions"].sum()
    df["rank"] = df.index + 1
    df["share"] = df["contributions"] / total if total else 0.0
    return df


# ------------------------------------------------------------------ time series
def _month(series: pd.Series) -> pd.Series:
    return series.dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()


def monthly_activity(df: pd.DataFrame, close_col: str, truncated: bool = False) -> pd.DataFrame:
    """Items opened and closed (or merged) per month, among the sampled items.

    When the sample was cut short (truncated), the oldest month is only partly
    covered, so it is dropped to avoid a misleading dip.
    """
    empty = pd.DataFrame({"month": pd.to_datetime([]), "opened": [], "closed": []})
    if df.empty:
        return empty

    opened = _month(df["created_at"]).value_counts()
    closed_series = df[close_col].dropna()
    closed = _month(closed_series).value_counts() if len(closed_series) else pd.Series(dtype=int)

    months = pd.date_range(
        min(opened.index.min(), closed.index.min() if len(closed) else opened.index.min()),
        max(opened.index.max(), closed.index.max() if len(closed) else opened.index.max()),
        freq="MS",
    )
    out = pd.DataFrame({"month": months})
    out["opened"] = out["month"].map(opened).fillna(0).astype(int)
    out["closed"] = out["month"].map(closed).fillna(0).astype(int)
    if truncated and len(out) > 1:
        out = out.iloc[1:].reset_index(drop=True)
    return out


def resolution_buckets(days: pd.Series) -> pd.DataFrame:
    """How long closed items took to resolve, grouped into readable buckets."""
    d = days.dropna()
    cats = pd.cut(d, bins=BUCKET_EDGES, labels=BUCKET_LABELS, right=False, include_lowest=True)
    counts = cats.value_counts().reindex(BUCKET_LABELS, fill_value=0)
    total = int(counts.sum())
    share = counts.values / total if total else 0.0
    return pd.DataFrame({"bucket": BUCKET_LABELS, "count": counts.values, "share": share})


# ---------------------------------------------------------------------- summary
def _median(s: pd.Series) -> float | None:
    s = s.dropna()
    return float(s.median()) if len(s) else None


def _quantile(s: pd.Series, q: float) -> float | None:
    s = s.dropna()
    return float(s.quantile(q)) if len(s) else None


def _ratio(a: float, b: float) -> float | None:
    return float(a) / float(b) if b else None


def summarize(
    repo: dict,
    issues: pd.DataFrame,
    pulls: pd.DataFrame,
    contributors: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> dict:
    """One row of headline metrics for a repository."""
    now = now or pd.Timestamp.now(tz="UTC")
    created = pd.to_datetime(repo.get("created_at"), utc=True, errors="coerce")
    pushed = pd.to_datetime(repo.get("pushed_at"), utc=True, errors="coerce")

    total_contrib = contributors["contributions"].sum() if len(contributors) else 0

    def top_share(n: int) -> float | None:
        if not total_contrib:
            return None
        return float(contributors["contributions"].head(n).sum() / total_contrib)

    license_info = repo.get("license") or {}
    return {
        "full_name": repo.get("full_name"),
        "language": repo.get("language"),
        "license": license_info.get("spdx_id"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "watchers": repo.get("subscribers_count", repo.get("watchers_count")),
        "open_issues_and_prs": repo.get("open_issues_count"),
        "age_years": (now - created).days / 365.25 if pd.notna(created) else None,
        "days_since_push": (now - pushed).total_seconds() / 86400 if pd.notna(pushed) else None,
        "issues_sampled": len(issues),
        "issues_closed": int(issues["closed_at"].notna().sum()),
        "issue_closure_rate": _ratio(issues["closed_at"].notna().sum(), len(issues)),
        "issue_median_days": _median(issues["resolution_days"]),
        "issue_p90_days": _quantile(issues["resolution_days"], 0.9),
        "prs_sampled": len(pulls),
        "prs_merged": int(pulls["merged_at"].notna().sum()),
        "pr_merge_rate": _ratio(pulls["merged_at"].notna().sum(), len(pulls)),
        "pr_median_days": _median(pulls["time_to_merge_days"]),
        "contributors_listed": len(contributors),
        "top1_share": top_share(1),
        "top5_share": top_share(5),
        "top10_share": top_share(10),
    }


def compare_table(summaries: list[dict]) -> pd.DataFrame:
    """Side-by-side numeric table (one row per repository)."""
    return pd.DataFrame(summaries)
