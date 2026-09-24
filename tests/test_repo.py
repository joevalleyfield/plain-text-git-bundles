"""Integration and unit tests for Git repository interface and object I/O."""

import subprocess
from pathlib import Path

import pytest

from ptbundle.objects import GitCommit, GitObjectType
from ptbundle.repo import (
    GitRepo,
    discover_delta,
    inject_loose_object,
    update_reference,
    verify_prerequisites,
)


def _init_repo(path: Path) -> GitRepo:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    return GitRepo.discover(path)


def test_git_repo_discovery_and_errors(tmp_path: Path) -> None:
    # Not a repo
    with pytest.raises(ValueError, match="Not a git repository"):
        GitRepo.discover(tmp_path)

    # Standard repo
    repo = _init_repo(tmp_path)
    assert repo.root == tmp_path.resolve()
    assert repo.git_dir == (tmp_path / ".git").resolve()

    # Discover from subdirectory
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    discovered_sub = GitRepo.discover(sub)
    assert discovered_sub.root == repo.root
    assert discovered_sub.git_dir == repo.git_dir

    # Worktree pointer file
    wt_path = tmp_path / "worktree"
    wt_path.mkdir()
    (wt_path / ".git").write_text(f"gitdir: {repo.git_dir}\n")
    discovered_wt = GitRepo.discover(wt_path)
    assert discovered_wt.root == wt_path.resolve()
    assert discovered_wt.git_dir == repo.git_dir

    # Malformed worktree pointer file
    bad_wt = tmp_path / "bad_worktree"
    bad_wt.mkdir()
    (bad_wt / ".git").write_text("corrupted content without gitdir\n")
    with pytest.raises(ValueError, match="Malformed .git pointer file"):
        GitRepo.discover(bad_wt)

    # Run git helper
    res = repo.run_git(["status"])
    assert res.returncode == 0
    with pytest.raises(subprocess.CalledProcessError):
        repo.run_git(["invalid-git-subcommand"])


