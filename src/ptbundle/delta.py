"""Plain-text delta compression engine for Plain-Text Git Bundles (ptbundle).

Implements CVS/RCS-style plain-text unified diff generation and deterministic
patch application for Git text blobs and ls-tree formatted trees with bit-exact
Git OID cryptographic verification and exact newline preservation.
"""

from __future__ import annotations

import dataclasses
import difflib
import re

from ptbundle.manifest import validate_oid
from ptbundle.objects import GitObjectType, GitTree, compute_oid

DELTA_FORMAT_HEADER = "# ptbundle delta v1"
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_NO_NEWLINE_MARKER = "\\ No newline at end of file"


@dataclasses.dataclass(frozen=True)
class TextDelta:
    """Representation of a plain-text delta against a base Git object."""

    object_type: GitObjectType
    base_oid: str
    target_oid: str
    diff_text: str
    path: str = ""

    def to_text(self) -> str:
        """Serialize delta into plain-text format with audit headers."""
        lines = [
            DELTA_FORMAT_HEADER,
            f"type: {self.object_type.value}",
        ]
        if self.path:
            lines.append(f"path: {self.path}")
        lines.append(f"base: {self.base_oid}")
        lines.append(f"target: {self.target_oid}")
        lines.append("")
        lines.append(self.diff_text)
        if not self.diff_text.endswith("\n"):
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_text(cls, text: str, hash_algo: str = "sha1") -> TextDelta:
        """Parse serialized delta text into a TextDelta instance.

        Raises ValueError if the header or fields are malformed or invalid.
        """
        raw_lines = text.splitlines(keepends=True)
        if not raw_lines:
            raise ValueError("Empty delta text")

        header = raw_lines[0].strip()
        if header != DELTA_FORMAT_HEADER:
            raise ValueError(f"Invalid delta header: {header!r}, expected {DELTA_FORMAT_HEADER!r}")

        obj_type_str: str | None = None
        base_oid: str | None = None
        target_oid: str | None = None
        path: str = ""
        diff_start_idx = -1

        for idx in range(1, len(raw_lines)):
            line = raw_lines[idx].strip()
            if not line:
                # Blank line marks end of header section if headers were found
                if base_oid and target_oid and obj_type_str:
                    diff_start_idx = idx + 1
                    break
                continue
            if line.startswith("@@ "):
                # Start of diff without preceding blank line
                diff_start_idx = idx
                break

            colon_idx = line.find(":")
            if colon_idx == -1:
                raise ValueError(f"Malformed delta header field: {line!r}")

            key = line[:colon_idx].strip().lower()
            val = line[colon_idx + 1 :].strip()

            if key == "type":
                obj_type_str = val.lower()
            elif key == "base":
                base_oid = validate_oid(val, hash_algo=hash_algo)
            elif key == "target":
                target_oid = validate_oid(val, hash_algo=hash_algo)
            elif key == "path":
                path = val
            else:
                raise ValueError(f"Unknown delta header field: {key!r}")

        if not obj_type_str:
            raise ValueError("Missing required 'type:' in delta header")
        if obj_type_str not in (GitObjectType.BLOB.value, GitObjectType.TREE.value):
            raise ValueError(
                f"Unsupported delta object type: {obj_type_str!r} (must be 'blob' or 'tree')"
            )
        if not base_oid:
            raise ValueError("Missing required 'base:' OID in delta header")
        if not target_oid:
            raise ValueError("Missing required 'target:' OID in delta header")
        if diff_start_idx == -1 or diff_start_idx >= len(raw_lines):
            raise ValueError("Delta text contains no diff hunks")

        diff_text = "".join(raw_lines[diff_start_idx:])
        if not diff_text.strip():
            raise ValueError("Delta diff content cannot be empty")

        return cls(
            object_type=GitObjectType(obj_type_str),
            base_oid=base_oid,
            target_oid=target_oid,
            diff_text=diff_text,
            path=path,
        )


def _split_lines_preserving_eof(payload_str: str) -> tuple[list[str], bool]:
    """Split a string into lines preserving line endings.

    Returns (lines, ends_with_newline).
    """
    if not payload_str:
        return [], True
    ends_with_nl = payload_str.endswith(("\n", "\r\n"))
    raw_lines = payload_str.splitlines(keepends=True)
    return raw_lines, ends_with_nl


