"""Shared pytest fixtures for ptbundle test suite."""

from __future__ import annotations

import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary initialized git repository."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    yield repo_dir
