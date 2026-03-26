"""GitHub Service — wraps the GitHub REST API for PR and branch operations.

Usage from ClawBoard API routes:
    from services.github_service import GitHubService

    gh = GitHubService()  # reads GITHUB_TOKEN from env
    pr = await gh.create_pr("owner/repo", "feat/xyz", "main", "feat: xyz", "body")
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubServiceError(Exception):
    """Raised when a GitHub API call fails."""

    def __init__(self, message: str, status_code: int = 0, detail: str = ""):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class GitHubService:
    """Async wrapper around GitHub REST API v3."""

    def __init__(self, token: str | None = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise GitHubServiceError("GITHUB_TOKEN not configured", status_code=500)
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ---- internal helpers ----

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{GITHUB_API}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=self._headers, **kwargs)
            if resp.status_code >= 400:
                body = resp.text[:500]
                logger.error("GitHub API %s %s → %s: %s", method, path, resp.status_code, body)
                raise GitHubServiceError(
                    f"GitHub API error ({resp.status_code})",
                    status_code=resp.status_code,
                    detail=body,
                )
            return resp.json() if resp.content else {}

    @staticmethod
    def parse_repo(repo: str) -> tuple[str, str]:
        """Parse 'owner/repo' into (owner, repo). Raises on bad format."""
        parts = repo.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise GitHubServiceError(f"Invalid repo format: '{repo}'. Expected 'owner/repo'.")
        return parts[0], parts[1]

    # ---- Pull Requests ----

    async def create_pr(
        self,
        repo: str,
        head: str,
        base: str = "main",
        title: str = "",
        body: str = "",
        draft: bool = False,
    ) -> dict:
        """Create a pull request.

        Args:
            repo: "owner/repo"
            head: source branch name
            base: target branch (default "main")
            title: PR title
            body: PR body (Markdown)
            draft: create as draft PR

        Returns: GitHub PR object (id, number, html_url, state, …)
        """
        owner, name = self.parse_repo(repo)
        payload = {
            "title": title or head,
            "head": head,
            "base": base,
            "body": body or "",
            "draft": draft,
        }
        logger.info("Creating PR: %s → %s/%s on %s", head, owner, name, base)
        return await self._request("POST", f"/repos/{owner}/{name}/pulls", json=payload)

    async def list_prs(
        self,
        repo: str,
        state: str = "open",
        head: str | None = None,
        per_page: int = 30,
    ) -> list[dict]:
        """List pull requests."""
        owner, name = self.parse_repo(repo)
        params: dict = {"state": state, "per_page": per_page}
        if head:
            # GitHub expects "owner:branch" format for head filter
            params["head"] = f"{owner}:{head}"
        return await self._request("GET", f"/repos/{owner}/{name}/pulls", params=params)

    async def get_pr(self, repo: str, pr_number: int) -> dict:
        """Get a single pull request."""
        owner, name = self.parse_repo(repo)
        return await self._request("GET", f"/repos/{owner}/{name}/pulls/{pr_number}")

    async def merge_pr(
        self,
        repo: str,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: str | None = None,
    ) -> dict:
        """Merge a pull request."""
        owner, name = self.parse_repo(repo)
        payload: dict = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        return await self._request("PUT", f"/repos/{owner}/{name}/pulls/{pr_number}/merge", json=payload)

    # ---- Branches ----

    async def list_branches(self, repo: str, per_page: int = 100) -> list[dict]:
        """List repository branches."""
        owner, name = self.parse_repo(repo)
        return await self._request("GET", f"/repos/{owner}/{name}/branches", params={"per_page": per_page})

    async def get_branch(self, repo: str, branch: str) -> dict:
        """Get branch details (including latest commit SHA)."""
        owner, name = self.parse_repo(repo)
        return await self._request("GET", f"/repos/{owner}/{name}/branches/{branch}")

    async def create_branch(self, repo: str, branch_name: str, from_branch: str = "main") -> dict:
        """Create a new branch from an existing branch.

        Returns: the Git ref object.
        """
        owner, name = self.parse_repo(repo)
        # First get the SHA of the source branch
        source = await self.get_branch(repo, from_branch)
        sha = source["commit"]["sha"]
        # Create the ref
        payload = {"ref": f"refs/heads/{branch_name}", "sha": sha}
        return await self._request("POST", f"/repos/{owner}/{name}/git/refs", json=payload)

    async def delete_branch(self, repo: str, branch_name: str) -> dict:
        """Delete a branch."""
        owner, name = self.parse_repo(repo)
        return await self._request("DELETE", f"/repos/{owner}/{name}/git/refs/heads/{branch_name}")

    # ---- Repository info ----

    async def get_repo(self, repo: str) -> dict:
        """Get repository info (name, default_branch, visibility, …)."""
        owner, name = self.parse_repo(repo)
        return await self._request("GET", f"/repos/{owner}/{name}")

    async def list_repos(self, per_page: int = 30) -> list[dict]:
        """List repos for the authenticated user."""
        return await self._request("GET", "/user/repos", params={"per_page": per_page, "sort": "updated"})

    # ---- Commits / Diff ----

    async def compare_branches(self, repo: str, base: str, head: str) -> dict:
        """Compare two branches. Returns files changed, commits, etc."""
        owner, name = self.parse_repo(repo)
        return await self._request("GET", f"/repos/{owner}/{name}/compare/{base}...{head}")
