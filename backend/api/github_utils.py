"""
GitHub API Utilities

Handles interaction with the GitHub API for repository scanning:
- list_user_repos(): Fetches the authenticated user's repositories for browsing
- get_repo_file_tree(): Returns the filtered file tree for a repository
- fetch_github_repo(): Downloads selected files from a repository for analysis

Design decision: We use the GitHub Trees API (recursive) instead of the
Contents API because it fetches the entire repo structure in a single API call,
which is much faster and uses fewer rate-limit credits than walking directories
one at a time with the Contents API.
"""

import os
import base64
import requests
import tempfile
from static_analyzer.analyzer import EXTENSION_TO_LANGUAGE
from api.zip_utils import MAX_BATCH_FILES

GITHUB_API_BASE = "https://api.github.com"

# Directories to skip during repo scanning — these never contain
# user-written source code worth reviewing
IGNORED_DIRECTORIES = {
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "env", "dist", "build", ".next", ".cache", "vendor",
    "target", "bin", "obj", ".idea", ".vscode",
}


def _github_headers(access_token: str) -> dict:
    """Build standard headers for GitHub API requests."""
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _is_supported_file(path: str) -> bool:
    """Check if a file path has a supported extension and isn't in an ignored directory."""
    # Check ignored directories
    parts = path.split("/")
    if any(part in IGNORED_DIRECTORIES for part in parts):
        return False

    # Check supported extension
    _, ext = os.path.splitext(path)
    return ext.lower() in EXTENSION_TO_LANGUAGE


def parse_repo_url(url: str) -> str:
    """Extract owner/repo from a GitHub URL or shorthand.

    Accepts:
        - 'owner/repo'
        - 'https://github.com/owner/repo'
        - 'https://github.com/owner/repo/tree/main/...'

    Returns:
        A string in 'owner/repo' format.

    Raises:
        ValueError: If the input doesn't match any known format.
    """
    url = url.strip().rstrip("/")

    if url.startswith("http"):
        parts = url.split("github.com/")
        if len(parts) == 2:
            repo_parts = parts[1].split("/")
            if len(repo_parts) >= 2:
                return f"{repo_parts[0]}/{repo_parts[1]}"

    # Assume it's already "owner/repo"
    parts = url.split("/")
    if len(parts) == 2 and all(parts):
        return url

    raise ValueError(
        "Invalid GitHub repository format. "
        "Use 'owner/repo' or 'https://github.com/owner/repo'."
    )


def list_user_repos(
    access_token: str,
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    sort: str = "updated",
) -> tuple[list[dict], int, str]:
    """Fetch the authenticated user's GitHub repositories.

    Uses the GitHub API endpoint GET /user/repos which returns repos
    the authenticated user has access to (owned, collaborated, org member).

    Args:
        access_token: GitHub OAuth token with at least read:user scope.
        page: Page number (1-indexed).
        per_page: Results per page (max 100).
        search: Optional search/filter string for repo name.
        sort: Sort field ('updated', 'pushed', 'full_name').

    Returns:
        (repos_list, total_count, error_message)
        repos_list: List of repo dicts with relevant fields.
        total_count: Approximate total count (GitHub doesn't give exact totals).
        error_message: None on success, string on error.
    """
    headers = _github_headers(access_token)
    per_page = min(per_page, 100)

    params = {
        "per_page": per_page,
        "page": page,
        "sort": sort,
        "direction": "desc",
        "type": "all",  # owned + collaborated + org member repos
    }

    try:
        resp = requests.get(
            f"{GITHUB_API_BASE}/user/repos",
            headers=headers,
            params=params,
            timeout=10,
        )

        if resp.status_code == 401:
            return [], 0, "GitHub token expired or invalid. Please re-authenticate."
        if resp.status_code != 200:
            return [], 0, f"GitHub API error: {resp.status_code}"

        all_repos = resp.json()

        # Client-side filter by search term (GitHub's /user/repos doesn't have
        # a built-in search param, so we filter after fetching)
        if search:
            search_lower = search.lower()
            all_repos = [
                r for r in all_repos
                if search_lower in r.get("full_name", "").lower()
                or search_lower in (r.get("description") or "").lower()
            ]

        # Extract only the fields the frontend needs
        repos = []
        for r in all_repos:
            repos.append({
                "full_name": r["full_name"],
                "name": r["name"],
                "owner": r["owner"]["login"],
                "private": r["private"],
                "language": r.get("language"),
                "description": r.get("description", ""),
                "stargazers_count": r.get("stargazers_count", 0),
                "updated_at": r.get("updated_at"),
                "default_branch": r.get("default_branch", "main"),
            })

        # GitHub uses Link headers for pagination — check if there are more pages
        link_header = resp.headers.get("Link", "")
        has_next = 'rel="next"' in link_header

        return repos, has_next, None

    except requests.exceptions.Timeout:
        return [], 0, "GitHub API timed out. Please try again."
    except Exception as e:
        return [], 0, f"Error fetching repositories: {str(e)}"


