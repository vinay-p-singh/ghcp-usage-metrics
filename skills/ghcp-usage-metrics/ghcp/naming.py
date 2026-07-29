"""Project identity: turning URIs, repo remotes and cwds into stable names."""
from __future__ import annotations

import os
from urllib.parse import unquote, urlparse

HOME = os.path.expanduser("~")


def uri_to_path(uri: str) -> str:
    """Convert a file:// URI (or plain path) to a local filesystem path."""
    if not uri:
        return ""
    if "://" not in uri:
        return uri
    p = urlparse(uri)
    path = unquote(p.path)
    # /C:/foo -> C:/foo
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path.replace("/", os.sep)


def project_name(path: str) -> str:
    """Human name from a folder path = its last segment."""
    if not path:
        return "(unknown)"
    base = os.path.basename(path.rstrip("\\/")) or path
    if base.endswith(".code-workspace"):
        base = base[: -len(".code-workspace")]
    return base


def repo_slug(repository: str) -> str:
    """Git remote -> 'owner/repo'. Handles https, git@, or a bare slug."""
    s = (repository or "").strip()
    if not s:
        return ""
    if s.endswith(".git"):
        s = s[: -len(".git")]
    if s.startswith("git@"):  # git@github.com:owner/repo
        s = s.split(":", 1)[-1]
    elif "://" in s:          # https://github.com/owner/repo
        s = urlparse(s).path.lstrip("/")
    return s.strip("/")


def is_junk_cwd(cwd: str) -> bool:
    """True for cwds that are not real projects (scratch/install/home)."""
    if not cwd:
        return True
    norm = cwd.replace("/", os.sep).lower()
    if os.sep + ".copilot" + os.sep + "chats" + os.sep in norm:
        return True
    if project_name(cwd) == "GitHub Copilot":
        return True
    if os.path.normcase(os.path.normpath(cwd)) == os.path.normcase(os.path.normpath(HOME)):
        return True
    return False


def _canon(name: str) -> str:
    """Grouping key: last path segment, case-insensitive."""
    return name.split("/")[-1].strip().lower()
