"""Unit tests for Plain-Text Delta Engine (ptbundle.delta)."""

from __future__ import annotations

import pytest

from ptbundle.delta import (
    TextDelta,
    _split_lines_preserving_eof,
    apply_text_delta,
    create_text_delta,
)
from ptbundle.objects import (
    GitObjectType,
    GitTree,
    GitTreeEntry,
    compute_oid,
)


def test_split_lines_preserving_eof() -> None:
    assert _split_lines_preserving_eof("") == ([], True)
    assert _split_lines_preserving_eof("a\n") == (["a\n"], True)
    assert _split_lines_preserving_eof("a\r\n") == (["a\r\n"], True)
    assert _split_lines_preserving_eof("a") == (["a"], False)
    assert _split_lines_preserving_eof("a\nb") == (["a\n", "b"], False)


def test_text_delta_serialization_and_parsing() -> None:
    base_oid = "1111111111111111111111111111111111111111"
    target_oid = "2222222222222222222222222222222222222222"
    diff = "@@ -1,1 +1,1 @@\n-old\n+new\n"

    delta = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text=diff,
        path="src/app.py",
    )

    serialized = delta.to_text()
    assert "# ptbundle delta v1" in serialized
    assert "type: blob" in serialized
    assert "path: src/app.py" in serialized
    assert f"base: {base_oid}" in serialized
    assert f"target: {target_oid}" in serialized
    assert diff in serialized

    # Parse back
    parsed = TextDelta.from_text(serialized)
    assert parsed.object_type == GitObjectType.BLOB
    assert parsed.base_oid == base_oid
    assert parsed.target_oid == target_oid
    assert parsed.path == "src/app.py"
    assert parsed.diff_text.strip() == diff.strip()


def test_text_delta_without_path_and_immediate_diff() -> None:
    base_oid = "1111111111111111111111111111111111111111"
    target_oid = "2222222222222222222222222222222222222222"
    diff = "@@ -1,1 +1,1 @@\n-old\n+new\n"

    delta = TextDelta(
        object_type=GitObjectType.TREE,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text=diff,
    )
    serialized = delta.to_text()
    parsed = TextDelta.from_text(serialized)
    assert parsed.path == ""
    assert parsed.object_type == GitObjectType.TREE

    # Test immediate diff without blank line
    text_no_blank = (
        f"# ptbundle delta v1\ntype: tree\nbase: {base_oid}\ntarget: {target_oid}\n{diff}"
    )
    parsed_no_blank = TextDelta.from_text(text_no_blank)
    assert parsed_no_blank.base_oid == base_oid
    assert parsed_no_blank.diff_text.strip() == diff.strip()


def test_text_delta_parsing_errors() -> None:
    valid_base = "1111111111111111111111111111111111111111"
    valid_target = "2222222222222222222222222222222222222222"

    with pytest.raises(ValueError, match="Empty delta text"):
        TextDelta.from_text("")

    with pytest.raises(ValueError, match="Invalid delta header"):
        TextDelta.from_text("invalid header\n")

    with pytest.raises(ValueError, match="Malformed delta header field"):
        TextDelta.from_text("# ptbundle delta v1\nno_colon_line\n")

    with pytest.raises(ValueError, match="Missing required 'type:'"):
        TextDelta.from_text(f"# ptbundle delta v1\nbase: {valid_base}\ntarget: {valid_target}\n")

    with pytest.raises(ValueError, match="Unsupported delta object type"):
        TextDelta.from_text(
            f"# ptbundle delta v1\ntype: commit\nbase: {valid_base}\ntarget: {valid_target}\n"
        )

    with pytest.raises(ValueError, match="Missing required 'base:'"):
        TextDelta.from_text(f"# ptbundle delta v1\ntype: blob\ntarget: {valid_target}\n")

    with pytest.raises(ValueError, match="Missing required 'target:'"):
        TextDelta.from_text(f"# ptbundle delta v1\ntype: blob\nbase: {valid_base}\n")

    with pytest.raises(ValueError, match="Delta text contains no diff hunks"):
        TextDelta.from_text(
            f"# ptbundle delta v1\ntype: blob\nbase: {valid_base}\ntarget: {valid_target}\n"
        )

    with pytest.raises(ValueError, match="Delta diff content cannot be empty"):
        TextDelta.from_text(
            f"# ptbundle delta v1\ntype: blob\nbase: {valid_base}\ntarget: {valid_target}\n\n   \n"
        )