def create_text_delta(
    base_payload: bytes,
    target_payload: bytes,
    base_oid: str,
    target_oid: str,
    object_type: GitObjectType = GitObjectType.BLOB,
    path: str = "",
) -> TextDelta | None:
    """Generate a plain-text unified diff delta from base_payload to target_payload.

    Returns None if:
    - Either payload contains null bytes or is not valid UTF-8.
    - Base and target are identical.
    - The generated delta is not smaller than storing target_payload in full.
    """
    if b"\x00" in base_payload or b"\x00" in target_payload:
        return None

    try:
        base_str = base_payload.decode("utf-8")
        target_str = target_payload.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if base_payload == target_payload:
        return None

    base_lines, base_ends_nl = _split_lines_preserving_eof(base_str)
    target_lines, target_ends_nl = _split_lines_preserving_eof(target_str)

    # Normalize lines for difflib: difflib requires newlines on all lines for proper comparison
    norm_base = [line if line.endswith("\n") else line + "\n" for line in base_lines]
    norm_target = [line if line.endswith("\n") else line + "\n" for line in target_lines]

    diff_iter = difflib.unified_diff(
        norm_base,
        norm_target,
        fromfile="base",
        tofile="target",
        lineterm="\n",
    )

    # Discard '--- base' and '+++ target' lines from difflib
    raw_diff_lines = list(diff_iter)
    hunk_lines: list[str] = []
    started = False

    base_pos = 0
    target_pos = 0

    for raw_line in raw_diff_lines:
        if raw_line.startswith("@@ "):
            started = True
            hunk_lines.append(raw_line)
            # Parse start positions from hunk header
            match = _HUNK_HEADER_RE.match(raw_line)
            assert match is not None
            base_pos = int(match.group(1)) - 1
            target_pos = int(match.group(3)) - 1
            continue

        if not started:
            continue

        hunk_lines.append(raw_line)

        # Check for missing newline at end of file
        if raw_line.startswith("-"):
            if not base_ends_nl and base_pos == len(base_lines) - 1:
                hunk_lines.append(_NO_NEWLINE_MARKER + "\n")
            base_pos += 1
        elif raw_line.startswith("+"):
            if not target_ends_nl and target_pos == len(target_lines) - 1:
                hunk_lines.append(_NO_NEWLINE_MARKER + "\n")
            target_pos += 1
        else:
            if not base_ends_nl and base_pos == len(base_lines) - 1:
                hunk_lines.append(_NO_NEWLINE_MARKER + "\n")
            base_pos += 1
            target_pos += 1

    diff_text = "".join(hunk_lines)
    if not diff_text.strip():
        return None

    candidate = TextDelta(
        object_type=object_type,
        base_oid=base_oid,
        target_oid=target_oid,
        diff_text=diff_text,
        path=path,
    )

    serialized = candidate.to_text().encode("utf-8")
    if len(serialized) >= len(target_payload):
        # Storing full payload is more efficient
        return None

    return candidate


