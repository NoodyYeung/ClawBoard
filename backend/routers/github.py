"""GitHub API — stable endpoints for PR creation, branch management, and repo info.

Claude Code and OpenClaw skills call these endpoints instead of relying on `gh` CLI
which may fail due to auth/path issues inside dispatched environments.

All endpoints require GITHUB_TOKEN to be set in the API container's environment.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.github_service import GitHubService, GitHubServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/github", tags=["github"])


# ---- Request / Response schemas ----

class CreatePRRequest(BaseModel):
    repo: str  # "owner/repo"
    head: str  # source branch
    base: str = "main"
    title: str
    body: str = ""
    draft: bool = False


class PRResponse(BaseModel):
    number: int
    html_url: str
    state: str
    title: str
    head_branch: str
    base_branch: str
    user: str
    created_at: str
    merged: bool = False
    mergeable: Optional[bool] = None


class MergePRRequest(BaseModel):
    merge_method: str = "squash"  # merge | squash | rebase
    commit_title: Optional[str] = None


class CreateBranchRequest(BaseModel):
    repo: str
    branch_name: str
    from_branch: str = "main"


class BranchResponse(BaseModel):
    name: str
    sha: str


class RepoResponse(BaseModel):
    full_name: str
    default_branch: str
    private: bool
    html_url: str


class CompareResponse(BaseModel):
    ahead_by: int
    behind_by: int
    total_commits: int
    files_changed: int
    files: list[dict]


# ---- helpers ----

def _get_service() -> GitHubService:
    try:
        return GitHubService()
    except GitHubServiceError as exc:
        raise HTTPException(500, f"GitHub not configured: {exc.message}")


def _pr_to_response(pr: dict) -> PRResponse:
    return PRResponse(
        number=pr["number"],
        html_url=pr["html_url"],
        state=pr["state"],
        title=pr["title"],
        head_branch=pr["head"]["ref"],
        base_branch=pr["base"]["ref"],
        user=pr["user"]["login"],
        created_at=pr["created_at"],
        merged=pr.get("merged", False),
        mergeable=pr.get("mergeable"),
    )


# ============================================================
# Pull Request endpoints
# ============================================================

@router.post("/pr", response_model=PRResponse, status_code=201)
async def create_pr(body: CreatePRRequest):
    """Create a pull request on GitHub.

    Usage from Claude Code:
        curl -X POST http://localhost:8100/api/github/pr \\
          -H 'Content-Type: application/json' \\
          -d '{"repo":"owner/repo","head":"feat/branch","title":"feat: description"}'
    """
    gh = _get_service()
    try:
        pr = await gh.create_pr(
            repo=body.repo,
            head=body.head,
            base=body.base,
            title=body.title,
            body=body.body,
            draft=body.draft,
        )
        logger.info("PR #%d created: %s", pr["number"], pr["html_url"])
        return _pr_to_response(pr)
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


@router.get("/pr/{repo_owner}/{repo_name}", response_model=list[PRResponse])
async def list_prs(
    repo_owner: str,
    repo_name: str,
    state: str = Query("open", regex="^(open|closed|all)$"),
    head: Optional[str] = None,
):
    """List pull requests for a repository."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        prs = await gh.list_prs(repo=repo, state=state, head=head)
        return [_pr_to_response(pr) for pr in prs]
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


@router.get("/pr/{repo_owner}/{repo_name}/{pr_number}", response_model=PRResponse)
async def get_pr(repo_owner: str, repo_name: str, pr_number: int):
    """Get a single pull request."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        pr = await gh.get_pr(repo=repo, pr_number=pr_number)
        return _pr_to_response(pr)
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


@router.post("/pr/{repo_owner}/{repo_name}/{pr_number}/merge", response_model=dict)
async def merge_pr(repo_owner: str, repo_name: str, pr_number: int, body: MergePRRequest):
    """Merge a pull request."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        result = await gh.merge_pr(
            repo=repo,
            pr_number=pr_number,
            merge_method=body.merge_method,
            commit_title=body.commit_title,
        )
        return result
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


# ============================================================
# Branch endpoints
# ============================================================

@router.post("/branch", response_model=BranchResponse, status_code=201)
async def create_branch(body: CreateBranchRequest):
    """Create a new branch from an existing one.

    Usage from Claude Code:
        curl -X POST http://localhost:8100/api/github/branch \\
          -H 'Content-Type: application/json' \\
          -d '{"repo":"owner/repo","branch_name":"feat/new","from_branch":"main"}'
    """
    gh = _get_service()
    try:
        ref = await gh.create_branch(repo=body.repo, branch_name=body.branch_name, from_branch=body.from_branch)
        return BranchResponse(name=body.branch_name, sha=ref["object"]["sha"])
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


@router.get("/branch/{repo_owner}/{repo_name}", response_model=list[BranchResponse])
async def list_branches(repo_owner: str, repo_name: str):
    """List branches for a repository."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        branches = await gh.list_branches(repo=repo)
        return [BranchResponse(name=b["name"], sha=b["commit"]["sha"]) for b in branches]
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


@router.delete("/branch/{repo_owner}/{repo_name}")
async def delete_branch(
    repo_owner: str,
    repo_name: str,
    branch_name: str = Query(..., description="Branch name to delete"),
):
    """Delete a branch after merge."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        await gh.delete_branch(repo=repo, branch_name=branch_name)
        return {"status": "deleted", "branch": branch_name}
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


# ============================================================
# Repository endpoints
# ============================================================

@router.get("/repo/{repo_owner}/{repo_name}", response_model=RepoResponse)
async def get_repo(repo_owner: str, repo_name: str):
    """Get repository info."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        r = await gh.get_repo(repo=repo)
        return RepoResponse(
            full_name=r["full_name"],
            default_branch=r["default_branch"],
            private=r["private"],
            html_url=r["html_url"],
        )
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")


@router.get("/compare/{repo_owner}/{repo_name}", response_model=CompareResponse)
async def compare_branches(
    repo_owner: str,
    repo_name: str,
    base: str = Query(..., description="Base branch name"),
    head: str = Query(..., description="Head branch name"),
):
    """Compare two branches — shows ahead/behind and changed files."""
    gh = _get_service()
    repo = f"{repo_owner}/{repo_name}"
    try:
        diff = await gh.compare_branches(repo=repo, base=base, head=head)
        return CompareResponse(
            ahead_by=diff.get("ahead_by", 0),
            behind_by=diff.get("behind_by", 0),
            total_commits=diff.get("total_commits", 0),
            files_changed=len(diff.get("files", [])),
            files=[{"filename": f["filename"], "status": f["status"], "changes": f["changes"]} for f in diff.get("files", [])],
        )
    except GitHubServiceError as exc:
        raise HTTPException(exc.status_code or 500, detail=f"GitHub error: {exc.message}. {exc.detail}")
