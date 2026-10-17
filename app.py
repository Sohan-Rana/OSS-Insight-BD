"""OSS Insight BD - Streamlit dashboard.

Run:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

from ossinsight.analysis import compare_table, monthly_activity, resolution_buckets
from ossinsight.charts import (
    activity_chart,
    compare_chart,
    contributors_chart,
    languages_chart,
    resolution_chart,
)
from ossinsight.github_client import GitHubAPIError, parse_repo
from ossinsight.pipeline import RepoBundle, load_repo

MAX_REPOS = 3  # colours stay easy to tell apart up to three repositories

st.set_page_config(page_title="OSS Insight BD", page_icon="📊", layout="wide")


# ------------------------------------------------------------------ helpers
def fmt_int(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{int(x):,}"


def fmt_pct(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.0%}"


def fmt_days(x) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x * 24:.0f} hours" if x < 1 else f"{x:.1f} days"


@st.cache_data(ttl=3600, show_spinner=False)
def cached_load(full_name: str, source: str, max_pages: int, token: str | None) -> RepoBundle:
    return load_repo(full_name, source=source, max_pages=max_pages, token=token or None)


# ------------------------------------------------------------------ sidebar
st.sidebar.title("OSS Insight BD")
st.sidebar.caption("Open-source software intelligence for GitHub repositories")

source_label = st.sidebar.radio(
    "Data source",
    ["Live (GitHub API)", "Demo data (offline)"],
    help="Demo data is synthetic. It only shows how the dashboard looks.",
)
source = "live" if source_label.startswith("Live") else "demo"

repo_text = st.sidebar.text_area(
    f"Repositories (max {MAX_REPOS}, one per line)",
    value="pandas-dev/pandas",
    height=100,
    help="Format: owner/name, or a full GitHub URL.",
)
max_pages = st.sidebar.slider(
    "Pages of history (100 items each)", 1, 10, 3,
    help="More pages = longer history, but more API requests.",
)
token = st.sidebar.text_input(
    "GitHub token (optional)", type="password",
    help="Leave empty to use GITHUB_TOKEN from your .env file. Without any token GitHub allows only 60 requests/hour.",
)
run = st.sidebar.button("Analyze", type="primary", width="stretch")

# ------------------------------------------------------------------ main
st.title("OSS Insight BD")
st.caption("Collect, clean, analyze and visualize GitHub repository activity.")

if run:
    names = [line.strip() for line in repo_text.splitlines() if line.strip()]
    names = list(dict.fromkeys(names))  # drop duplicates, keep order
    if not names:
        st.warning("Enter at least one repository, for example pandas-dev/pandas")
        st.stop()
    if len(names) > MAX_REPOS:
        st.warning(f"Only the first {MAX_REPOS} repositories are used.")
        names = names[:MAX_REPOS]

    bundles: list[RepoBundle] = []
    try:
        with st.spinner("Collecting data..."):
            for n in names:
                parse_repo(n)  # validate early with a friendly message
                bundles.append(cached_load(n, source, max_pages, token.strip() or None))
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except GitHubAPIError as exc:
        st.error(f"GitHub API problem: {exc}")
        st.stop()
    except requests.RequestException as exc:
        st.error(f"Network problem: {exc}")
        st.stop()
    st.session_state["bundles"] = bundles

bundles: list[RepoBundle] | None = st.session_state.get("bundles")
if not bundles:
    st.info("Choose a data source and repository in the sidebar, then press **Analyze**.")
    st.stop()

if any(b.is_demo for b in bundles):
    st.warning("DEMO DATA - these numbers are synthetic and are not real GitHub data.")

if len(bundles) > 1:
    chosen = st.selectbox("Repository to inspect", [b.full_name for b in bundles])
    bundle = next(b for b in bundles if b.full_name == chosen)
else:
    bundle = bundles[0]

summary = bundle.summary
for note in bundle.notes:
    if not bundle.is_demo:
        st.caption(f"Note: {note}")

tab_names = ["Overview", "Issues & PRs", "Contributors"]
if len(bundles) > 1:
    tab_names.append("Compare")
tab_names += ["Data & export", "Method & limits"]
tabs = dict(zip(tab_names, st.tabs(tab_names)))

# ---- Overview
with tabs["Overview"]:
    url = bundle.repo.get("html_url")
    st.subheader(f"[{bundle.full_name}]({url})" if url and not bundle.is_demo else bundle.full_name)
    if bundle.repo.get("description"):
        st.write(bundle.repo["description"])
    c = st.columns(4)
    c[0].metric("Stars", fmt_int(summary["stars"]))
    c[1].metric("Forks", fmt_int(summary["forks"]))
    c[2].metric("Open issues + PRs", fmt_int(summary["open_issues_and_prs"]),
                help="GitHub counts open pull requests inside this number.")
    c[3].metric("Main language", summary["language"] or "n/a")
    c = st.columns(4)
    c[0].metric("Repository age", "n/a" if summary["age_years"] is None else f"{summary['age_years']:.1f} years")
    c[1].metric("Last push", fmt_days(summary["days_since_push"]) + " ago" if summary["days_since_push"] is not None else "n/a")
    c[2].metric("License", summary["license"] or "none")
    c[3].metric("Watchers", fmt_int(summary["watchers"]))
    st.plotly_chart(languages_chart(bundle.languages, "Languages by code size"), width="stretch")

# ---- Issues & PRs
with tabs["Issues & PRs"]:
    c = st.columns(4)
    c[0].metric("Issue closure rate", fmt_pct(summary["issue_closure_rate"]),
                help=f"Closed issues / issues in the sample ({fmt_int(summary['issues_sampled'])}).")
    c[1].metric("Median time to close", fmt_days(summary["issue_median_days"]),
                help="Only closed issues are counted, so slow-to-close items are under-represented.")
    c[2].metric("PR merge rate", fmt_pct(summary["pr_merge_rate"]),
                help=f"Merged PRs / PRs in the sample ({fmt_int(summary['prs_sampled'])}).")
    c[3].metric("Median time to merge", fmt_days(summary["pr_median_days"]))

    issues_m = monthly_activity(bundle.issues, "closed_at", bundle.issues_truncated)
    pulls_m = monthly_activity(bundle.pulls, "merged_at", bundle.pulls_truncated)
    left, right = st.columns(2)
    left.plotly_chart(activity_chart(issues_m, "Issues per month", "Opened", "Closed"), width="stretch")
    right.plotly_chart(activity_chart(pulls_m, "Pull requests per month", "Opened", "Merged"), width="stretch")
    st.caption("Counts cover the sampled items only. The latest month may still be in progress.")
    st.plotly_chart(
        resolution_chart(resolution_buckets(bundle.issues["resolution_days"]), "How long closed issues took to resolve"),
        width="stretch",
    )

# ---- Contributors
with tabs["Contributors"]:
    c = st.columns(3)
    c[0].metric("Contributors listed", fmt_int(summary["contributors_listed"]),
                help="GitHub returns the top 100 contributors by commits.")
    c[1].metric("Top contributor share", fmt_pct(summary["top1_share"]))
    c[2].metric("Top 10 share", fmt_pct(summary["top10_share"]),
                help="Share of commits made by the 10 most active contributors, among those listed.")
    st.plotly_chart(contributors_chart(bundle.contributors, "Top contributors by commits"), width="stretch")
    if not bundle.contributors.empty:
        shown = bundle.contributors.copy()
        shown["share"] = (shown["share"] * 100).round(1)
        st.dataframe(shown.rename(columns={"share": "share (%)"}), width="stretch", hide_index=True)

# ---- Compare
table = compare_table([b.summary for b in bundles])
if "Compare" in tabs:
    with tabs["Compare"]:
        shown = table[[
            "full_name", "stars", "forks", "issue_closure_rate", "issue_median_days",
            "pr_merge_rate", "pr_median_days", "top10_share",
        ]].rename(columns={
            "full_name": "Repository", "stars": "Stars", "forks": "Forks",
            "issue_closure_rate": "Issue closure rate", "issue_median_days": "Median days to close",
            "pr_merge_rate": "PR merge rate", "pr_median_days": "Median days to merge",
            "top10_share": "Top-10 commit share",
        })
        st.dataframe(shown, width="stretch", hide_index=True)
        a, b = st.columns(2)
        a.plotly_chart(compare_chart(table, "stars", "Stars", decimals=0), width="stretch")
        b.plotly_chart(compare_chart(table, "issue_closure_rate", "Issue closure rate", percent=True), width="stretch")
        a, b = st.columns(2)
        a.plotly_chart(compare_chart(table, "issue_median_days", "Median days to close an issue"), width="stretch")
        b.plotly_chart(compare_chart(table, "pr_merge_rate", "PR merge rate", percent=True), width="stretch")
        st.caption("More stars do not mean a project is better maintained. Compare metrics with care.")

# ---- Data & export
with tabs["Data & export"]:
    slug = bundle.full_name.replace("/", "__")
    st.write("Download the cleaned data used in the charts.")
    c = st.columns(4)
    c[0].download_button("Issues (CSV)", bundle.issues.to_csv(index=False), f"{slug}_issues.csv", "text/csv")
    c[1].download_button("Pull requests (CSV)", bundle.pulls.to_csv(index=False), f"{slug}_pulls.csv", "text/csv")
    c[2].download_button("Contributors (CSV)", bundle.contributors.to_csv(index=False), f"{slug}_contributors.csv", "text/csv")
    c[3].download_button("Summary, all repos (CSV)", table.to_csv(index=False), "summary.csv", "text/csv")
    st.dataframe(bundle.issues.head(200), width="stretch", hide_index=True)

# ---- Method & limits
with tabs["Method & limits"]:
    st.markdown(
        """
**Pipeline:** GitHub REST API -> clean with Pandas -> metrics -> interactive charts.

**Limits to keep in mind**
- Issues and pull requests are a **sample**: the newest N items (N = pages x 100). Older history is not included.
- *Time to close/merge* uses only finished items. Items still open are left out, so the real waiting time is usually longer.
- Contributor shares use the top 100 contributors that GitHub lists by commits.
- Correlation is not causation. Popularity (stars) does not prove good maintenance.
- GitHub counts pull requests inside "open issues". This dashboard separates them.
"""
    )
