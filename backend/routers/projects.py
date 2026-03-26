"""Project Explorer API — browse & manage ClaudeCodeProject sub-projects."""

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects", tags=["projects"])

# ---- Configuration ----

# The ClaudeCodeProject root directory (mounted into the container)
PROJECTS_ROOT = Path(os.environ.get(
    "CLAUDE_PROJECTS_PATH",
    "/projects",
))

TEMPLATES_DIR = PROJECTS_ROOT / "_templates"

# Folders/files to skip when listing
SKIP_NAMES = {"__pycache__", ".git", "node_modules", ".venv", ".env", ".pytest_cache"}
SKIP_PREFIXES = (".", "_")


# ---- Schemas ----

class ProjectSummary(BaseModel):
    name: str
    path: str
    description: str = ""
    has_docker_compose: bool = False
    has_dockerfile: bool = False
    has_readme: bool = False
    has_claude_md: bool = False
    services: list[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    file_count: int = 0
    dir_count: int = 0
    pr_policy: str = "require_pr"


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified: Optional[str] = None
    children: Optional[list["FileNode"]] = None


class FileContent(BaseModel):
    path: str
    name: str
    content: str
    size: int
    modified: Optional[str] = None
    language: str = "text"


class ScaffoldRequest(BaseModel):
    name: str
    description: str = ""
    include_db: bool = True
    include_redis: bool = False
    python_deps: list[str] = []


class ScaffoldResponse(BaseModel):
    name: str
    path: str
    files_created: int
    message: str


# ---- Helpers ----

def _guess_language(filename: str) -> str:
    """Guess the code language from the file extension."""
    ext_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".js": "javascript",
        ".jsx": "javascriptreact",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
        ".md": "markdown",
        ".css": "css",
        ".html": "html",
        ".dockerfile": "dockerfile",
        ".env": "dotenv",
        ".txt": "text",
        ".cfg": "ini",
        ".ini": "ini",
        ".xml": "xml",
        ".csv": "csv",
    }
    name_lower = filename.lower()
    if name_lower == "dockerfile":
        return "dockerfile"
    if name_lower in (".env", ".env.example", ".env.local"):
        return "dotenv"
    if name_lower in ("makefile", "gnumakefile"):
        return "makefile"
    ext = os.path.splitext(filename)[1].lower()
    return ext_map.get(ext, "text")


def _is_text_file(filepath: Path) -> bool:
    """Check if a file is likely a text file (not binary)."""
    text_exts = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml",
        ".toml", ".sql", ".sh", ".bash", ".md", ".css", ".html", ".txt",
        ".cfg", ".ini", ".xml", ".csv", ".env", ".example", ".lock",
        ".gitignore", ".dockerignore",
    }
    name = filepath.name.lower()
    if name in ("dockerfile", "makefile", "gnumakefile", ".gitignore", ".dockerignore", ".env", ".env.example"):
        return True
    ext = filepath.suffix.lower()
    return ext in text_exts


