"""Unit tests for Git bundle interoperability bridge (ptbundle.bundle)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ptbundle.bundle import (
    convert_from_bundle,
    convert_to_bundle,
    read_bundle_header,
)
from ptbundle.manifest import ManifestPrerequisite, ManifestRef


def test_read_bundle_header_valid_v2(tmp_path: Path) -> None:
    bundle_file = tmp_path / "valid.bundle"
    oid1 = "1111111111111111111111111111111111111111"
    oid2 = "2222222222222222222222222222222222222222"
    content = (
        f"# v2 git bundle\n"
        f"-{oid1} main base\n"
        f"{oid2} refs/heads/feature\n"
        f"\n"
        f"PACKfakebinarypackpayload"
    ).encode()
    bundle_file.write_bytes(content)

    header = read_bundle_header(bundle_file)
    assert header.version == 2
    assert len(header.prerequisites) == 1
    assert header.prerequisites[0] == ManifestPrerequisite(oid=oid1, comment="main base")
    assert len(header.refs) == 1
    assert header.refs[0] == ManifestRef(name="refs/heads/feature", oid=oid2)


def test_read_bundle_header_valid_v3_with_capabilities(tmp_path: Path) -> None:
    bundle_file = tmp_path / "valid_v3.bundle"
    oid = "3333333333333333333333333333333333333333"
    content = (
        f"# v3 git bundle\n@object-format=sha1\n{oid} refs/heads/main\n\r\n\r\nPACKbinarypayload"
    ).encode()
    bundle_file.write_bytes(content)

    header = read_bundle_header(bundle_file)
    assert header.version == 3
    assert len(header.prerequisites) == 0
    assert len(header.refs) == 1
    assert header.refs[0].name == "refs/heads/main"


def test_read_bundle_header_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_bundle_header(tmp_path / "nonexistent.bundle")

    # Missing blank line separator
    no_sep = tmp_path / "no_sep.bundle"
    no_sep.write_bytes(b"# v2 git bundle\n1111111111111111111111111111111111111111 refs/heads/main")
    with pytest.raises(ValueError, match="missing blank line separator"):
        read_bundle_header(no_sep)

    # Malformed UTF-8 header
    bad_utf8 = tmp_path / "bad_utf8.bundle"
    bad_utf8.write_bytes(b"\xff\xfe\n\nPACK")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        read_bundle_header(bad_utf8)

    # Empty header text
    empty_header = tmp_path / "empty.bundle"
    empty_header.write_bytes(b"\n\nPACK")
    with pytest.raises(ValueError, match="Empty Git bundle header"):
        read_bundle_header(empty_header)

    # Invalid header signature
    bad_sig = tmp_path / "bad_sig.bundle"
    bad_sig.write_bytes(b"# v1 git bundle\n\nPACK")
    with pytest.raises(ValueError, match="Unsupported or invalid Git bundle header"):
        read_bundle_header(bad_sig)

    # Malformed prerequisite line
    bad_prereq = tmp_path / "bad_prereq.bundle"
    bad_prereq.write_bytes(b"# v2 git bundle\n-\n\nPACK")
    with pytest.raises(ValueError, match="Malformed prerequisite line"):
        read_bundle_header(bad_prereq)

    # Malformed ref line
    bad_ref = tmp_path / "bad_ref.bundle"
    bad_ref.write_bytes(b"# v2 git bundle\nsingle_token\n\nPACK")
    with pytest.raises(ValueError, match="Malformed reference line"):
        read_bundle_header(bad_ref)

    # No refs declared
    no_refs = tmp_path / "no_refs.bundle"
    no_refs.write_bytes(b"# v2 git bundle\n\nPACK")
    with pytest.raises(ValueError, match="declares no reference heads"):
        read_bundle_header(no_refs)


def test_bundle_conversion_roundtrip(tmp_path: Path) -> None:
    # 1. Create a real Git repo with 2 commits
    repo_dir = tmp_path / "src_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
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

    f1 = repo_dir / "file1.txt"
    f1.write_text("initial commit\n" + "context\n" * 30, encoding="utf-8")
    subprocess.run(["git", "add", "file1.txt"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "commit 1"], cwd=repo_dir, check=True, capture_output=True
    )

    f1.write_text("updated commit\n" + "context\n" * 30, encoding="utf-8")
    subprocess.run(["git", "add", "file1.txt"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "commit 2"], cwd=repo_dir, check=True, capture_output=True
    )

    # 2. Create canonical Git bundle using `git bundle create`
    git_bundle = tmp_path / "test.bundle"
    subprocess.run(
        ["git", "bundle", "create", str(git_bundle), "main"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    assert git_bundle.is_file()

    # 3. Convert from Git bundle to ptbundle
    ptbundle_dir = tmp_path / "ptbundle_out"
    manifest = convert_from_bundle(git_bundle, ptbundle_dir, enable_delta=True)
    assert manifest.metrics.commits == 2
    assert (ptbundle_dir / "manifest.txt").is_file()

    # 4. Convert ptbundle back to Git bundle
    recreated_bundle = tmp_path / "recreated.bundle"
    convert_to_bundle(ptbundle_dir, recreated_bundle)
    assert recreated_bundle.is_file()

    # 5. Verify the synthesized bundle passes `git bundle verify`
    verify_proc = subprocess.run(
        ["git", "bundle", "verify", str(recreated_bundle)],
        capture_output=True,
        text=True,
    )
    assert verify_proc.returncode == 0
    assert "is okay" in verify_proc.stdout or "is okay" in verify_proc.stderr

    # 6. Verify error on missing manifest.txt
    with pytest.raises(FileNotFoundError, match="Missing manifest.txt"):
        convert_to_bundle(tmp_path / "empty_dir", tmp_path / "out.bundle")