def test_create_text_delta_rejections() -> None:
    base = b"hello\0world"
    target = b"hello world"
    assert create_text_delta(base, target, "a" * 40, "b" * 40) is None
    assert create_text_delta(target, base, "a" * 40, "b" * 40) is None

    # Invalid utf-8
    assert create_text_delta(b"\xff\xfe", target, "a" * 40, "b" * 40) is None

    # Identical
    assert create_text_delta(b"same\n", b"same\n", "a" * 40, "b" * 40) is None

    # Delta larger than target (target is 4 bytes, delta text overhead is >50 bytes)
    assert create_text_delta(b"abcdef\n", b"xyz\n", "a" * 40, "b" * 40) is None


def test_create_and_apply_text_delta_blob_roundtrip() -> None:
    # Large enough base and target so that diff is smaller than full target payload
    base_content = ("line 1: initial content\n" + "context line\n" * 50).encode("utf-8")
    target_content = ("line 1: updated content\n" + "context line\n" * 50).encode("utf-8")

    base_oid = compute_oid(GitObjectType.BLOB, base_content)
    target_oid = compute_oid(GitObjectType.BLOB, target_content)

    delta = create_text_delta(
        base_content,
        target_content,
        base_oid,
        target_oid,
        path="test.txt",
    )
    assert delta is not None
    assert delta.path == "test.txt"
    assert delta.base_oid == base_oid
    assert delta.target_oid == target_oid

    # Reconstruct
    reconstructed = apply_text_delta(base_content, delta)
    assert reconstructed == target_content
    assert compute_oid(GitObjectType.BLOB, reconstructed) == target_oid


def test_create_and_apply_text_delta_no_eof_newline() -> None:
    base_content = ("context line\n" * 50 + "end without newline").encode("utf-8")
    target_content = ("context line\n" * 50 + "updated end without newline").encode("utf-8")

    base_oid = compute_oid(GitObjectType.BLOB, base_content)
    target_oid = compute_oid(GitObjectType.BLOB, target_content)

    delta = create_text_delta(base_content, target_content, base_oid, target_oid)
    assert delta is not None

    reconstructed = apply_text_delta(base_content, delta)
    assert reconstructed == target_content
    assert not reconstructed.endswith(b"\n")
    assert compute_oid(GitObjectType.BLOB, reconstructed) == target_oid


def test_create_and_apply_text_delta_crlf_endings() -> None:
    base_content = ("line 1\r\n" + "line 2\r\n" * 50).encode("utf-8")
    target_content = ("line 1 modified\r\n" + "line 2\r\n" * 50).encode("utf-8")

    base_oid = compute_oid(GitObjectType.BLOB, base_content)
    target_oid = compute_oid(GitObjectType.BLOB, target_content)

    delta = create_text_delta(base_content, target_content, base_oid, target_oid)
    assert delta is not None

    reconstructed = apply_text_delta(base_content, delta)
    assert reconstructed == target_content
    assert compute_oid(GitObjectType.BLOB, reconstructed) == target_oid


def test_create_and_apply_text_delta_tree_roundtrip() -> None:
    # Build base tree with 20 entries
    entries_base = [
        GitTreeEntry(
            mode="100644",
            type=GitObjectType.BLOB,
            path=f"file_{i:03d}.txt",
            oid=f"1111111111111111111111111111111111111{i:03d}",
        )
        for i in range(20)
    ]
    tree_base = GitTree(entries=entries_base)
    base_payload = tree_base.to_text().encode("utf-8")
    base_oid = tree_base.oid

    # Target tree: modifies entry 5, adds entry 21, deletes entry 10
    entries_target = [
        GitTreeEntry(
            mode="100644",
            type=GitObjectType.BLOB,
            path=f"file_{i:03d}.txt",
            oid=(
                f"9999999999999999999999999999999999999{i:03d}"
                if i == 5
                else f"1111111111111111111111111111111111111{i:03d}"
            ),
        )
        for i in range(20)
        if i != 10
    ]
    entries_target.append(
        GitTreeEntry(
            mode="100755",
            type=GitObjectType.BLOB,
            path="file_020.txt",
            oid="8888888888888888888888888888888888888888",
        )
    )
    tree_target = GitTree(entries=entries_target)
    target_payload = tree_target.to_text().encode("utf-8")
    target_oid = tree_target.oid

    delta = create_text_delta(
        base_payload,
        target_payload,
        base_oid,
        target_oid,
        object_type=GitObjectType.TREE,
        path="src/",
    )
    assert delta is not None
    assert delta.object_type == GitObjectType.TREE

    reconstructed_binary = apply_text_delta(base_payload, delta)
    # The return of tree patching is canonical Git binary tree payload
    assert reconstructed_binary == tree_target.to_binary_payload()
    assert compute_oid(GitObjectType.TREE, reconstructed_binary) == target_oid


