"""GitHub API client for checking releases."""

import json
import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ReleaseInfo:
    """Information about a GitHub release."""

    tag_name: str
    version: str  # Parsed from tag (e.g., "0.2.0" from "v0.2.0")
    name: str
    body: str  # Release notes (markdown)
    published_at: datetime
    html_url: str
    download_url: Optional[str] = None  # Direct download link for asset
    download_size: Optional[int] = None  # Size in bytes


class GitHubClient:
    """Client for GitHub Releases API."""

    API_BASE = "https://api.github.com"
    USER_AGENT = "TITrack-Updater"

    def __init__(self, owner: str, repo: str) -> None:
        """
        Initialize GitHub client.

        Args:
            owner: Repository owner (e.g., "astockman99")
            repo: Repository name (e.g., "TITrack")
        """
        self.owner = owner
        self.repo = repo

    def _make_request(self, endpoint: str) -> Optional[dict]:
        """Make a GET request to the GitHub API."""
        url = f"{self.API_BASE}{endpoint}"
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"GitHub API error: {e.code} {e.reason}")
            return None
        except urllib.error.URLError as e:
            print(f"Network error: {e.reason}")
            return None
        except Exception as e:
            print(f"Unexpected error fetching release: {e}")
            return None

    def get_latest_release(self) -> Optional[ReleaseInfo]:
        """
        Get information about the latest release.

        Returns:
            ReleaseInfo or None if request failed
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/releases/latest"
        data = self._make_request(endpoint)

        if not data:
            return None

        return self._parse_release(data)

    def get_release_by_tag(self, tag: str) -> Optional[ReleaseInfo]:
        """
        Get information about a specific release by tag.

        Args:
            tag: Release tag (e.g., "v0.2.0")

        Returns:
            ReleaseInfo or None if not found
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/releases/tags/{tag}"
        data = self._make_request(endpoint)

        if not data:
            return None

        return self._parse_release(data)

    def _parse_release(self, data: dict) -> ReleaseInfo:
        """Parse release data from GitHub API response."""
        tag_name = data.get("tag_name", "")
        # Extract version from tag (remove leading 'v' if present)
        version = tag_name.lstrip("v")

        platform_tokens = _release_asset_tokens()

        # Find a platform-appropriate ZIP asset
        download_url = None
        download_size = None
        assets = data.get("assets", [])
        for asset in assets:
            name = asset.get("name", "")
            lower_name = name.lower()
            if any(token in lower_name for token in platform_tokens) and lower_name.endswith(".zip"):
                download_url = asset.get("browser_download_url")
                download_size = asset.get("size")
                break

        # Parse publish date
        published_str = data.get("published_at", "")
        try:
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            published_at = datetime.now()

        return ReleaseInfo(
            tag_name=tag_name,
            version=version,
            name=data.get("name", tag_name),
            body=data.get("body", ""),
            published_at=published_at,
            html_url=data.get("html_url", ""),
            download_url=download_url,
            download_size=download_size,
        )


def _release_asset_tokens() -> tuple[str, ...]:
    """Return release asset name tokens for the current platform."""
    if sys.platform == "win32":
        return ("windows", "win-x64", "win_x64", "win64")
    if sys.platform.startswith("linux"):
        return ("linux",)
    if sys.platform == "darwin":
        return ("macos", "darwin")
    return (sys.platform,)


def parse_version(version_str: str) -> tuple[int, ...]:
    """
    Parse a version string into a tuple for comparison.

    Handles formats like "0.2.0", "v0.2.0", "0.2.0-beta.1"

    Args:
        version_str: Version string to parse

    Returns:
        Tuple of version components (major, minor, patch, ...)
    """
    # Remove leading 'v' if present
    version_str = version_str.lstrip("v")

    # Extract numeric parts only for comparison
    parts = re.split(r"[-+]", version_str)[0]  # Remove pre-release suffix
    components = []

    for part in parts.split("."):
        try:
            components.append(int(part))
        except ValueError:
            # Non-numeric part, try to extract leading digits
            match = re.match(r"(\d+)", part)
            if match:
                components.append(int(match.group(1)))
            else:
                components.append(0)

    return tuple(components)


def is_newer_version(current: str, latest: str) -> bool:
    """
    Check if latest version is newer than current.

    Args:
        current: Current version string
        latest: Latest version string

    Returns:
        True if latest is newer than current
    """
    current_tuple = parse_version(current)
    latest_tuple = parse_version(latest)

    return latest_tuple > current_tuple