def _get_mtime_iso(p: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _count_files_dirs(root: Path) -> tuple[int, int]:
    """Count files and directories recursively, skipping hidden/special dirs."""
    file_count = 0
    dir_count = 0
    for item in root.rglob("*"):
        # Skip items inside hidden/special directories
        parts = item.relative_to(root).parts
        if any(p in SKIP_NAMES or p.startswith(".") for p in parts):
            continue
        if item.is_file():
            file_count += 1
        elif item.is_dir():
            dir_count += 1
    return file_count, dir_count


def _parse_docker_compose_services(project_dir: Path) -> list[str]:
    """Extract service names from docker-compose.yml."""
    dc_path = project_dir / "docker-compose.yml"
    if not dc_path.exists():
        return []
    try:
        content = dc_path.read_text()
        # Simple regex to find service names under 'services:'
        in_services = False
        services = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("services:"):
                in_services = True
                continue
            if in_services:
                if line and not line[0].isspace() and not stripped.startswith("#"):
                    break  # Left the services block
                match = re.match(r"^  (\w[\w-]*):", line)
                if match:
                    svc = match.group(1)
                    if not svc.startswith("#"):
                        services.append(svc)
        return services
    except Exception:
        return []


def _read_clawboard_config(project_dir: Path) -> dict:
    """Read .clawboard.json from a project directory, returning defaults on error."""
    config_path = project_dir / ".clawboard.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _extract_description(project_dir: Path) -> str:
    """Try to extract a description from README.md or CLAUDE.md."""
    for fname in ("README.md", "CLAUDE.md"):
        fpath = project_dir / fname
        if fpath.exists():
            try:
                content = fpath.read_text()
                # Look for a line after the first heading
                lines = content.strip().splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("# "):
                        # Check if next non-empty line is a description
                        for j in range(i + 1, min(i + 5, len(lines))):
                            candidate = lines[j].strip()
                            if candidate and not candidate.startswith("#") and not candidate.startswith("```") and not candidate.startswith(">"):
                                return candidate[:200]
                            if candidate.startswith("> "):
                                return candidate[2:200]
                        break
            except Exception:
                pass
    return ""


def _build_file_tree(root: Path, base: Path, depth: int = 0, max_depth: int = 4) -> list[FileNode]:
    """Recursively build a file tree."""
    if depth > max_depth:
        return []

    nodes: list[FileNode] = []
    try:
        items = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return []

    for item in items:
        name = item.name
        if name in SKIP_NAMES or (name.startswith(".") and name not in (".env", ".env.example", ".gitignore", ".dockerignore")):
            continue

        rel_path = str(item.relative_to(base))

        if item.is_dir():
            children = _build_file_tree(item, base, depth + 1, max_depth)
            nodes.append(FileNode(
                name=name,
                path=rel_path,
                is_dir=True,
                modified=_get_mtime_iso(item),
                children=children,
            ))
        else:
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            nodes.append(FileNode(
                name=name,
                path=rel_path,
                is_dir=False,
                size=size,
                modified=_get_mtime_iso(item),
            ))

    return nodes


# ---- Simple TTL Cache ----
_projects_cache: list[dict] | None = None
_projects_cache_ts: float = 0
_CACHE_TTL = 120  # seconds


def _list_projects_sync() -> list[dict]:
    """Synchronous project listing — runs in a thread to avoid blocking the event loop."""
    if not PROJECTS_ROOT.exists():
        return []

    projects: list[dict] = []
    for item in sorted(PROJECTS_ROOT.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith(("_", ".")):
            continue

        config = _read_clawboard_config(item)
        projects.append(dict(
            name=item.name,
            path=str(item.relative_to(PROJECTS_ROOT)),
            description=_extract_description(item),
            has_docker_compose=(item / "docker-compose.yml").exists(),
            has_dockerfile=(item / "Dockerfile").exists(),
            has_readme=(item / "README.md").exists(),
            has_claude_md=(item / "CLAUDE.md").exists(),
            services=_parse_docker_compose_services(item),
            created_at=_get_mtime_iso(item),
            updated_at=_get_mtime_iso(item),
            file_count=0,  # computed lazily per-project
            dir_count=0,
            pr_policy=config.get("pr_policy", "require_pr"),
        ))

    return projects


# ---- Endpoints ----

@router.get("/names", response_model=list[str])
async def list_project_names():
    """Fast endpoint returning only project directory names (for dropdowns)."""
    if not PROJECTS_ROOT.exists():
        return []
    return sorted([
        item.name
        for item in PROJECTS_ROOT.iterdir()
        if item.is_dir() and not item.name.startswith(("_", "."))
    ])


@router.get("/", response_model=list[ProjectSummary])
async def list_projects():
    """List all projects in ClaudeCodeProject/."""
    global _projects_cache, _projects_cache_ts

    now = time.monotonic()
    if _projects_cache is not None and (now - _projects_cache_ts) < _CACHE_TTL:
        return [ProjectSummary(**p) for p in _projects_cache]

    data = await asyncio.to_thread(_list_projects_sync)
    _projects_cache = data
    _projects_cache_ts = now
    return [ProjectSummary(**p) for p in data]


@router.get("/{project_name}/tree", response_model=list[FileNode])
async def get_project_tree(project_name: str):
    """Get the file tree for a specific project."""
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    if project_name.startswith(("_", ".")):
        raise HTTPException(status_code=400, detail="Cannot access special directories")
    return await asyncio.to_thread(_build_file_tree, project_dir, project_dir)


@router.get("/{project_name}/file")
async def get_file_content(
    project_name: str,
    path: str = Query(..., description="Relative path within the project"),
):
    """Read a file's content from a project."""
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    file_path = (project_dir / path).resolve()
    # Security: ensure path doesn't escape the project directory
    if not str(file_path).startswith(str(project_dir.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not _is_text_file(file_path):
        raise HTTPException(status_code=400, detail="Binary files cannot be read")

    try:
        content = file_path.read_text(errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return FileContent(
        path=path,
        name=file_path.name,
        content=content,
        size=file_path.stat().st_size,
        modified=_get_mtime_iso(file_path),
        language=_guess_language(file_path.name),
    )


@router.post("/scaffold", response_model=ScaffoldResponse, status_code=201)
async def scaffold_project(req: ScaffoldRequest):
    """Scaffold a new project from the template."""
    # Validate name
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", req.name):
        raise HTTPException(
            status_code=400,
            detail="Project name must start with a letter and contain only letters, digits, hyphens, and underscores",
        )

    target = PROJECTS_ROOT / req.name
    if target.exists():
        raise HTTPException(status_code=409, detail=f"Project '{req.name}' already exists")

    if not TEMPLATES_DIR.exists():
        raise HTTPException(status_code=500, detail="Templates directory not found")

    # Copy template
    try:
        shutil.copytree(str(TEMPLATES_DIR), str(target))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to copy template: {e}")

    # Replace {{PROJECT_NAME}} placeholders
    files_created = 0
    for fpath in target.rglob("*"):
        if fpath.is_file() and _is_text_file(fpath):
            try:
                text = fpath.read_text()
                updated = text.replace("{{PROJECT_NAME}}", req.name)
                if req.description:
                    updated = updated.replace("<!-- Describe what this project does -->", req.description)
                    updated = updated.replace("<!-- What does this project do? -->", req.description)
                fpath.write_text(updated)
                files_created += 1
            except Exception:
                pass

    # Customise docker-compose: toggle DB / Redis
    dc_path = target / "docker-compose.yml"
    if dc_path.exists():
        dc_content = dc_path.read_text()
        dc_content = dc_content.replace("${PROJECT_NAME:-myproject}", f"${{PROJECT_NAME:-{req.name}}}")
        if req.include_redis:
            dc_content = dc_content.replace("  # redis:", "  redis:")
            dc_content = dc_content.replace("  #   image: redis:7-alpine", "    image: redis:7-alpine")
            dc_content = dc_content.replace("  #   container_name:", f"    container_name:")
            dc_content = dc_content.replace("  #   restart:", "    restart:")
            dc_content = dc_content.replace("  #   ports:", "    ports:")
            dc_content = dc_content.replace('  #     - "${REDIS_PORT:-6379}:6379"', '      - "${REDIS_PORT:-6379}:6379"')
            dc_content = dc_content.replace("  #   networks:", "    networks:")
            dc_content = dc_content.replace("  #     - app-network", "      - app-network")
        dc_path.write_text(dc_content)

    # Update requirements.txt with extra deps
    if req.python_deps:
        req_path = target / "requirements.txt"
        if req_path.exists():
            content = req_path.read_text()
            content += "\n# Additional dependencies\n"
            for dep in req.python_deps:
                content += f"{dep}\n"
            req_path.write_text(content)

    # Create .env from .env.example
    env_example = target / ".env.example"
    env_file = target / ".env"
    if env_example.exists() and not env_file.exists():
        env_content = env_example.read_text()
        env_content = env_content.replace("PROJECT_NAME=myproject", f"PROJECT_NAME={req.name}")
        env_file.write_text(env_content)

    return ScaffoldResponse(
        name=req.name,
        path=str(target.relative_to(PROJECTS_ROOT)),
        files_created=files_created,
        message=f"Project '{req.name}' scaffolded successfully from template",
    )


@router.delete("/{project_name}", status_code=204)
async def delete_project(project_name: str):
    """Delete a project directory (irreversible)."""
    if project_name.startswith(("_", ".")):
        raise HTTPException(status_code=400, detail="Cannot delete special directories")

    target = PROJECTS_ROOT / project_name
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    try:
        shutil.rmtree(str(target))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")


# ---- Project Settings ----

VALID_PR_POLICIES = {"require_pr", "direct_commit"}


class ProjectSettingsUpdate(BaseModel):
    pr_policy: str


@router.put("/{project_name}/settings")
async def update_project_settings(project_name: str, body: ProjectSettingsUpdate):
    """Update project-level settings (.clawboard.json)."""
    if project_name.startswith(("_", ".")):
        raise HTTPException(status_code=400, detail="Cannot access special directories")

    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    if body.pr_policy not in VALID_PR_POLICIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pr_policy. Must be one of: {', '.join(sorted(VALID_PR_POLICIES))}",
        )

    config_path = project_dir / ".clawboard.json"

    # Read existing config
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            config = {}

    config["pr_policy"] = body.pr_policy
    config["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

    try:
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write settings: {e}")

    # Invalidate cache
    global _projects_cache
    _projects_cache = None

    return config


# ---- Git Branch Endpoints ----

class GitBranchInfo(BaseModel):
    current: str
    branches: list[str]


class GitCheckoutRequest(BaseModel):
    branch: str


def _validate_project(project_name: str) -> Path:
    """Validate and return the project directory path."""
    if project_name.startswith(("_", ".")):
        raise HTTPException(status_code=400, detail="Cannot access special directories")
    project_dir = PROJECTS_ROOT / project_name
    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    if not (project_dir / ".git").exists():
        raise HTTPException(status_code=400, detail=f"Project '{project_name}' is not a git repository")
    return project_dir


@router.get("/{project_name}/git/branches", response_model=GitBranchInfo)
async def get_git_branches(project_name: str):
    """Get the current branch and list of all branches for a project."""
    project_dir = _validate_project(project_name)

    try:
        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        current = result.stdout.strip() if result.returncode == 0 else "unknown"

        # Get all local branches
        result = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        local_branches = [b.strip() for b in result.stdout.strip().splitlines() if b.strip()]

        # Get remote branches (excluding HEAD pointer)
        result = subprocess.run(
            ["git", "branch", "-r", "--format=%(refname:short)"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        remote_branches = []
        for b in result.stdout.strip().splitlines():
            b = b.strip()
            if b and "/HEAD" not in b:
                # Strip origin/ prefix for display
                short = b.split("/", 1)[1] if "/" in b else b
                if short not in local_branches:
                    remote_branches.append(b)

        all_branches = local_branches + remote_branches
        return GitBranchInfo(current=current, branches=all_branches)

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git command timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {e}")


@router.post("/{project_name}/git/checkout")
async def git_checkout(project_name: str, req: GitCheckoutRequest):
    """Checkout a branch in a project repository."""
    project_dir = _validate_project(project_name)

    branch = req.branch.strip()
    if not branch:
        raise HTTPException(status_code=400, detail="Branch name is required")

    # Security: prevent injection
    if any(c in branch for c in (";", "&", "|", "`", "$", "\n")):
        raise HTTPException(status_code=400, detail="Invalid branch name")

    try:
        # If it's a remote branch like "origin/feat-x", check it out as local tracking branch
        if "/" in branch and not branch.startswith("."):
            remote, _, local_name = branch.partition("/")
            # Check if local branch already exists
            check = subprocess.run(
                ["git", "rev-parse", "--verify", local_name],
                cwd=str(project_dir),
                capture_output=True, text=True, timeout=10,
            )
            if check.returncode == 0:
                # Local branch exists, just switch to it
                cmd = ["git", "checkout", local_name]
            else:
                # Create tracking branch
                cmd = ["git", "checkout", "-b", local_name, branch]
        else:
            cmd = ["git", "checkout", branch]

        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise HTTPException(status_code=400, detail=f"Checkout failed: {error_msg}")

        # Get the current branch name after checkout
        result2 = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        new_branch = result2.stdout.strip() if result2.returncode == 0 else branch

        return {"message": f"Switched to branch '{new_branch}'", "branch": new_branch}

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Git checkout timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {e}")
