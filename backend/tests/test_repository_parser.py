import pytest

from app.core.errors import InvalidRepositoryURLError
from app.services.repository_parser import parse_repository_url


@pytest.mark.parametrize(
    ("raw", "owner", "name"),
    [
        ("https://github.com/facebook/react", "facebook", "react"),
        ("http://github.com/facebook/react/", "facebook", "react"),
        ("https://www.github.com/facebook/react.git", "facebook", "react"),
        ("github.com/facebook/react", "facebook", "react"),
        ("https://github.com/vercel/next.js/tree/canary/packages", "vercel", "next.js"),
        ("https://github.com/psf/requests?tab=readme#install", "psf", "requests"),
        ("  https://github.com/Owner-1/repo_name.v2  ", "Owner-1", "repo_name.v2"),
        ("git@github.com:rust-lang/rust.git", "rust-lang", "rust"),
        ("torvalds/linux", "torvalds", "linux"),
        ("HTTPS://GITHUB.COM/a/b", "a", "b"),
    ],
)
def test_parses_supported_forms(raw: str, owner: str, name: str) -> None:
    ref = parse_repository_url(raw)
    assert (ref.owner, ref.name) == (owner, name)
    assert ref.full_name == f"{owner}/{name}"
    assert ref.html_url == f"https://github.com/{owner}/{name}"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "https://github.com/facebook",
        "https://gitlab.com/group/project",
        "https://github.com.evil.com/a/b",
        "https://evil.com/github.com/a/b",
        "ftp://github.com/a/b",
        "javascript:alert(1)",
        "https://user:pass@github.com/a/b",
        "https://github.com:8443/a/b",
        "https://github.com/-bad/repo",
        "https://github.com/bad-/repo",
        "https://github.com/a--b-/repo",
        "https://github.com/" + "a" * 40 + "/repo",
        "https://github.com/owner/" + "r" * 101,
        "https://github.com/owner/..",
        "https://github.com/owner/re po",
        "https://github.com/owner/repo%2F..",
        "https://github.com/../../etc/passwd",
        "https://github.com/settings/profile",
        "https://github.com/orgs/python",
        "owner/repo\nHost: evil",
        "a" * 600,
    ],
)
def test_rejects_invalid_input(raw: str) -> None:
    with pytest.raises(InvalidRepositoryURLError):
        parse_repository_url(raw)


def test_rejects_non_string() -> None:
    with pytest.raises(InvalidRepositoryURLError):
        parse_repository_url(None)  # type: ignore[arg-type]
