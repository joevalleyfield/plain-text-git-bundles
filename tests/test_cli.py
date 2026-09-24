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


def test_cli_from_bundle_and_to_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_a = _setup_test_repo(tmp_path / "repo_a")
    for i in range(10):
        (Path(repo_a) / f"file_{i}.txt").write_text(f"content {i}\n" + "ctx\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_a, check=True)
    subprocess.run(["git", "commit", "-m", "Commit delta 1"], cwd=repo_a, check=True)

    (Path(repo_a) / "file_0.txt").write_text("mod\n" + "ctx\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_a, check=True)
    subprocess.run(["git", "commit", "-m", "Commit delta 2"], cwd=repo_a, check=True)

    # 1. Convert bundle with prerequisites and deltas using --repo
    bundle_file = tmp_path / "test.bundle"
    subprocess.run(
        ["git", "bundle", "create", str(bundle_file), "HEAD~2..feature"],
        cwd=repo_a,
        check=True,
        capture_output=True,
    )

    ptbundle_dir = tmp_path / "ptbundle_out"
    code_from = main(
        [
            "--repo",
            str(repo_a),
            "from-bundle",
            str(bundle_file),
            "-o",
            str(ptbundle_dir),
            "--whitelist-ext",
            "png,jpg",
        ]
    )
    assert code_from == 0
    captured_from = capsys.readouterr()
    assert "Converted Git bundle" in captured_from.out
    assert "Trees (delta):" in captured_from.out
    assert "Blobs (delta):" in captured_from.out

    # Convert back to bundle with --repo
    recreated_bundle = tmp_path / "recreated.bundle"
    code_to = main(
        [
            "--repo",
            str(repo_a),
            "to-bundle",
            str(ptbundle_dir),
            "-o",
            str(recreated_bundle),
        ]
    )
    assert code_to == 0
    captured_to = capsys.readouterr()
    assert "Converted ptbundle at" in captured_to.out
    assert recreated_bundle.is_file()

    # 2. Self-contained bundle without valid --repo (tests repo_path = None fallback in both commands)
    root_bundle = tmp_path / "root.bundle"
    subprocess.run(
        ["git", "bundle", "create", str(root_bundle), "main"],
        cwd=repo_a,
        check=True,
        capture_output=True,
    )
    non_repo_dir = tmp_path / "non_repo"
    non_repo_dir.mkdir()
    ptbundle_root = tmp_path / "ptbundle_root"
    code_root = main(
        [
            "--repo",
            str(non_repo_dir),
            "from-bundle",
            str(root_bundle),
            "-o",
            str(ptbundle_root),
        ]
    )
    assert code_root == 0

    recreated_root_bundle = tmp_path / "recreated_root.bundle"
    code_to_root = main(
        [
            "--repo",
            str(non_repo_dir),
            "to-bundle",
            str(ptbundle_root),
            "-o",
            str(recreated_root_bundle),
        ]
    )
    assert code_to_root == 0


def test_cli_bundle_bridge_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code_from = main(
        ["from-bundle", str(tmp_path / "nonexistent.bundle"), "-o", str(tmp_path / "out")]
    )
    assert code_from == 1
    captured_from = capsys.readouterr()
    assert "Error converting from Git bundle" in captured_from.err

    code_to = main(
        ["to-bundle", str(tmp_path / "nonexistent_ptbundle"), "-o", str(tmp_path / "out.bundle")]
    )
    assert code_to == 1
    captured_to = capsys.readouterr()
    assert "Error converting to Git bundle" in captured_to.err


def test_cli_pack_thin_and_no_thin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_a = _setup_test_repo(tmp_path / "repo_a")

    # 1. pack with explicit --thin
    bundle_thin = tmp_path / "bundle_thin"
    code_thin = main(
        ["--repo", str(repo_a), "pack", "main..feature", "-o", str(bundle_thin), "--thin"]
    )
    assert code_thin == 0
    assert (bundle_thin / "manifest.txt").is_file()

    # 2. pack with explicit --no-thin
    bundle_thick = tmp_path / "bundle_thick"
    code_thick = main(
        ["--repo", str(repo_a), "pack", "main..feature", "-o", str(bundle_thick), "--no-thin"]
    )
    assert code_thick == 0
    assert (bundle_thick / "manifest.txt").is_file()
    assert len(list(bundle_thick.rglob("*.delta.txt"))) == 0

    # 3. from-bundle with --no-thin
    git_bundle = tmp_path / "cli_test.bundle"
    subprocess.run(["git", "bundle", "create", str(git_bundle), "main"], cwd=repo_a, check=True)
    bundle_converted = tmp_path / "bundle_converted"
    code_from = main(
        [
            "--repo",
            str(repo_a),
            "from-bundle",
            str(git_bundle),
            "-o",
            str(bundle_converted),
            "--no-thin",
        ]
    )
    assert code_from == 0
    assert (bundle_converted / "manifest.txt").is_file()
