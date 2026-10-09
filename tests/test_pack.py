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


def test_pack_bundle_thin_and_no_thin(tmp_path: Path) -> None:
    repo_dir = tmp_path / "thin_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)

    # Base commit on main with multiple entries so tree text is ~1KB+
    for i in range(20):
        (repo_dir / f"entry_{i:02d}.txt").write_text("initial\n" + "context\n" * 50)
    sub_dir = repo_dir / "subdir"
    sub_dir.mkdir()
    for i in range(20):
        (sub_dir / f"subdoc_{i:02d}.txt").write_text("sub initial\n" + "context\n" * 50)
    (repo_dir / "large.txt").write_text("large initial line\n" + "context\n" * 50)
    (repo_dir / "bin_to_text.txt").write_bytes(b"\x00binary_initial\x00")
    (repo_dir / "small.txt").write_text("a")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=repo_dir, check=True)

    # Feature branch with 1 commit modifying large.txt and subdoc_00.txt, adding new_file.txt and new_dir/nested.txt
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo_dir, check=True)
    (sub_dir / "subdoc_00.txt").write_text("subdoc modified line\n" + "context\n" * 50)
    (repo_dir / "large.txt").write_text("large modified line\n" + "context\n" * 50)
    (repo_dir / "bin_to_text.txt").write_text("now pure text\n")
    (repo_dir / "small.txt").write_text("b")
    (repo_dir / "new_file.txt").write_text("completely brand new file\n")
    new_sub_dir = repo_dir / "new_dir"
    new_sub_dir.mkdir()
    (new_sub_dir / "nested.txt").write_text("nested content\n")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Feature commit (1 ahead)"], cwd=repo_dir, check=True)

    repo = GitRepo.discover(repo_dir)

    # 1. Thin pack (default): should delta-compress large.txt, subdoc.txt, and trees against main
    bundle_thin_dir = tmp_path / "thin_bundle"
    manifest_thin = pack_bundle(repo, "main..feature", bundle_thin_dir, thin=True)
    assert manifest_thin.metrics.commits == 1
    assert manifest_thin.metrics.blobs_delta >= 2
    assert manifest_thin.metrics.trees_delta >= 1

    # Verify that the delta files exist and their bases are NOT in the bundle
    blob_deltas = list((bundle_thin_dir / "blobs").rglob("*.delta.txt"))
    assert len(blob_deltas) >= 2
    for bd in blob_deltas:
        base_line = [l for l in bd.read_text().splitlines() if l.startswith("base: ")][0]
        base_oid = base_line.split()[1]
        base_fanout = base_oid[:2]
        base_rest = base_oid[2:]
        # Base is NOT bundled as a full blob
        assert not (bundle_thin_dir / "blobs" / base_fanout / f"{base_rest}.txt").exists()

    # 2. No-thin pack (opt-out): single commit cannot delta because no bases in range
    bundle_thick_dir = tmp_path / "thick_bundle"
    manifest_thick = pack_bundle(repo, "main..feature", bundle_thick_dir, thin=False)
    assert manifest_thick.metrics.commits == 1
    assert manifest_thick.metrics.blobs_delta == 0
    assert manifest_thick.metrics.trees_delta == 0
    assert len(list(bundle_thick_dir.rglob("*.delta.txt"))) == 0


def test_pack_bundle_to_zip(tmp_path: Path) -> None:
    import zipfile

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo, base_oid, tip_oid = _setup_repo(repo_dir)

    policy = WhitelistPolicy.from_extensions(["png"])
    zip_bundle = tmp_path / "bundle.zip"

    # Pack directly to .zip file
    manifest = pack_bundle(repo, "main..feature", zip_bundle, whitelist_policy=policy)

    assert manifest.version == 1
    assert manifest.refs[0].oid == tip_oid
    assert zip_bundle.is_file()

    with zipfile.ZipFile(zip_bundle, "r") as zf:
        names = zf.namelist()
        assert "manifest.txt" in names
        assert any(n.startswith("commits/") for n in names)
        assert any(n.startswith("trees/") for n in names)
        assert any(n.startswith("blobs/") for n in names)
        assert "quarantine/quarantine-manifest.txt" in names

    # Also test uncompressed zip
    zip_stored = tmp_path / "bundle_stored.zip"
    manifest_stored = pack_bundle(
        repo,
        "main..feature",
        zip_stored,
        whitelist_policy=policy,
        zip_compression=zipfile.ZIP_STORED,
    )
    assert manifest_stored.refs[0].oid == tip_oid
    assert zip_stored.is_file()
