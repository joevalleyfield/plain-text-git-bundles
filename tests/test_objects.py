"""Tests for Git object data models, canonical serialization, and OID hashing."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from ptbundle.objects import (
    GitBlob,
    GitCommit,
    GitObject,
    GitObjectType,
    GitTag,
    GitTree,
    GitTreeEntry,
    compute_oid,
    format_git_object,
    parse_git_object,
    tree_entry_sort_key,
)


def test_compute_oid_empty_blob() -> None:
    # Git canonical empty blob SHA-1 is e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
    oid = compute_oid(GitObjectType.BLOB, b"", hash_algo="sha1")
    assert oid == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_compute_oid_with_string_type() -> None:
    oid = compute_oid("blob", b"", hash_algo="sha1")
    assert oid == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_compute_oid_known_string() -> None:
    payload = b"hello world\n"
    oid = compute_oid(GitObjectType.BLOB, payload, hash_algo="sha1")
    assert oid == "3b18e512dba79e4c8300dd08aeb37f8e728b8dad"


def test_compute_oid_sha256() -> None:
    payload = b"hello world\n"
    oid = compute_oid(GitObjectType.BLOB, payload, hash_algo="sha256")
    assert len(oid) == 64
    expected = hashlib.sha256(b"blob 12\0hello world\n").hexdigest()
    assert oid == expected


def test_compute_oid_invalid_algo() -> None:
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        compute_oid(GitObjectType.BLOB, b"", hash_algo="md5")


def test_format_and_parse_git_object() -> None:
    payload = b"test content"
    raw = format_git_object(GitObjectType.BLOB, payload)
    assert raw == b"blob 12\0test content"

    raw_str = format_git_object("blob", payload)
    assert raw_str == b"blob 12\0test content"

    obj_type, parsed_payload = parse_git_object(raw)
    assert obj_type == GitObjectType.BLOB
    assert parsed_payload == payload


def test_parse_git_object_malformed() -> None:
    with pytest.raises(ValueError, match="Malformed Git object: missing null byte"):
        parse_git_object(b"blob 12 test content")

    with pytest.raises(ValueError, match="Malformed Git object header"):
        parse_git_object(b"invalid_header\0content")

    with pytest.raises(ValueError, match="Size mismatch"):
        parse_git_object(b"blob 100\0short")


def test_git_blob_text_and_binary() -> None:
    text_blob = GitBlob.from_text("Hello, world! 🌍\n")
    assert text_blob.is_utf8_text() is True
    assert text_blob.decode_text() == "Hello, world! 🌍\n"
    assert text_blob.type == GitObjectType.BLOB
    assert len(text_blob.oid) == 40
    assert text_blob.to_payload() == "Hello, world! 🌍\n".encode()

    binary_blob = GitBlob(b"\x00\xff\xfe\x00binary data")
    assert binary_blob.is_utf8_text() is False
    with pytest.raises(UnicodeDecodeError):
        binary_blob.decode_text()

    # Non-utf8 bytes without null byte
    latin1_blob = GitBlob(b"\x80\x81\x82")
    assert latin1_blob.is_utf8_text() is False


def test_git_tree_entry_and_sort_key() -> None:
    key_dir = tree_entry_sort_key("foo", is_tree=True)
    key_file = tree_entry_sort_key("foo.txt", is_tree=False)
    assert key_dir == b"foo/"
    assert key_file == b"foo.txt"
    assert key_file < key_dir

    entry = GitTreeEntry(mode="40000", type=GitObjectType.TREE, oid="1" * 40, path="dir")
    assert entry.mode == "040000"
    assert entry.is_tree is True
    assert entry.sort_key() == b"dir/"


def test_git_tree_binary_and_text_roundtrip(temp_git_repo: Path) -> None:
    blob1_content = b"echo 'hello'\n"
    blob2_content = b"# Readme\n"
    blob1_oid = compute_oid(GitObjectType.BLOB, blob1_content)
    blob2_oid = compute_oid(GitObjectType.BLOB, blob2_content)

    entries = [
        GitTreeEntry(mode="100755", type=GitObjectType.BLOB, oid=blob1_oid, path="script.sh"),
        GitTreeEntry(mode="100644", type=GitObjectType.BLOB, oid=blob2_oid, path="README.md"),
    ]
    tree = GitTree(entries=entries)

    # 1. Test ls-tree text representation
    text_repr = tree.to_text()
    assert f"100644 blob {blob2_oid}\tREADME.md\n" in text_repr
    assert f"100755 blob {blob1_oid}\tscript.sh\n" in text_repr

    # 2. Test roundtrip from text representation
    tree_from_text = GitTree.from_text(text_repr)
    assert tree_from_text.oid == tree.oid
    assert len(tree_from_text.entries) == 2

    # 3. Test roundtrip from binary payload
    bin_payload = tree.to_binary_payload()
    assert tree.to_payload() == bin_payload
    tree_from_bin = GitTree.from_binary_payload(bin_payload)
    assert tree_from_bin.oid == tree.oid

    # 4. Compare with canonical git mktree --missing
    mktree_proc = subprocess.run(
        ["git", "mktree", "--missing"],
        cwd=temp_git_repo,
        input=text_repr.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    git_tree_oid = mktree_proc.stdout.decode("utf-8").strip()
    assert tree.oid == git_tree_oid


def test_git_tree_sha256_binary_roundtrip() -> None:
    oid1 = "1" * 64
    oid2 = "2" * 64
    entries = [
        GitTreeEntry(mode="100644", type=GitObjectType.BLOB, oid=oid1, path="file.txt"),
        GitTreeEntry(mode="040000", type=GitObjectType.TREE, oid=oid2, path="subdir"),
    ]
    tree = GitTree(entries=entries, hash_algo="sha256")
    bin_payload = tree.to_binary_payload()
    parsed_tree = GitTree.from_binary_payload(bin_payload, hash_algo="sha256")
    assert parsed_tree.oid == tree.oid
    assert len(parsed_tree.entries) == 2
    assert parsed_tree.entries[0].type == GitObjectType.BLOB
    assert parsed_tree.entries[1].type == GitObjectType.TREE


def test_git_tree_canonical_sort_parity(temp_git_repo: Path) -> None:
    dummy_oid = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    entries = [
        GitTreeEntry(mode="100644", type=GitObjectType.BLOB, oid=dummy_oid, path="a.c"),
        GitTreeEntry(mode="040000", type=GitObjectType.TREE, oid=dummy_oid, path="a"),
        GitTreeEntry(mode="100644", type=GitObjectType.BLOB, oid=dummy_oid, path="a-b"),
        GitTreeEntry(mode="100644", type=GitObjectType.BLOB, oid=dummy_oid, path="a_b"),
    ]
    tree = GitTree(entries=entries)
    text_repr = tree.to_text()

    # Pass to git mktree --missing to verify Git's authoritative sort and OID
    mktree_proc = subprocess.run(
        ["git", "mktree", "--missing"],
        cwd=temp_git_repo,
        input=text_repr.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    expected_oid = mktree_proc.stdout.decode("utf-8").strip()
    assert tree.oid == expected_oid


def test_git_tree_invalid_parsing() -> None:
    with pytest.raises(ValueError, match="Invalid ls-tree line"):
        GitTree.from_text("invalid line without tab")

    with pytest.raises(ValueError, match="Invalid ls-tree metadata"):
        GitTree.from_text("100644 blob\tfile.txt")

    with pytest.raises(ValueError, match="Corrupt binary tree entry"):
        GitTree.from_binary_payload(b"100644 README.md\0short")

    with pytest.raises(ValueError, match="Corrupt binary tree entry"):
        GitTree.from_binary_payload(b"100644no_space\0" + b"0" * 20)

    with pytest.raises(ValueError, match="Corrupt binary tree entry"):
        GitTree.from_binary_payload(b"100644 no_null" + b"0" * 20)


def test_git_commit_serialization_and_parity(temp_git_repo: Path) -> None:
    tree_oid = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    parent_oid = "3b18e512dba79e4c8300dd08aeb37f8e728b8dad"
    author = "Alice <alice@example.com> 1700000000 +0000"
    committer = "Bob <bob@example.com> 1700000100 +0000"
    message = "Initial commit\n\nDetailed description here.\n"

    commit = GitCommit(
        tree_oid=tree_oid,
        parent_oids=[parent_oid],
        author=author,
        committer=committer,
        message=message,
    )
    payload = commit.to_payload()

    parsed = GitCommit.from_payload(payload)
    assert parsed.tree_oid == tree_oid
    assert parsed.parent_oids == [parent_oid]
    assert parsed.author == author
    assert parsed.committer == committer
    assert parsed.message == message
    assert parsed.oid == commit.oid

    env = {
        "GIT_AUTHOR_NAME": "Alice",
        "GIT_AUTHOR_EMAIL": "alice@example.com",
        "GIT_AUTHOR_DATE": "1700000000 +0000",
        "GIT_COMMITTER_NAME": "Bob",
        "GIT_COMMITTER_EMAIL": "bob@example.com",
        "GIT_COMMITTER_DATE": "1700000100 +0000",
    }
    empty_tree_oid = (
        subprocess.run(
            ["git", "mktree"],
            cwd=temp_git_repo,
            input=b"",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )

    commit_under_test = GitCommit(
        tree_oid=empty_tree_oid,
        parent_oids=[],
        author=author,
        committer=committer,
        message="feat: first commit\n",
    )
    commit_proc = subprocess.run(
        ["git", "commit-tree", empty_tree_oid, "-m", "feat: first commit"],
        cwd=temp_git_repo,
        env=env,
        capture_output=True,
        check=True,
    )
    git_commit_oid = commit_proc.stdout.decode().strip()
    assert commit_under_test.oid == git_commit_oid


def test_git_commit_merge_and_extra_headers() -> None:
    commit = GitCommit(
        tree_oid="0" * 40,
        parent_oids=["1" * 40, "2" * 40],
        author="Alice <a@example.com> 1 +0000",
        committer="Alice <a@example.com> 1 +0000",
        message="Merge branch 'foo'\n",
        extra_headers=[
            ("gpgsig", "-----BEGIN PGP SIGNATURE-----\ndata\n-----END PGP SIGNATURE-----")
        ],
    )
    payload = commit.to_payload()
    parsed = GitCommit.from_payload(payload)
    assert parsed.parent_oids == ["1" * 40, "2" * 40]
    assert len(parsed.extra_headers) == 1
    assert parsed.extra_headers[0][0] == "gpgsig"
    assert "data" in parsed.extra_headers[0][1]


def test_git_commit_malformed_payload() -> None:
    with pytest.raises(ValueError, match="Malformed commit: missing header/body separator"):
        GitCommit.from_payload(b"tree 1234\nauthor Me")

    with pytest.raises(ValueError, match="Missing required commit fields"):
        GitCommit.from_payload(b"parent 1234\n\nMissing tree")

    with pytest.raises(ValueError, match="Missing required commit fields"):
        GitCommit.from_payload(b"tree 1234\nauthor Alice\n\nMissing committer")

    with pytest.raises(ValueError, match="Missing required commit fields"):
        GitCommit.from_payload(b"tree 1234\ncommitter Bob\n\nMissing author")


def test_git_tag_serialization_and_parsing() -> None:
    tag = GitTag(
        object_oid="1" * 40,
        object_type=GitObjectType.COMMIT,
        tag_name="v1.0.0",
        tagger="Tagger <tagger@example.com> 1700000000 +0000",
        message="Release v1.0.0\n",
        extra_headers=[("gpgsig", "sigline1\nsigline2")],
    )
    payload = tag.to_payload()
    parsed = GitTag.from_payload(payload)
    assert parsed.object_oid == "1" * 40
    assert parsed.object_type == GitObjectType.COMMIT
    assert parsed.tag_name == "v1.0.0"
    assert parsed.tagger == "Tagger <tagger@example.com> 1700000000 +0000"
    assert parsed.message == "Release v1.0.0\n"
    assert parsed.oid == tag.oid
    assert len(parsed.extra_headers) == 1
    assert parsed.extra_headers[0][1] == "sigline1\nsigline2"


def test_git_tag_malformed_payload() -> None:
    with pytest.raises(ValueError, match="Malformed tag: missing header/body separator"):
        GitTag.from_payload(b"object 1234")

    with pytest.raises(ValueError, match="Missing required tag fields"):
        GitTag.from_payload(b"object 1234\n\nMissing other headers")

    with pytest.raises(ValueError, match="Missing required tag fields"):
        GitTag.from_payload(b"object 1234\ntype commit\n\nMissing tag name")


def test_git_tree_blank_lines() -> None:
    oid = "0" * 40
    text = f"\n100644 blob {oid}\tfoo.txt\n\n"
    tree = GitTree.from_text(text)
    assert len(tree.entries) == 1
    assert tree.entries[0].path == "foo.txt"


def test_git_commit_blank_header_lines() -> None:
    oid = "0" * 40
    raw = f"\ntree {oid}\nauthor Alice <a@b> 1 +0000\ncommitter Bob <b@b> 2 +0000\n\nmessage\n".encode()
    commit = GitCommit.from_payload(raw)
    assert commit.tree_oid == oid
    assert commit.author == "Alice <a@b> 1 +0000"


def test_git_tag_no_tagger_and_blank_header_lines() -> None:
    oid = "0" * 40
    tag = GitTag(
        object_oid=oid,
        object_type=GitObjectType.COMMIT,
        tag_name="v0.1",
        tagger="",
        message="Tag without tagger\n",
    )
    payload = tag.to_payload()
    assert b"tagger " not in payload

    # Also test blank header line in tag payload parsing
    raw = f"\nobject {oid}\ntype commit\ntag v0.1\n\nTag without tagger\n".encode()
    parsed = GitTag.from_payload(raw)
    assert parsed.tagger == ""
    assert parsed.tag_name == "v0.1"


def test_git_object_base_class() -> None:
    blob = GitBlob(b"hello")
    assert isinstance(blob, GitObject)
    assert blob.oid == compute_oid(GitObjectType.BLOB, b"hello")