def apply_text_delta(
    base_payload: bytes,
    delta: TextDelta,
    hash_algo: str = "sha1",
) -> bytes:
    """Apply a TextDelta to base_payload and return the reconstituted payload.

    Verifies that:
    1. Base payload matches delta.base_oid.
    2. Patch applies cleanly.
    3. Reconstituted object matches delta.target_oid bit-exactly.

    For trees, also validates ls-tree syntax and returns canonical binary tree payload.
    Raises ValueError on any context mismatch, patch failure, or OID discrepancy.
    """
    # 1. Base OID verification & decoding
    if delta.object_type == GitObjectType.TREE:
        if b"\x00" in base_payload:
            tree = GitTree.from_binary_payload(base_payload, hash_algo=hash_algo)
            base_str = tree.to_text()
        else:
            try:
                base_str = base_payload.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("Base payload is not valid UTF-8 text") from None
            tree = GitTree.from_text(base_str, hash_algo=hash_algo)
        if tree.oid != delta.base_oid:
            raise ValueError(
                f"Base object OID mismatch: expected {delta.base_oid}, computed {tree.oid}"
            )
    else:
        computed_base_oid = compute_oid(delta.object_type, base_payload, hash_algo=hash_algo)
        if computed_base_oid != delta.base_oid:
            raise ValueError(
                f"Base object OID mismatch: expected {delta.base_oid}, computed {computed_base_oid}"
            )
        try:
            base_str = base_payload.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Base payload is not valid UTF-8 text") from None

    base_lines, base_ends_nl = _split_lines_preserving_eof(base_str)
    # Normalized base lines with newline for uniform matching
    norm_base = [line if line.endswith(("\n", "\r\n")) else line + "\n" for line in base_lines]

    diff_lines = delta.diff_text.splitlines(keepends=True)
    target_lines: list[str] = []
    base_idx = 0
    in_hunk = False

    idx = 0
    while idx < len(diff_lines):
        line = diff_lines[idx]
        if line.startswith("@@ "):
            match = _HUNK_HEADER_RE.match(line)
            if not match:
                raise ValueError(f"Malformed hunk header: {line!r}")
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1

            # Adjust 1-based index to 0-based
            target_base_idx = 0 if old_count == 0 and old_start == 0 else old_start - 1

            if target_base_idx < base_idx:
                raise ValueError(f"Hunk out of order: target index {target_base_idx} < {base_idx}")

            # Copy unchanged base lines preceding this hunk
            while base_idx < target_base_idx:
                if base_idx >= len(base_lines):
                    raise ValueError(f"Hunk starts past end of base lines: {target_base_idx}")
                target_lines.append(base_lines[base_idx])
                base_idx += 1

            in_hunk = True
            idx += 1
            continue

        if not in_hunk:
            idx += 1
            continue

        if line.startswith(" "):
            # Context line
            context = line[1:]
            if base_idx >= len(norm_base):
                raise ValueError("Hunk context line beyond base file length")
            if norm_base[base_idx] != context:
                raise ValueError(
                    f"Hunk context mismatch at base line {base_idx + 1}:\n"
                    f"  expected: {norm_base[base_idx]!r}\n"
                    f"  found in diff: {context!r}"
                )
            target_lines.append(base_lines[base_idx])
            base_idx += 1
            idx += 1

        elif line.startswith("-"):
            # Deletion line
            deletion = line[1:]
            if base_idx >= len(norm_base):
                raise ValueError("Hunk deletion line beyond base file length")
            if norm_base[base_idx] != deletion:
                raise ValueError(
                    f"Hunk deletion mismatch at base line {base_idx + 1}:\n"
                    f"  expected: {norm_base[base_idx]!r}\n"
                    f"  found in diff: {deletion!r}"
                )
            base_idx += 1
            idx += 1
            # Check if next line is no-newline marker
            if idx < len(diff_lines) and diff_lines[idx].strip() == _NO_NEWLINE_MARKER:
                idx += 1

        elif line.startswith("+"):
            # Addition line
            added = line[1:]
            idx += 1
            # Check if next line is no-newline marker
            if idx < len(diff_lines) and diff_lines[idx].strip() == _NO_NEWLINE_MARKER:
                # Strip trailing newline from added line
                if added.endswith("\r\n"):
                    added = added[:-2]
                else:
                    added = added.removesuffix("\n")
                idx += 1
            target_lines.append(added)

        elif line.strip() == _NO_NEWLINE_MARKER:
            # Marker handled in previous addition/deletion branch; if loose, ignore or advance
            idx += 1

        else:
            # Trailing text or unrecognized line outside hunk
            idx += 1

    # Copy remaining base lines
    while base_idx < len(base_lines):
        target_lines.append(base_lines[base_idx])
        base_idx += 1

    reconstructed_str = "".join(target_lines)

    if delta.object_type == GitObjectType.TREE:
        # Reconstruct canonical binary tree payload and verify OID
        tree = GitTree.from_text(reconstructed_str, hash_algo=hash_algo)
        if tree.oid != delta.target_oid:
            raise ValueError(
                f"Reconstructed tree OID mismatch: expected {delta.target_oid}, computed {tree.oid}"
            )
        return tree.to_binary_payload()

    # Object is a blob
    reconstructed_bytes = reconstructed_str.encode("utf-8")
    computed_target_oid = compute_oid(GitObjectType.BLOB, reconstructed_bytes, hash_algo=hash_algo)
    if computed_target_oid != delta.target_oid:
        raise ValueError(
            f"Reconstructed blob OID mismatch: expected {delta.target_oid}, computed {computed_target_oid}"
        )
    return reconstructed_bytes
