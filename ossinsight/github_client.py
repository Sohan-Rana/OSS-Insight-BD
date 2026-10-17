"""Small GitHub REST API client.

Features: optional token, pagination, 1-hour disk cache and clear error messages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import requests
from dotenv import load_dotenv

load_dotenv()

API_ROOT = "https://api.github.com"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour

_REPO_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$"
)


class GitHubAPIError(RuntimeError):
    """Any problem talking to the GitHub API."""


class RateLimitError(GitHubAPIError):
    """The GitHub API rate limit was reached."""


class RepoNotFoundError(GitHubAPIError):
    """The repository (or endpoint) does not exist or is private."""


class FetchResult(NamedTuple):
    items: list
    truncated: bool  # True when more pages may exist that were not fetched


def parse_repo(text: str) -> tuple[str, str]:
    """Accept 'owner/name' or a full GitHub URL and return (owner, name)."""
    match = _REPO_RE.match(text.strip())
    if not match:
        raise ValueError(
            f"'{text}' is not a valid repository. Use the form owner/name, "
            "for example pandas-dev/pandas"
        )
    return match.group("owner"), match.group("repo")


class GitHubClient:
    def __init__(self, token: str | None = None, use_cache: bool = True, per_page: int = 100):
        self.token = token or os.getenv("GITHUB_TOKEN") or None
        self.use_cache = use_cache
        self.per_page = per_page
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "oss-insight-bd",
            }
        )
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    # ------------------------------------------------------------------ cache
    def _cache_file(self, path: str, params: dict | None) -> Path:
        raw = json.dumps([path, params or {}], sort_keys=True)
        return CACHE_DIR / (hashlib.sha1(raw.encode()).hexdigest() + ".json")

    def _cache_read(self, path: str, params: dict | None) -> Any | None:
        if not self.use_cache:
            return None
        file = self._cache_file(path, params)
        try:
            if file.exists() and time.time() - file.stat().st_mtime < CACHE_TTL_SECONDS:
                return json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return None

    def _cache_write(self, path: str, params: dict | None, data: Any) -> None:
        if not self.use_cache:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._cache_file(path, params).write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass  # cache is best-effort

    # ---------------------------------------------------------------- request
    @staticmethod
    def _check(resp: requests.Response, path: str) -> None:
        status = resp.status_code
        if status == 401:
            raise GitHubAPIError("Bad credentials (401). Check your GITHUB_TOKEN.")
        if status == 404:
            raise RepoNotFoundError(
                f"Not found (404): {path}. Check the owner/name, "
                "or the repository may be private."
            )
        if status in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining == "0" or status == 429 or "Retry-After" in resp.headers:
                reset = resp.headers.get("X-RateLimit-Reset")
                when = ""
                if reset and reset.isdigit():
                    when = " Limit resets at " + datetime.fromtimestamp(int(reset)).strftime("%H:%M") + "."
                raise RateLimitError(
                    "GitHub API rate limit reached." + when
                    + " Add a GITHUB_TOKEN to raise the limit from 60 to 5000 requests/hour."
                )
            raise GitHubAPIError(f"Access forbidden (403) for {path}: {resp.text[:200]}")
        resp.raise_for_status()

    def _get_json(self, path: str, params: dict | None = None) -> Any:
        cached = self._cache_read(path, params)
        if cached is not None:
            return cached
        try:
            resp = self.session.get(API_ROOT + path, params=params, timeout=30)
        except requests.RequestException as exc:
            raise GitHubAPIError(f"Network error while calling GitHub: {exc}") from exc
        self._check(resp, path)
        data = resp.json() if resp.content else []
        self._cache_write(path, params, data)
        return data

    def _paginate(self, path: str, params: dict, max_pages: int) -> FetchResult:
        items: list = []
        truncated = False
        for page in range(1, max_pages + 1):
            data = self._get_json(path, {**params, "per_page": self.per_page, "page": page})
            if not isinstance(data, list):
                break
            items.extend(data)
            if len(data) < self.per_page:
                break
        else:
            truncated = True  # every page was full, so more may exist
        return FetchResult(items, truncated)

    # --------------------------------------------------------------- endpoints
    def rate_limit(self) -> dict:
        """Remaining API calls (this endpoint does not count against the limit)."""
        return self._get_json_uncached("/rate_limit").get("resources", {}).get("core", {})

    def _get_json_uncached(self, path: str) -> dict:
        resp = self.session.get(API_ROOT + path, timeout=30)
        self._check(resp, path)
        return resp.json()

    def get_repo(self, owner: str, repo: str) -> dict:
        return self._get_json(f"/repos/{owner}/{repo}")

    def get_languages(self, owner: str, repo: str) -> dict:
        return self._get_json(f"/repos/{owner}/{repo}/languages")

    def get_issues(self, owner: str, repo: str, max_pages: int = 3) -> FetchResult:
        """Latest issues (newest first). Pull requests are filtered out."""
        result = self._paginate(
            f"/repos/{owner}/{repo}/issues",
            {"state": "all", "sort": "created", "direction": "desc"},
            max_pages,
        )
        issues = [i for i in result.items if "pull_request" not in i]
        return FetchResult(issues, result.truncated)

    def get_pulls(self, owner: str, repo: str, max_pages: int = 3) -> FetchResult:
        """Latest pull requests (newest first)."""
        return self._paginate(
            f"/repos/{owner}/{repo}/pulls",
            {"state": "all", "sort": "created", "direction": "desc"},
            max_pages,
        )

    def get_contributors(self, owner: str, repo: str, max_pages: int = 1) -> FetchResult:
        """Top contributors by number of commits (anonymous contributors excluded)."""
        return self._paginate(f"/repos/{owner}/{repo}/contributors", {}, max_pages)