def get_repo_file_tree(
    repo_path: str,
    access_token: str,
) -> tuple[list[dict], int, int, str]:
    """Fetch and filter the file tree of a GitHub repository.

    Returns the full tree of supported files without downloading their content.
    The frontend uses this to display a file picker when the repo has >30 files.

    Args:
        repo_path: Repository in 'owner/repo' format.
        access_token: GitHub OAuth token.

    Returns:
        (files, total_files, skipped_count, error)
        files: List of dicts with {path, language, size} for supported files.
        total_files: Total number of files in the repo (before filtering).
        skipped_count: Number of files skipped (unsupported extension or ignored dir).
        error: None on success, string on error.
    """
    headers = _github_headers(access_token)

    # Get repo info to find the default branch
    resp = requests.get(
        f"{GITHUB_API_BASE}/repos/{repo_path}",
        headers=headers,
        timeout=10,
    )

    if resp.status_code == 404:
        return [], 0, 0, "Repository not found or you don't have access."
    if resp.status_code in (401, 403):
        return [], 0, 0, "Unauthorized. Your GitHub token may be expired or lack the 'repo' scope."
    if resp.status_code != 200:
        return [], 0, 0, f"GitHub API error: {resp.status_code}"

    default_branch = resp.json().get("default_branch", "main")

    # Fetch the recursive tree — one API call gets the entire repo structure
    tree_resp = requests.get(
        f"{GITHUB_API_BASE}/repos/{repo_path}/git/trees/{default_branch}?recursive=1",
        headers=headers,
        timeout=15,
    )

    if tree_resp.status_code != 200:
        return [], 0, 0, f"Failed to fetch repository tree: {tree_resp.status_code}"

    tree_data = tree_resp.json()

    if tree_data.get("truncated"):
        return [], 0, 0, (
            "Repository is too large (tree truncated by GitHub). "
            "Please upload a ZIP of the specific directory you want to review."
        )

    # Filter the tree
    supported_files = []
    total_files = 0
    skipped_count = 0

    for item in tree_data.get("tree", []):
        if item["type"] != "blob":
            continue

        total_files += 1

        if _is_supported_file(item["path"]):
            _, ext = os.path.splitext(item["path"])
            supported_files.append({
                "path": item["path"],
                "language": EXTENSION_TO_LANGUAGE[ext.lower()],
                "size": item.get("size", 0),
                "sha": item["sha"],
            })
        else:
            skipped_count += 1

    return supported_files, total_files, skipped_count, None


def fetch_github_repo(
    repo_url: str,
    access_token: str,
    selected_files: list[str] = None,
) -> tuple[str, list[dict], int, str]:
    """Download files from a GitHub repository for analysis.

    If selected_files is provided, only those files are downloaded (the frontend
    lets users pick which files to scan when a repo exceeds 30 supported files).
    If selected_files is None, all supported files are downloaded (capped at 30).

    Args:
        repo_url: Repository URL or 'owner/repo' shorthand.
        access_token: GitHub OAuth token.
        selected_files: Optional list of file paths to download. If None, uses all.

    Returns:
        (temp_dir, files_to_analyze, skipped_count, error)
    """
    try:
        repo_path = parse_repo_url(repo_url)
    except ValueError as e:
        return None, None, 0, str(e)

    headers = _github_headers(access_token)

    # Get the file tree
    all_files, total_files, skipped_count, error = get_repo_file_tree(
        repo_path, access_token
    )

    if error:
        return None, None, 0, error

    if not all_files:
        return None, None, 0, "No supported source files found in the repository."

    # Determine which files to download
    if selected_files:
        # User picked specific files from the file tree picker
        selected_set = set(selected_files)
        files_to_download = [f for f in all_files if f["path"] in selected_set]

        if len(files_to_download) > MAX_BATCH_FILES:
            return None, None, 0, (
                f"Too many files selected ({len(files_to_download)}). "
                f"Maximum is {MAX_BATCH_FILES} files per scan."
            )
    else:
        # No selection — take first 30 supported files
        files_to_download = all_files[:MAX_BATCH_FILES]

    # Download each file's content via the Git Blobs API
    temp_dir = tempfile.mkdtemp(prefix="codelens_github_")
    files_to_analyze = []

    try:
        for file_info in files_to_download:
            blob_url = f"{GITHUB_API_BASE}/repos/{repo_path}/git/blobs/{file_info['sha']}"
            blob_resp = requests.get(blob_url, headers=headers, timeout=10)

            if blob_resp.status_code != 200:
                skipped_count += 1
                continue

            blob_data = blob_resp.json()
            content = blob_data.get("content", "")
            encoding = blob_data.get("encoding", "")

            if encoding == "base64":
                try:
                    decoded_content = base64.b64decode(content).decode("utf-8")
                except UnicodeDecodeError:
                    skipped_count += 1
                    continue  # Binary file that slipped through

            else:
                decoded_content = content

            # Skip files over 500KB
            if len(decoded_content.encode("utf-8")) > 500 * 1024:
                skipped_count += 1
                continue

            target_path = os.path.join(temp_dir, file_info["path"].replace("/", os.sep))
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(decoded_content)

            files_to_analyze.append({
                "relative_path": file_info["path"],
                "absolute_path": target_path,
                "language": file_info["language"],
            })

        if not files_to_analyze:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, None, 0, "No files could be downloaded from the repository."

        return temp_dir, files_to_analyze, skipped_count, None

    except Exception as e:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, 0, f"Error fetching files: {str(e)}"
