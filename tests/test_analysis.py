import pandas as pd

from ossinsight.analysis import (
    compare_table,
    contributors_to_df,
    issues_to_df,
    monthly_activity,
    pulls_to_df,
    resolution_buckets,
    summarize,
)
from ossinsight.pipeline import load_repo


def test_issue_cleaning_and_resolution_days():
    raw = [
        {"number": 1, "state": "closed", "created_at": "2025-01-01T00:00:00Z",
         "closed_at": "2025-01-03T00:00:00Z", "user": {"login": "a"}, "labels": [{"name": "bug"}]},
        {"number": 2, "state": "open", "created_at": "2025-01-05T00:00:00Z",
         "closed_at": None, "user": None, "labels": []},
        {"number": 1, "state": "closed", "created_at": "2025-01-01T00:00:00Z",
         "closed_at": "2025-01-03T00:00:00Z"},  # duplicate number is dropped
    ]
    df = issues_to_df(raw)
    assert len(df) == 2
    assert df.loc[df.number == 1, "resolution_days"].iloc[0] == 2.0
    assert pd.isna(df.loc[df.number == 2, "resolution_days"].iloc[0])
    assert df.loc[df.number == 2, "author"].iloc[0] == "ghost"
    assert df.loc[df.number == 1, "labels"].iloc[0] == "bug"


def test_pull_outcomes():
    raw = [
        {"number": 1, "state": "closed", "created_at": "2025-01-01T00:00:00Z",
         "closed_at": "2025-01-02T00:00:00Z", "merged_at": "2025-01-02T00:00:00Z"},
        {"number": 2, "state": "closed", "created_at": "2025-01-01T00:00:00Z",
         "closed_at": "2025-01-02T00:00:00Z", "merged_at": None},
        {"number": 3, "state": "open", "created_at": "2025-01-01T00:00:00Z",
         "closed_at": None, "merged_at": None},
    ]
    df = pulls_to_df(raw)
    assert df.set_index("number")["outcome"].to_dict() == {
        1: "merged", 2: "closed (not merged)", 3: "open"}


def test_contributor_shares_sum_to_one():
    df = contributors_to_df([{"login": "a", "contributions": 30}, {"login": "b", "contributions": 70}])
    assert list(df["login"]) == ["b", "a"]
    assert abs(df["share"].sum() - 1.0) < 1e-9


def test_monthly_activity_counts_everything_once():
    bundle = load_repo("demo/repo", source="demo")
    m = monthly_activity(bundle.issues, "closed_at")
    assert m["opened"].sum() == len(bundle.issues)
    assert m["closed"].sum() == bundle.issues["closed_at"].notna().sum()


def test_truncated_sample_drops_first_partial_month():
    bundle = load_repo("demo/repo", source="demo")
    full = monthly_activity(bundle.issues, "closed_at", truncated=False)
    cut = monthly_activity(bundle.issues, "closed_at", truncated=True)
    assert len(cut) == len(full) - 1


def test_resolution_buckets_cover_all_closed_items():
    bundle = load_repo("demo/repo", source="demo")
    buckets = resolution_buckets(bundle.issues["resolution_days"])
    assert buckets["count"].sum() == bundle.issues["closed_at"].notna().sum()
    assert abs(buckets["share"].sum() - 1.0) < 1e-9


def test_summary_rates_are_valid_fractions():
    s = load_repo("demo/repo", source="demo").summary
    for key in ("issue_closure_rate", "pr_merge_rate", "top1_share", "top5_share", "top10_share"):
        assert 0 <= s[key] <= 1
    assert s["top1_share"] <= s["top5_share"] <= s["top10_share"]


def test_empty_inputs_do_not_crash():
    ei, ep, ec = issues_to_df([]), pulls_to_df([]), contributors_to_df([])
    assert monthly_activity(ei, "closed_at").empty
    assert resolution_buckets(ei["resolution_days"])["count"].sum() == 0
    s = summarize({"full_name": "x/y"}, ei, ep, ec)
    assert s["issue_closure_rate"] is None and s["top10_share"] is None


def test_demo_data_is_deterministic_and_differs_between_repos():
    a1 = load_repo("a/one", source="demo").summary
    a2 = load_repo("a/one", source="demo").summary
    b = load_repo("b/two", source="demo").summary
    assert a1["stars"] == a2["stars"]
    assert a1["stars"] != b["stars"]


def test_compare_table_has_one_row_per_repo():
    rows = [load_repo(n, source="demo").summary for n in ("a/one", "b/two", "c/three")]
    assert len(compare_table(rows)) == 3
