"""Unit tests for GitHub service — runs against real GitHub API."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.github_service import GitHubService, GitHubServiceError


async def test_get_repo():
    gh = GitHubService()
    repo = await gh.get_repo("NoodyYeung/EducationDataAnalysis")
    assert repo["full_name"] == "NoodyYeung/EducationDataAnalysis"
    assert "default_branch" in repo
    print("✅ test_get_repo passed")


async def test_list_branches():
    gh = GitHubService()
    branches = await gh.list_branches("NoodyYeung/EducationDataAnalysis")
    assert isinstance(branches, list)
    names = [b["name"] for b in branches]
    assert "main" in names
    print(f"✅ test_list_branches passed ({len(branches)} branches)")


async def test_list_prs():
    gh = GitHubService()
    prs = await gh.list_prs("NoodyYeung/EducationDataAnalysis", state="all")
    assert isinstance(prs, list)
    if prs:
        assert "number" in prs[0]
        assert "title" in prs[0]
    print(f"✅ test_list_prs passed ({len(prs)} PRs)")


async def test_compare_branches():
    gh = GitHubService()
    diff = await gh.compare_branches("NoodyYeung/EducationDataAnalysis", "main", "feat/data-quality")
    assert "ahead_by" in diff
    assert "behind_by" in diff
    print(f"✅ test_compare_branches passed (ahead={diff['ahead_by']}, behind={diff['behind_by']})")


async def test_parse_repo():
    gh = GitHubService()
    owner, name = gh.parse_repo("NoodyYeung/EducationDataAnalysis")
    assert owner == "NoodyYeung"
    assert name == "EducationDataAnalysis"

    try:
        gh.parse_repo("badformat")
        assert False, "Should have raised"
    except GitHubServiceError:
        pass
    print("✅ test_parse_repo passed")


async def test_no_token():
    old = os.environ.pop("GITHUB_TOKEN", None)
    try:
        GitHubService(token="")
        assert False, "Should have raised"
    except GitHubServiceError as e:
        assert "not configured" in e.message
    finally:
        if old:
            os.environ["GITHUB_TOKEN"] = old
    print("✅ test_no_token passed")


async def main():
    print("Running GitHub Service tests...\n")
    await test_parse_repo()
    await test_no_token()
    await test_get_repo()
    await test_list_branches()
    await test_list_prs()
    await test_compare_branches()
    print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
