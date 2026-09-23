"""Unit and integration tests for bundle unpacking orchestrator."""

import subprocess
from pathlib import Path

import pytest

from ptbundle.pack import pack_bundle
from ptbundle.policy import WhitelistPolicy
from ptbundle.repo import GitRepo
from ptbundle.unpack import unpack_bundle


def _setup_repos(tmp_path: Path) -> tuple[GitRepo, GitRepo, Path]:
    repo_a_dir = tmp_path / "repo_a"
    repo_a_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_a_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester A"], cwd=repo_a_dir, check=True)
    subprocess.run(["git", "config", "user.email", "a@example.com"], cwd=repo_a_dir, check=True)

    (repo_a_dir / "base.txt").write_text("Base version\n")
    subprocess.run(["git", "add", "base.txt"], cwd=repo_a_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=repo_a_dir, check=True)

    # Clone Repo B from Repo A at base
    repo_b_dir = tmp_path / "repo_b"
    subprocess.run(
        ["git", "clone", str(repo_a_dir), str(repo_b_dir)], capture_output=True, check=True
    )

    # Feature branch in Repo A
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo_a_dir, check=True)
    (repo_a_dir / "new_feature.txt").write_text("Feature text\n")
    (repo_a_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nimage_payload")
    (repo_a_dir / "quarantined.bin").write_bytes(b"\x00\x01\x02disallowed")
    subprocess.run(["git", "add", "."], cwd=repo_a_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Feature commit"], cwd=repo_a_dir, check=True)

    repo_a = GitRepo.discover(repo_a_dir)
    repo_b = GitRepo.discover(repo_b_dir)
    bundle_dir = tmp_path / "bundle"
    return repo_a, repo_b, bundle_dir


def test_unpack_bundle_with_quarantine_roundtrip(tmp_path: Path) -> None:
    repo_a, repo_b, bundle_dir = _setup_repos(tmp_path)
    policy = WhitelistPolicy.from_extensions(["png"])

    # Pack bundle in Repo A
    pack_bundle(repo_a, "main..feature", bundle_dir, whitelist_policy=policy)

    # Unpacking into Repo B without sidechannel should fail because of quarantined.bin
    with pytest.raises(ValueError, match="requires 1 quarantined object"):
        unpack_bundle(repo_b, bundle_dir, sidechannel_dir=None)

    # Unpack with sidechannel pointing to bundle_dir/quarantine succeeds
    result = unpack_bundle(repo_b, bundle_dir, sidechannel_dir=bundle_dir / "quarantine")
    assert result.target_ref == "refs/heads/feature"
    assert result.objects_injected > 0

    # Verify repo_b has the feature branch and can checkout cleanly
    subprocess.run(["git", "checkout", "feature"], cwd=repo_b.root, capture_output=True, check=True)
    assert (repo_b.root / "new_feature.txt").read_text() == "Feature text\n"
    assert (repo_b.root / "logo.png").read_bytes() == b"\x89PNG\r\n\x1a\nimage_payload"
    assert (repo_b.root / "quarantined.bin").read_bytes() == b"\x00\x01\x02disallowed"

    # Verify git fsck is completely clean
    fsck_proc = repo_b.run_git(["fsck"])
    assert fsck_proc.returncode == 0

    # Idempotent re-unpack
    res2 = unpack_bundle(repo_b, bundle_dir, sidechannel_dir=bundle_dir / "quarantine")
    assert res2.target_ref == result.target_ref


def test_unpack_bundle_error_cases(tmp_path: Path) -> None:
    repo_a, repo_b, bundle_dir = _setup_repos(tmp_path)
    policy = WhitelistPolicy.from_extensions(["png", "bin"])  # no quarantine

    pack_bundle(repo_a, "main..feature", bundle_dir, whitelist_policy=policy)

    # 1. Missing manifest.txt
    with pytest.raises(FileNotFoundError, match="missing manifest.txt"):
        unpack_bundle(repo_b, tmp_path / "nonexistent_bundle")

    # 2. Corrupted commit file (OID mismatch)
    corrupted_bundle = tmp_path / "corrupted_bundle"
    subprocess.run(["cp", "-r", str(bundle_dir), str(corrupted_bundle)], check=True)
    for cfile in (corrupted_bundle / "commits").rglob("*.txt"):
        cfile.write_bytes(
            b"tree "
            + b"0" * 40
            + b"\nauthor A <a@b> 1 +0000\ncommitter B <b@b> 2 +0000\n\nmessage\n"
        )
        break
    with pytest.raises(ValueError, match="Commit OID mismatch"):
        unpack_bundle(repo_b, corrupted_bundle)

    # 3. Corrupted tree file (OID mismatch)
    corrupted_tree_bundle = tmp_path / "corrupted_tree_bundle"
    subprocess.run(["cp", "-r", str(bundle_dir), str(corrupted_tree_bundle)], check=True)
    for tfile in (corrupted_tree_bundle / "trees").rglob("*.txt"):
        tfile.write_text("100644 blob " + ("0" * 40) + "\tbad.txt\n")
        break
    with pytest.raises(ValueError, match="Tree OID mismatch"):
        unpack_bundle(repo_b, corrupted_tree_bundle)

    # 4. Corrupted blob file (OID mismatch)
    corrupted_blob_bundle = tmp_path / "corrupted_blob_bundle"
    subprocess.run(["cp", "-r", str(bundle_dir), str(corrupted_blob_bundle)], check=True)
    for bfile in (corrupted_blob_bundle / "blobs").rglob("*"):
        if bfile.is_file():
            bfile.write_bytes(b"corrupted blob data")
            break
    with pytest.raises(ValueError, match="Blob OID mismatch"):
        unpack_bundle(repo_b, corrupted_blob_bundle)

    # 5. Successful unpack of unquarantined bundle
    result = unpack_bundle(repo_b, bundle_dir)
    assert result.metrics.blobs_quarantined == 0
    assert result.target_ref == "refs/heads/feature"


def test_unpack_bundle_quarantine_without_manifest_file(tmp_path: Path) -> None:
    repo_a, repo_b, bundle_dir = _setup_repos(tmp_path)
    policy = WhitelistPolicy.from_extensions(["png"])  # quarantined.bin will be quarantined
    pack_bundle(repo_a, "main..feature", bundle_dir, whitelist_policy=policy)

    # Remove quarantine-manifest.txt from bundle/quarantine
    q_manifest = bundle_dir / "quarantine" / "quarantine-manifest.txt"
    q_manifest.unlink()

    # Unpack with sidechannel still succeeds because load_sidechannel_objects works with manifest=None
    result = unpack_bundle(repo_b, bundle_dir, sidechannel_dir=bundle_dir / "quarantine")
    assert result.objects_injected > 0


def test_unpack_bundle_missing_subdirectories(tmp_path: Path) -> None:
    repo_a, repo_b, _ = _setup_repos(tmp_path)
    base_oid = repo_a.run_git(["rev-parse", "main"]).stdout.decode().strip()

    # Minimal bundle with only manifest.txt (no commits/, trees/, blobs/ dirs)
    bundle_dir = tmp_path / "empty_bundle"
    bundle_dir.mkdir()
    manifest_content = (
        f"# ptbundle v1\nhash-algo sha1\n\nref refs/heads/empty {base_oid}\n\n"
        "# Summary Metrics\ncommits: 0\ntrees: 0\nblobs_text: 0\nblobs_binary: 0\nblobs_quarantined: 0\n"
    )
    (bundle_dir / "manifest.txt").write_text(manifest_content)

    result = unpack_bundle(repo_b, bundle_dir)
    assert result.objects_injected == 0
    assert result.target_ref == "refs/heads/empty"
