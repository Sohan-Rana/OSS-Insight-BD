"""Load one repository (live from GitHub, or demo data) into a RepoBundle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from .analysis import (
    contributors_to_df,
    issues_to_df,
    pulls_to_df,
    summarize,
)
from .demo_data import make_demo_raw
from .github_client import GitHubAPIError, GitHubClient, RateLimitError, parse_repo


@dataclass
class RepoBundle:
    full_name: str
    source: str  # "live" or "demo"
    repo: dict
    languages: dict
    issues: pd.DataFrame
    pulls: pd.DataFrame
    contributors: pd.DataFrame
    issues_truncated: bool = False
    pulls_truncated: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: list[str] = field(default_factory=list)

    @property
    def is_demo(self) -> bool:
        return self.source == "demo"

    @property
    def summary(self) -> dict:
        return summarize(self.repo, self.issues, self.pulls, self.contributors)


def load_repo(
    full_name: str,
    source: str = "live",
    max_pages: int = 3,
    token: str | None = None,
    use_cache: bool = True,
) -> RepoBundle:
    """Fetch and clean everything we need for one repository."""
    owner, name = parse_repo(full_name)
    canonical = f"{owner}/{name}"

    if source == "demo":
        raw = make_demo_raw(canonical)
        return RepoBundle(
            full_name=canonical,
            source="demo",
            repo=raw["repo"],
            languages=raw["languages"],
            issues=issues_to_df(raw["issues"]),
            pulls=pulls_to_df(raw["pulls"]),
            contributors=contributors_to_df(raw["contributors"]),
            notes=["Synthetic demo data - not real GitHub data."],
        )

    client = GitHubClient(token=token, use_cache=use_cache)
    notes: list[str] = []

    repo = client.get_repo(owner, name)
    languages = client.get_languages(owner, name)
    issues = client.get_issues(owner, name, max_pages=max_pages)
    pulls = client.get_pulls(owner, name, max_pages=max_pages)

    try:
        contributors = client.get_contributors(owner, name, max_pages=1).items
    except RateLimitError:
        raise
    except GitHubAPIError as exc:
        contributors = []
        notes.append(f"Contributor list unavailable: {exc}")

    if issues.truncated:
        notes.append(f"Issues: only the newest {max_pages * client.per_page} items were fetched.")
    if pulls.truncated:
        notes.append(f"Pull requests: only the newest {max_pages * client.per_page} items were fetched.")

    return RepoBundle(
        full_name=repo.get("full_name", canonical),
        source="live",
        repo=repo,
        languages=languages,
        issues=issues_to_df(issues.items),
        pulls=pulls_to_df(pulls.items),
        contributors=contributors_to_df(contributors),
        issues_truncated=issues.truncated,
        pulls_truncated=pulls.truncated,
        notes=notes,
    )
