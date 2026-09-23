"""Unit and integration tests for bundle packing orchestrator."""

import subprocess
from pathlib import Path

from ptbundle.pack import pack_bundle
from ptbundle.policy import WhitelistPolicy
from ptbundle.repo import GitRepo


def _setup_repo(path: Path) -> tuple[GitRepo, str, str]:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Pack Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "pack@example.com"], cwd=path, check=True)

    # Base commit
    (path / "README.md").write_text("# Project\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True)
    base_oid = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )

    # Feature branch with text, whitelisted binary, and quarantined binary
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=path, check=True)
    (path / "script.py").write_text("print('hello')\n")
    (path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nvalid_png_payload")
    (path / "tool.bin").write_bytes(b"\x00\x01\x02binary_payload")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "Add feature assets"], cwd=path, check=True)
    tip_oid = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )

    repo = GitRepo.discover(path)
    return repo, base_oid, tip_oid


def test_pack_bundle_mixed_content(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, base_oid, tip_oid = _setup_repo(repo_dir)

    bundle_dir = tmp_path / "bundle"
    policy = WhitelistPolicy.from_extensions(["png"])

    manifest = pack_bundle(repo, "main..feature", bundle_dir, whitelist_policy=policy)

    assert manifest.version == 1
    assert manifest.hash_algo == "sha1"
    assert len(manifest.prerequisites) == 1
    assert manifest.prerequisites[0].oid == base_oid
    assert len(manifest.refs) == 1
    assert manifest.refs[0].name == "refs/heads/feature"
    assert manifest.refs[0].oid == tip_oid

    assert manifest.metrics.commits == 1
    assert manifest.metrics.trees >= 1
    assert manifest.metrics.blobs_text >= 1
    assert manifest.metrics.blobs_binary == 1
    assert manifest.metrics.blobs_quarantined == 1

    # Verify filesystem layout
    assert (bundle_dir / "manifest.txt").is_file()
    assert (bundle_dir / "commits").is_dir()
    assert (bundle_dir / "trees").is_dir()
    assert (bundle_dir / "blobs").is_dir()
    assert (bundle_dir / "quarantine").is_dir()
    assert (bundle_dir / "quarantine" / "quarantine-manifest.txt").is_file()

    # Verify zero null bytes in tree files
    for tree_file in (bundle_dir / "trees").rglob("*.txt"):
        content = tree_file.read_bytes()
        assert b"\x00" not in content
