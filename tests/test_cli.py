"""Tests for the ptbundle CLI entrypoint."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ptbundle import __version__
from ptbundle.cli import main


def _setup_test_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "CLI Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "cli@example.com"], cwd=path, check=True)
    (path / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "file.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True)

    subprocess.run(["git", "checkout", "-b", "feature"], cwd=path, check=True)
    (path / "feature.txt").write_text("feature content\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "Feature commit"], cwd=path, check=True)
    return path


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage: ptbundle" in captured.out
    assert "pack" in captured.out
    assert "unpack" in captured.out


def test_cli_main_default_argv(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["ptbundle"]):
        code = main()
    assert code == 0
    captured = capsys.readouterr()
    assert "usage: ptbundle" in captured.out


def test_cli_pack_and_unpack_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_a = _setup_test_repo(tmp_path / "repo_a")
    bundle_dir = tmp_path / "bundle"

    # Pack
    code_pack = main(
        [
            "--repo",
            str(repo_a),
            "pack",
            "main..feature",
            "-o",
            str(bundle_dir),
            "--whitelist-ext",
            "png,jpg",
        ]
    )
    assert code_pack == 0
    captured_pack = capsys.readouterr()
    assert "Created ptbundle" in captured_pack.out
    assert "Commits: 1" in captured_pack.out

    # Unpack into clone
    repo_b = tmp_path / "repo_b"
    subprocess.run(["git", "clone", str(repo_a), str(repo_b)], capture_output=True, check=True)
    code_unpack = main(["--repo", str(repo_b), "unpack", str(bundle_dir)])
    assert code_unpack == 0
    captured_unpack = capsys.readouterr()
    assert "Successfully unpacked bundle" in captured_unpack.out
    assert "Updated ref: refs/heads/feature" in captured_unpack.out


def test_cli_pack_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()

    code = main(
        ["--repo", str(not_a_repo), "pack", "main..feature", "-o", str(tmp_path / "bundle")]
    )
    assert code == 1
    captured = capsys.readouterr()
    assert "Error packing bundle" in captured.err


def test_cli_unpack_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()

    code = main(["--repo", str(not_a_repo), "unpack", str(tmp_path / "nonexistent")])
    assert code == 1
    captured = capsys.readouterr()
    assert "Error unpacking bundle" in captured.err


def test_cli_pack_with_deltas(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_dir = tmp_path / "cli_delta_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    for i in range(10):
        (repo_dir / f"f_{i}.txt").write_text(f"line {i}\n" + "ctx\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "C1"], cwd=repo_dir, check=True)

    (repo_dir / "f_0.txt").write_text("mod 1\n" + "ctx\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "C2"], cwd=repo_dir, check=True)

    (repo_dir / "f_0.txt").write_text("mod 2\n" + "ctx\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "C3"], cwd=repo_dir, check=True)

    bundle_dir = tmp_path / "cli_delta_bundle"
    code = main(["--repo", str(repo_dir), "pack", "HEAD~2..HEAD", "-o", str(bundle_dir)])
    assert code == 0
    captured = capsys.readouterr()
    assert "Trees (delta):" in captured.out
    assert "Blobs (delta):" in captured.out
