"""Client tests use a fake HTTP session, so they never touch the network."""
import pytest

from ossinsight import github_client
from ossinsight.github_client import (
    GitHubAPIError,
    GitHubClient,
    RateLimitError,
    RepoNotFoundError,
    parse_repo,
)


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self.content = b"x" if data is not None else b""
        self.text = str(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def make_client(monkeypatch, responses, per_page=2):
    monkeypatch.setattr(github_client, "CACHE_DIR", github_client.CACHE_DIR / "_test_unused")
    client = GitHubClient(token="t", use_cache=False, per_page=per_page)
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, dict(params or {})))
        return responses.pop(0)

    monkeypatch.setattr(client.session, "get", fake_get)
    client._calls = calls
    return client


def test_parse_repo_accepts_name_and_url():
    assert parse_repo("pandas-dev/pandas") == ("pandas-dev", "pandas")
    assert parse_repo("https://github.com/numpy/numpy") == ("numpy", "numpy")
    assert parse_repo("https://github.com/numpy/numpy.git") == ("numpy", "numpy")


@pytest.mark.parametrize("bad", ["", "pandas", "a/b/c", "https://example.com/a/b"])
def test_parse_repo_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_repo(bad)


def test_token_is_sent_as_bearer_header(monkeypatch):
    client = make_client(monkeypatch, [])
    assert client.session.headers["Authorization"] == "Bearer t"


def test_issues_filter_out_pull_requests_and_paginate(monkeypatch):
    page1 = [{"number": 1}, {"number": 2, "pull_request": {}}]  # full page (per_page=2)
    page2 = [{"number": 3}]                                       # short page -> stop
    client = make_client(monkeypatch, [FakeResponse(data=page1), FakeResponse(data=page2)])
    result = client.get_issues("o", "r", max_pages=5)
    assert [i["number"] for i in result.items] == [1, 3]
    assert result.truncated is False
    assert [c[1]["page"] for c in client._calls] == [1, 2]


def test_truncated_flag_when_every_page_is_full(monkeypatch):
    full = [{"number": 1}, {"number": 2}]
    client = make_client(monkeypatch, [FakeResponse(data=full), FakeResponse(data=full)])
    result = client.get_pulls("o", "r", max_pages=2)
    assert len(result.items) == 4
    assert result.truncated is True


def test_rate_limit_error(monkeypatch):
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1900000000"}
    client = make_client(monkeypatch, [FakeResponse(status=403, data={}, headers=headers)])
    with pytest.raises(RateLimitError):
        client.get_repo("o", "r")


def test_not_found_and_other_403(monkeypatch):
    client = make_client(monkeypatch, [FakeResponse(status=404, data={})])
    with pytest.raises(RepoNotFoundError):
        client.get_repo("o", "missing")
    client = make_client(monkeypatch, [FakeResponse(status=403, data={"message": "blocked"})])
    with pytest.raises(GitHubAPIError) as info:
        client.get_repo("o", "r")
    assert not isinstance(info.value, RateLimitError)


def test_empty_body_returns_empty_list(monkeypatch):
    client = make_client(monkeypatch, [FakeResponse(status=204, data=None)])
    assert client.get_contributors("o", "r").items == []