def test_apply_text_delta_errors() -> None:
    base = b"line 1\nline 2\nline 3\n"
    base_oid = compute_oid(GitObjectType.BLOB, base)
    target_oid = "2222222222222222222222222222222222222222"

    # 1. Base OID mismatch
    delta = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid="0" * 40,
        target_oid=target_oid,
        diff_text="@@ -1,1 +1,1 @@\n-line 1\n+new line\n",
    )
    with pytest.raises(ValueError, match="Base object OID mismatch"):
        apply_text_delta(base, delta)

    # 2. Base payload non-UTF-8
    with pytest.raises(ValueError, match="Base payload is not valid UTF-8"):
        delta_nonutf8 = TextDelta(
            object_type=GitObjectType.BLOB,
            base_oid=compute_oid(GitObjectType.BLOB, b"\xff\xfe"),
            target_oid=target_oid,
            diff_text="@@ -1,1 +1,1 @@\n",
        )
        apply_text_delta(b"\xff\xfe", delta_nonutf8)

    # 3. Malformed hunk header
    delta_bad_hunk = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ bad hunk @@\n",
    )
    with pytest.raises(ValueError, match="Malformed hunk header"):
        apply_text_delta(base, delta_bad_hunk)

    # 4. Out-of-order hunk
    delta_out_of_order = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ -3,1 +3,1 @@\n line 3\n@@ -1,1 +1,1 @@\n line 1\n",
    )
    with pytest.raises(ValueError, match="Hunk out of order"):
        apply_text_delta(base, delta_out_of_order)

    # 5. Hunk starts past end of base
    delta_past_end = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ -10,1 +10,1 @@\n line 10\n",
    )
    with pytest.raises(ValueError, match="Hunk starts past end"):
        apply_text_delta(base, delta_past_end)

    # 6. Context mismatch
    delta_context_mismatch = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ -1,2 +1,2 @@\n wrong context\n",
    )
    with pytest.raises(ValueError, match="Hunk context mismatch"):
        apply_text_delta(base, delta_context_mismatch)

    # 7. Context beyond length
    delta_context_beyond = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ -1,5 +1,5 @@\n line 1\n line 2\n line 3\n line 4\n",
    )
    with pytest.raises(ValueError, match="Hunk context line beyond"):
        apply_text_delta(base, delta_context_beyond)

    # 8. Deletion mismatch
    delta_del_mismatch = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ -1,1 +1,1 @@\n-wrong line\n+new\n",
    )
    with pytest.raises(ValueError, match="Hunk deletion mismatch"):
        apply_text_delta(base, delta_del_mismatch)

    # 9. Deletion beyond length
    delta_del_beyond = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text="@@ -1,4 +1,1 @@\n-line 1\n-line 2\n-line 3\n-line 4\n+new\n",
    )
    with pytest.raises(ValueError, match="Hunk deletion line beyond"):
        apply_text_delta(base, delta_del_beyond)

    # 10. Target OID mismatch on blob
    delta_oid_mismatch = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid="3" * 40,
        diff_text="@@ -1,1 +1,1 @@\n-line 1\n+line 1 modified\n",
    )
    with pytest.raises(ValueError, match="Reconstructed blob OID mismatch"):
        apply_text_delta(base, delta_oid_mismatch)

    # 11. Target OID mismatch on tree
    base_tree = GitTree(
        entries=[
            GitTreeEntry(
                mode="100644",
                type=GitObjectType.BLOB,
                path="a.txt",
                oid="1111111111111111111111111111111111111111",
            )
        ]
    )
    base_tree_payload = base_tree.to_text().encode("utf-8")
    delta_tree_oid_mismatch = TextDelta(
        object_type=GitObjectType.TREE,
        base_oid=base_tree.oid,
        target_oid="4" * 40,
        diff_text="@@ -1,1 +1,1 @@\n-100644 blob 1111111111111111111111111111111111111111\ta.txt\n+100644 blob 2222222222222222222222222222222222222222\ta.txt\n",
    )
    with pytest.raises(ValueError, match="Reconstructed tree OID mismatch"):
        apply_text_delta(base_tree_payload, delta_tree_oid_mismatch)

    # 12. Tree base with binary payload roundtrip
    valid_target_tree = GitTree(
        entries=[
            GitTreeEntry(
                mode="100644",
                type=GitObjectType.BLOB,
                path="a.txt",
                oid="2222222222222222222222222222222222222222",
            )
        ]
    )
    delta_tree_valid = TextDelta(
        object_type=GitObjectType.TREE,
        base_oid=base_tree.oid,
        target_oid=valid_target_tree.oid,
        diff_text="@@ -1,1 +1,1 @@\n-100644 blob 1111111111111111111111111111111111111111\ta.txt\n+100644 blob 2222222222222222222222222222222222222222\ta.txt\n",
    )
    reconstituted_bin = apply_text_delta(base_tree.to_binary_payload(), delta_tree_valid)
    assert reconstituted_bin == valid_target_tree.to_binary_payload()

    # 13. Tree base with non-UTF-8 payload (and no null byte)
    with pytest.raises(ValueError, match="Base payload is not valid UTF-8"):
        apply_text_delta(b"\xff\xfe", delta_tree_valid)

    # 14. Tree base OID mismatch
    other_tree = GitTree(
        entries=[
            GitTreeEntry(
                mode="100644",
                type=GitObjectType.BLOB,
                path="other.txt",
                oid="3333333333333333333333333333333333333333",
            )
        ]
    )
    with pytest.raises(ValueError, match="Base object OID mismatch"):
        apply_text_delta(other_tree.to_text().encode("utf-8"), delta_tree_valid)