def test_loose_object_injection_and_fsck(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    # 1. Inject blob
    payload = b"Hello loose world!\n"
    blob_oid = inject_loose_object(repo, GitObjectType.BLOB, payload)
    assert len(blob_oid) == 40

    # Idempotent write
    assert inject_loose_object(repo, GitObjectType.BLOB, payload) == blob_oid

    # Verify with native git
    cat_proc = repo.run_git(["cat-file", "-p", blob_oid])
    assert cat_proc.stdout == payload

    # 2. Inject commit referencing blob (via empty tree)
    empty_tree_proc = repo.run_git(["mktree"], input=b"")
    empty_tree_oid = empty_tree_proc.stdout.decode().strip()

    commit = GitCommit(
        tree_oid=empty_tree_oid,
        parent_oids=[],
        author="Tester <t@example.com> 1700000000 +0000",
        committer="Tester <t@example.com> 1700000000 +0000",
        message="Initial injected commit\n",
    )
    commit_oid = inject_loose_object(repo, GitObjectType.COMMIT, commit.to_payload())
    assert commit_oid == commit.oid

    # Verify with git fsck
    fsck_proc = repo.run_git(["fsck"])
    assert fsck_proc.returncode == 0

    # 3. Update reference
    update_reference(repo, "refs/heads/main", commit_oid)
    assert repo.run_git(["rev-parse", "refs/heads/main"]).stdout.decode().strip() == commit_oid


def test_verify_prerequisites(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    (tmp_path / "file.txt").write_text("v1\n")
    repo.run_git(["add", "file.txt"])
    repo.run_git(["commit", "-m", "Initial"])

    commit_oid = repo.run_git(["rev-parse", "HEAD"]).stdout.decode().strip()

    # Valid prerequisite check succeeds
    verify_prerequisites(repo, [commit_oid])

    # Missing prerequisite raises ValueError
    missing_oid = "0" * 40
    with pytest.raises(ValueError, match="Missing prerequisite commit"):
        verify_prerequisites(repo, [missing_oid])


def test_discover_delta_scenarios(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    # Initial commit
    (tmp_path / "hello.txt").write_text("Hello world\n")
    repo.run_git(["add", "hello.txt"])
    repo.run_git(["commit", "-m", "Initial commit"])
    base_oid = repo.run_git(["rev-parse", "HEAD"]).stdout.decode().strip()

    # Create feature branch
    repo.run_git(["checkout", "-b", "feature"])
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("Nested content\n")
    # Duplicate file with identical content to exercise duplicate OID handling
    (sub / "nested_copy.txt").write_text("Nested content\n")
    repo.run_git(["add", "subdir/nested.txt", "subdir/nested_copy.txt"])
    repo.run_git(["commit", "-m", "Add nested"])

    # 1. Delta between main..feature
    delta = discover_delta(repo, "main..feature")
    assert delta.range_spec == "main..feature"
    assert delta.target_ref == "refs/heads/feature"
    assert delta.prerequisites == [base_oid]
    assert len(delta.objects) > 0

    # Check that nested.txt object has path recorded
    nested_blobs = [obj for obj in delta.objects if obj.path == "subdir/nested.txt"]
    assert len(nested_blobs) == 1
    assert nested_blobs[0].payload == b"Nested content\n"

    # 2. Symmetric difference range syntax: main...feature
    delta_sym = discover_delta(repo, "main...feature")
    assert delta_sym.target_ref == "refs/heads/feature"

    # 3. Explicit ref_name override
    delta_custom = discover_delta(repo, "feature", ref_name="refs/heads/custom-target")
    assert delta_custom.target_ref == "refs/heads/custom-target"
    assert delta_custom.prerequisites == []

    # 4. Attached HEAD scenario with raw commit hash
    delta_attached = discover_delta(repo, base_oid)
    assert delta_attached.target_ref == "refs/heads/feature"

    # 5. Detached HEAD scenario
    repo.run_git(["checkout", base_oid])
    delta_detached = discover_delta(repo, "HEAD")
    assert delta_detached.target_ref == "refs/heads/main"

    # 6. Empty delta
    delta_empty = discover_delta(repo, "feature..feature")
    assert len(delta_empty.objects) == 0


def test_discover_delta_batch_parsing_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a\n")
    repo.run_git(["add", "a.txt"])
    repo.run_git(["commit", "-m", "commit a"])

    orig_run_git = repo.run_git

    def mock_run_git(
        args: list[str], input: bytes | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        if args[:2] == ["rev-list", "--objects"]:
            # Inject a blank line, duplicate OID, and two distinct OIDs
            oid1 = "1" * 40
            oid2 = "2" * 40
            oid3 = "3" * 40
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"\n{oid1} path1\n{oid1} path1_dup\n{oid2} path2\n{oid3} path3\n\n".encode(),
                stderr=b"",
            )
        elif args[:2] == ["cat-file", "--batch"]:
            oid1 = "1" * 40
            oid2 = "2" * 40
            oid3 = "3" * 40
            # oid1: valid blob
            # oid2: missing
            # oid3: unknown object type
            output = (
                f"{oid1} blob 4\ndata\n{oid2} missing\n{oid3} unknown_git_type 4\ndata\n"
            ).encode()
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=output, stderr=b"")
        return orig_run_git(args, input=input, check=check)

    monkeypatch.setattr(repo, "run_git", mock_run_git)

    delta = discover_delta(repo, "HEAD")
    assert len(delta.objects) == 1
    assert delta.objects[0].oid == "1" * 40
    assert delta.objects[0].type == GitObjectType.BLOB
    assert delta.objects[0].payload == b"data"


def test_read_raw_object_and_get_object_at_revision(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    sub = tmp_path / "subdir"
    sub.mkdir()
    f1 = sub / "hello.txt"
    f1.write_text("hello world\n")
    repo.run_git(["add", "."])
    repo.run_git(["commit", "-m", "initial"])

    blob_oid = repo.run_git(["rev-parse", "HEAD:subdir/hello.txt"]).stdout.decode().strip()
    tree_oid = repo.run_git(["rev-parse", "HEAD:subdir"]).stdout.decode().strip()
    root_tree_oid = repo.run_git(["rev-parse", "HEAD^{tree}"]).stdout.decode().strip()

    # 1. read_raw_object with obj_type specified
    blob_bytes = repo.read_raw_object(blob_oid, GitObjectType.BLOB)
    assert blob_bytes == b"hello world\n"

    tree_bytes = repo.read_raw_object(tree_oid, GitObjectType.TREE)
    assert tree_bytes is not None

    # 2. read_raw_object without obj_type specified (cat-file -p)
    raw_untyped = repo.read_raw_object(blob_oid)
    assert raw_untyped == b"hello world\n"

    # 3. read_raw_object with nonexistent OID
    assert repo.read_raw_object("9" * 40) is None
    assert repo.read_raw_object("9" * 40, GitObjectType.BLOB) is None

    # 4. read_raw_object with wrong obj_type (blob requested as tree)
    assert repo.read_raw_object(blob_oid, GitObjectType.TREE) is None

    # 5. get_object_at_revision: root tree
    res_root = repo.get_object_at_revision("HEAD", "", GitObjectType.TREE)
    assert res_root is not None
    assert res_root[0] == root_tree_oid

    # 6. get_object_at_revision: subtree
    res_sub = repo.get_object_at_revision("HEAD", "subdir", GitObjectType.TREE)
    assert res_sub is not None
    assert res_sub[0] == tree_oid

    # 7. get_object_at_revision: blob
    res_blob = repo.get_object_at_revision("HEAD", "subdir/hello.txt", GitObjectType.BLOB)
    assert res_blob is not None
    assert res_blob[0] == blob_oid
    assert res_blob[1] == b"hello world\n"

    # 8. get_object_at_revision: blob with empty path returns None
    assert repo.get_object_at_revision("HEAD", "", GitObjectType.BLOB) is None

    # 9. get_object_at_revision: nonexistent path or rev
    assert repo.get_object_at_revision("HEAD", "nonexistent.txt", GitObjectType.BLOB) is None
    assert repo.get_object_at_revision("nonexistent_rev", "subdir", GitObjectType.TREE) is None

    # 10. get_object_at_revision: path is blob but tree requested
    assert repo.get_object_at_revision("HEAD", "subdir/hello.txt", GitObjectType.TREE) is None
