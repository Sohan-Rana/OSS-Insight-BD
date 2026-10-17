"""Command-line report generator: fetch repositories and save PNG charts + CSV.

Examples:
    python generate_report.py pandas-dev/pandas
    python generate_report.py pandas-dev/pandas numpy/numpy scikit-learn/scikit-learn
    python generate_report.py pandas-dev/pandas --demo      # offline, synthetic data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ossinsight.analysis import compare_table
from ossinsight.github_client import GitHubAPIError
from ossinsight.pipeline import load_repo
from ossinsight.report import save_comparison_chart, save_repo_charts


def main() -> int:
    parser = argparse.ArgumentParser(description="OSS Insight BD report generator")
    parser.add_argument("repos", nargs="+", help="owner/name (up to 3)")
    parser.add_argument("--demo", action="store_true", help="use synthetic demo data (no network)")
    parser.add_argument("--max-pages", type=int, default=3, help="pages of 100 items per endpoint")
    parser.add_argument("--out", default="assets", help="output folder for PNG files")
    parser.add_argument("--prefix", default="", help="file name prefix, e.g. demo_")
    args = parser.parse_args()

    repos = list(dict.fromkeys(args.repos))[:3]
    source = "demo" if args.demo else "live"
    out = Path(args.out)

    bundles = []
    try:
        for name in repos:
            print(f"Loading {name} ({source}) ...")
            bundles.append(load_repo(name, source=source, max_pages=args.max_pages))
    except (ValueError, GitHubAPIError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for bundle in bundles:
        for path in save_repo_charts(bundle, out, prefix=args.prefix):
            print("  saved", path)

    table = compare_table([b.summary for b in bundles])
    exports = Path("data/exports")
    exports.mkdir(parents=True, exist_ok=True)
    csv_path = exports / f"{args.prefix}summary.csv"
    table.to_csv(csv_path, index=False)
    print("  saved", csv_path)

    if len(bundles) > 1:
        specs = [
            ("issue_closure_rate", "Issue closure rate", "closure_rate", True),
            ("issue_median_days", "Median days to close an issue", "median_days", False),
            ("pr_merge_rate", "PR merge rate", "merge_rate", True),
        ]
        for column, title, slug, percent in specs:
            path = out / f"{args.prefix}compare_{slug}.png"
            save_comparison_chart(table, column, title, path, bundles=bundles, percent=percent)
            print("  saved", path)

    print(table[["full_name", "stars", "issue_closure_rate", "issue_median_days", "pr_merge_rate"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