def test_delta_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. TextDelta.to_text without trailing newline
    delta = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid="1" * 40,
        target_oid="2" * 40,
        diff_text="@@ -1 +1 @@\n-a\n+b",
    )
    serialized = delta.to_text()
    assert serialized.endswith("\n")

    # 2. TextDelta.from_text with blank lines before headers and unknown header
    text_with_blanks = (
        "# ptbundle delta v1\n"
        "\n"
        "type: blob\n"
        "path: test.txt\n"
        "base: " + "1" * 40 + "\n"
        "target: " + "2" * 40 + "\n"
        "\n"
        "@@ -1,1 +1,1 @@\n"
        "-a\n"
        "+b\n"
    )
    parsed = TextDelta.from_text(text_with_blanks)
    assert parsed.path == "test.txt"

    text_unknown_header = (
        "# ptbundle delta v1\n"
        "type: blob\n"
        "foo: bar\n"
        "base: " + "1" * 40 + "\n"
        "target: " + "2" * 40 + "\n"
        "\n"
        "@@ -1 +1 @@\n"
    )
    with pytest.raises(ValueError, match="Unknown delta header field: 'foo'"):
        TextDelta.from_text(text_unknown_header)

    # 3. Context line at end without trailing newline in create_text_delta
    lines_base = [f"line {i:03d} content here to fill size\n" for i in range(30)]
    lines_base.append("no newline at the very end")
    base_no_nl = "".join(lines_base).encode("utf-8")

    lines_target = list(lines_base)
    lines_target[28] = "modified line 28 content here!\n"
    target_no_nl = "".join(lines_target).encode("utf-8")

    d_ctx = create_text_delta(
        base_no_nl,
        target_no_nl,
        compute_oid(GitObjectType.BLOB, base_no_nl),
        compute_oid(GitObjectType.BLOB, target_no_nl),
    )
    assert d_ctx is not None
    assert "\\ No newline at end of file" in d_ctx.diff_text
    reconstructed = apply_text_delta(base_no_nl, d_ctx)
    assert reconstructed == target_no_nl

    # 4. Empty diff text from difflib
    import difflib

    monkeypatch.setattr(difflib, "unified_diff", lambda *a, **k: iter([]))
    d_empty = create_text_delta(
        b"abc\n",
        b"def\n",
        compute_oid(GitObjectType.BLOB, b"abc\n"),
        compute_oid(GitObjectType.BLOB, b"def\n"),
    )
    assert d_empty is None

    # 5. CRLF with no-newline marker and extra lines outside hunk in apply_text_delta
    base = b"old line\r\n"
    base_oid = compute_oid(GitObjectType.BLOB, base)
    target = b"new line"
    target_oid = compute_oid(GitObjectType.BLOB, target)
    diff_crlf = (
        "unrecognized comment line before hunk\n"
        "@@ -1,1 +1,1 @@\n"
        "-old line\r\n"
        "+new line\r\n"
        "\\ No newline at end of file\n"
        "\\ No newline at end of file\n"
        "unrecognized comment line after hunk\n"
    )
    delta_crlf = TextDelta(
        object_type=GitObjectType.BLOB,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text=diff_crlf,
    )
    reconstructed_crlf = apply_text_delta(base, delta_crlf)
    assert reconstructed_crlf == target
