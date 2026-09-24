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


def test_pack_bundle_with_deltas_and_no_delta(tmp_path: Path) -> None:
    repo_dir = tmp_path / "delta_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    # Base commit with 15 files
    for i in range(15):
        (repo_dir / f"doc_{i:02d}.txt").write_text(f"doc {i} content\n" + "context\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=repo_dir, check=True)

    # Commit 2: Modify doc_00.txt
    (repo_dir / "doc_00.txt").write_text("doc 00 updated line\n" + "context\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=repo_dir, check=True)

    # Commit 3: Modify doc_00.txt again
    (repo_dir / "doc_00.txt").write_text("doc 00 updated line 2\n" + "context\n" * 100)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 3"], cwd=repo_dir, check=True)

    repo = GitRepo.discover(repo_dir)

    # 1. Pack with delta compression (default)
    bundle_delta_dir = tmp_path / "bundle_with_deltas"
    manifest_delta = pack_bundle(repo, "HEAD~2..HEAD", bundle_delta_dir, enable_delta=True)
    assert manifest_delta.metrics.commits == 2
    assert manifest_delta.metrics.trees_delta > 0
    assert manifest_delta.metrics.blobs_delta > 0
    assert len(list(bundle_delta_dir.rglob("*.delta.txt"))) > 0

    # 2. Pack without delta compression
    bundle_no_delta_dir = tmp_path / "bundle_no_delta"
    manifest_no_delta = pack_bundle(repo, "HEAD~2..HEAD", bundle_no_delta_dir, enable_delta=False)
    assert manifest_no_delta.metrics.commits == 2
    assert manifest_no_delta.metrics.trees_delta == 0
    assert manifest_no_delta.metrics.blobs_delta == 0
    assert len(list(bundle_no_delta_dir.rglob("*.delta.txt"))) == 0


def test_pack_bundle_delta_fallbacks(tmp_path: Path) -> None:
    repo_dir = tmp_path / "fallback_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    # Commit 0 (outside range): root commit
    (repo_dir / "readme.txt").write_text("root")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 0"], cwd=repo_dir, check=True)

    # Commit 1 (in range, visited second): item.txt is text, small.txt is 1 char
    (repo_dir / "item.txt").write_text("now text")
    (repo_dir / "small.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=repo_dir, check=True)

    # Commit 2 (in range, visited first): item.txt becomes binary (so it populates last_seen first!), small.txt changes 1 char
    (repo_dir / "item.txt").write_bytes(b"\x00binary\x00")
    (repo_dir / "small.txt").write_text("y")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=repo_dir, check=True)

    repo = GitRepo.discover(repo_dir)
    bundle_dir = tmp_path / "fallback_bundle"
    policy = WhitelistPolicy.from_extensions(["txt"])
    manifest = pack_bundle(
        repo, "HEAD~2..HEAD", bundle_dir, whitelist_policy=policy, enable_delta=True
    )
    assert manifest.metrics.commits == 2
    assert manifest.metrics.blobs_delta == 0
