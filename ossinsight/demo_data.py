"""Synthetic demo data shaped like GitHub API responses.

IMPORTANT: this is NOT real GitHub data. It exists so the dashboard, charts and
tests can run offline. Every chart made from it is labelled "DEMO DATA".
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np

LABELS = ["bug", "enhancement", "documentation", "question", "good first issue"]
LANGUAGES = ["Python", "C", "Cython", "JavaScript", "Shell", "Makefile", "HTML"]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_demo_raw(
    full_name: str,
    n_issues: int = 400,
    n_pulls: int = 250,
    n_contributors: int = 60,
    span_days: int = 540,
    now: datetime | None = None,
) -> dict:
    """Return raw API-shaped data. The same name always gives the same data."""
    seed = int(hashlib.sha256(full_name.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    now = now or datetime.now(timezone.utc)

    users = [f"contributor_{i:02d}" for i in range(1, n_contributors + 1)]
    weights = 1.0 / np.arange(1, n_contributors + 1) ** 1.1
    weights = weights / weights.sum()

    issue_median = float(rng.uniform(4, 40))   # median days to close an issue
    pr_median = float(rng.uniform(1, 12))      # median days to merge a PR
    merge_prob = float(rng.uniform(0.55, 0.85))

    def times(n: int) -> list[datetime]:
        days_ago = np.sort(rng.uniform(0, span_days, n))[::-1]  # oldest first
        return [now - timedelta(days=float(d)) for d in days_ago]

    # --- issues -----------------------------------------------------------
    issues = []
    for idx, created in enumerate(times(n_issues)):
        res_days = float(rng.lognormal(np.log(issue_median), 1.1))
        closed = created + timedelta(days=res_days)
        is_closed = bool(rng.random() < 0.85) and closed <= now
        n_labels = int(rng.integers(0, 3))
        issues.append(
            {
                "number": 1000 + idx,
                "title": f"Demo issue {1000 + idx}",
                "state": "closed" if is_closed else "open",
                "created_at": _iso(created),
                "closed_at": _iso(closed) if is_closed else None,
                "comments": int(rng.poisson(3)),
                "user": {"login": str(rng.choice(users, p=weights))},
                "labels": [{"name": str(x)} for x in rng.choice(LABELS, n_labels, replace=False)],
            }
        )

    # --- pull requests ----------------------------------------------------
    pulls = []
    for idx, created in enumerate(times(n_pulls)):
        res_days = float(rng.lognormal(np.log(pr_median), 1.0))
        finished = created + timedelta(days=res_days)
        r = rng.random()
        if finished > now:
            state, merged, closed = "open", None, None
        elif r < merge_prob:
            state, merged, closed = "closed", _iso(finished), _iso(finished)
        elif r < merge_prob + 0.1:
            state, merged, closed = "closed", None, _iso(finished)
        else:
            state, merged, closed = "open", None, None
        pulls.append(
            {
                "number": 5000 + idx,
                "title": f"Demo pull request {5000 + idx}",
                "state": state,
                "created_at": _iso(created),
                "closed_at": closed,
                "merged_at": merged,
                "draft": False,
                "user": {"login": str(rng.choice(users, p=weights))},
            }
        )

    # --- contributors -----------------------------------------------------
    contributors = [
        {"login": u, "contributions": int(3000 / (rank ** 1.1)) + int(rng.integers(1, 5))}
        for rank, u in enumerate(users, start=1)
    ]

    open_count = sum(i["state"] == "open" for i in issues) + sum(p["state"] == "open" for p in pulls)
    repo = {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": "Synthetic demo data - not a real repository.",
        "stargazers_count": int(rng.integers(500, 60000)),
        "forks_count": int(rng.integers(50, 20000)),
        "subscribers_count": int(rng.integers(20, 2000)),
        "open_issues_count": int(open_count),
        "language": "Python",
        "license": {"spdx_id": "MIT"},
        "created_at": _iso(now - timedelta(days=int(rng.integers(1200, 3600)))),
        "pushed_at": _iso(now - timedelta(hours=int(rng.integers(1, 72)))),
    }

    lang_weights = np.sort(rng.dirichlet(np.ones(len(LANGUAGES)) * 0.6))[::-1]
    languages = {lang: int(w * 5_000_000) for lang, w in zip(LANGUAGES, lang_weights)}

    return {
        "repo": repo,
        "languages": languages,
        "issues": issues[::-1],   # API returns newest first
        "pulls": pulls[::-1],
        "contributors": contributors,
    }
