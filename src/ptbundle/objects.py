"""Git object models, canonical serialization, and OID hashing for ptbundle.

Implements zero-dependency Python representations for Git objects (blob, tree, commit, tag)
supporting bit-exact SHA-1/SHA-256 canonical hashing and bidirectional plain-text serialization.
"""

from __future__ import annotations

import abc
import enum
import hashlib
from dataclasses import dataclass, field


class GitObjectType(str, enum.Enum):
    """Git canonical object types."""

    BLOB = "blob"
    TREE = "tree"
    COMMIT = "commit"
    TAG = "tag"


def compute_oid(
    obj_type: GitObjectType | str,
    payload: bytes,
    hash_algo: str = "sha1",
) -> str:
    """Compute canonical Git Object ID (OID) for a given object type and payload.

    Git framing format: `<type> <size>\0<payload>`
    """
    type_str = obj_type.value if isinstance(obj_type, GitObjectType) else str(obj_type)
    header = f"{type_str} {len(payload)}\0".encode("ascii")
    full_data = header + payload

    algo = hash_algo.lower()
    if algo == "sha1":
        return hashlib.sha1(full_data).hexdigest()
    if algo == "sha256":
        return hashlib.sha256(full_data).hexdigest()
    raise ValueError(f"Unsupported hash algorithm: {hash_algo} (must be 'sha1' or 'sha256')")


def format_git_object(obj_type: GitObjectType | str, payload: bytes) -> bytes:
    """Format an uncompressed loose Git object buffer (<type> <size>\0<payload>)."""
    type_str = obj_type.value if isinstance(obj_type, GitObjectType) else str(obj_type)
    header = f"{type_str} {len(payload)}\0".encode("ascii")
    return header + payload


def parse_git_object(raw: bytes) -> tuple[GitObjectType, bytes]:
    """Parse an uncompressed loose Git object buffer into (obj_type, payload)."""
    null_idx = raw.find(b"\0")
    if null_idx == -1:
        raise ValueError("Malformed Git object: missing null byte header separator")

    header_parts = raw[:null_idx].decode("ascii", errors="replace").split(" ")
    if len(header_parts) != 2:
        raise ValueError(f"Malformed Git object header: {raw[:null_idx]!r}")

    obj_type = GitObjectType(header_parts[0])
    declared_size = int(header_parts[1])
    payload = raw[null_idx + 1 :]

    if len(payload) != declared_size:
        raise ValueError(f"Size mismatch: header specifies {declared_size}, got {len(payload)}")

    return obj_type, payload


def tree_entry_sort_key(path: str, is_tree: bool) -> bytes:
    """Compute Git canonical tree collation key.

    Git sorts tree entries byte-by-byte by name, treating subtrees as if suffixed with '/'.
    """
    raw_path = path.encode("utf-8")
    return raw_path + (b"/" if is_tree else b"")


class GitObject(abc.ABC):
    """Abstract base class for Git objects."""

    hash_algo: str = "sha1"

    @property
    @abc.abstractmethod
    def type(self) -> GitObjectType:
        """Git object type."""

    @abc.abstractmethod
    def to_payload(self) -> bytes:
        """Emit raw Git payload bytes (excluding the Git header frame)."""

    @property
    def oid(self) -> str:
        """Compute the Git OID for this object."""
        return compute_oid(self.type, self.to_payload(), hash_algo=self.hash_algo)


@dataclass(frozen=True)
class GitBlob(GitObject):
    """Git blob object containing file content."""

    payload: bytes
    hash_algo: str = "sha1"

    @property
    def type(self) -> GitObjectType:
        return GitObjectType.BLOB

    def to_payload(self) -> bytes:
        return self.payload

    def is_utf8_text(self) -> bool:
        """Return True if the payload is valid UTF-8 and contains no null bytes."""
        if b"\0" in self.payload:
            return False
        try:
            self.payload.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def decode_text(self) -> str:
        """Decode the blob payload as UTF-8 string."""
        return self.payload.decode("utf-8")

    @classmethod
    def from_text(cls, text: str, hash_algo: str = "sha1") -> GitBlob:
        """Construct a GitBlob from a UTF-8 string."""
        return cls(payload=text.encode("utf-8"), hash_algo=hash_algo)


@dataclass(frozen=True)
class GitTreeEntry:
    """Entry inside a Git tree object."""

    mode: str  # Standard 6-digit octal string (e.g. '100644', '040000', '100755', '120000')
    type: GitObjectType
    oid: str
    path: str

    def __post_init__(self) -> None:
        # Normalize mode to 6 digits (e.g. '40000' -> '040000')
        if len(self.mode) < 6:
            object.__setattr__(self, "mode", self.mode.zfill(6))

    @property
    def is_tree(self) -> bool:
        return self.type == GitObjectType.TREE

    def sort_key(self) -> bytes:
        return tree_entry_sort_key(self.path, self.is_tree)

    def to_text_line(self) -> str:
        """Emit standard tab-separated ls-tree format: <mode> <type> <hex_oid>\t<path>."""
        return f"{self.mode} {self.type.value} {self.oid}\t{self.path}\n"


@dataclass(frozen=True)
class GitTree(GitObject):
    """Git tree object representing a directory index."""

    entries: list[GitTreeEntry] = field(default_factory=list)
    hash_algo: str = "sha1"

    @property
    def type(self) -> GitObjectType:
        return GitObjectType.TREE

    def sorted_entries(self) -> list[GitTreeEntry]:
        """Return entries sorted according to Git's canonical tree sorting rules."""
        return sorted(self.entries, key=lambda e: e.sort_key())

    def to_payload(self) -> bytes:
        return self.to_binary_payload()

    def to_binary_payload(self) -> bytes:
        """Serialize into canonical binary Git tree payload."""
        sorted_items = self.sorted_entries()
        chunks: list[bytes] = []
        for entry in sorted_items:
            # Mode in binary tree has no leading zeros
            mode_oct = f"{int(entry.mode, 8):o}".encode("ascii")
            path_bytes = entry.path.encode("utf-8")
            oid_bytes = bytes.fromhex(entry.oid)
            chunks.append(mode_oct + b" " + path_bytes + b"\0" + oid_bytes)
        return b"".join(chunks)

    @classmethod
    def from_binary_payload(cls, payload: bytes, hash_algo: str = "sha1") -> GitTree:
        """Parse canonical binary Git tree payload."""
        oid_len = 32 if hash_algo.lower() == "sha256" else 20
        entries: list[GitTreeEntry] = []
        idx = 0
        total_len = len(payload)

        while idx < total_len:
            space_idx = payload.find(b" ", idx)
            null_idx = payload.find(b"\0", space_idx)
            if space_idx == -1 or null_idx == -1 or null_idx + 1 + oid_len > total_len:
                raise ValueError(f"Corrupt binary tree entry at offset {idx}")

            mode_str = payload[idx:space_idx].decode("ascii")
            path = payload[space_idx + 1 : null_idx].decode("utf-8")
            oid_bytes = payload[null_idx + 1 : null_idx + 1 + oid_len]
            oid_hex = oid_bytes.hex()

            # Determine type from mode
            mode_int = int(mode_str, 8)
            entry_type = (
                GitObjectType.TREE if (mode_int & 0o170000 == 0o040000) else GitObjectType.BLOB
            )

            entries.append(
                GitTreeEntry(
                    mode=f"{mode_int:06o}",
                    type=entry_type,
                    oid=oid_hex,
                    path=path,
                )
            )
            idx = null_idx + 1 + oid_len

        return cls(entries=entries, hash_algo=hash_algo)

    def to_text(self) -> str:
        """Serialize tree into plain-text ls-tree format."""
        return "".join(entry.to_text_line() for entry in self.sorted_entries())

    @classmethod
    def from_text(cls, text: str, hash_algo: str = "sha1") -> GitTree:
        """Parse plain-text ls-tree format into GitTree."""
        entries: list[GitTreeEntry] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "\t" not in line:
                raise ValueError(f"Invalid ls-tree line (missing tab separator): {line!r}")

            meta, path = line.split("\t", 1)
            parts = meta.split(" ")
            if len(parts) != 3:
                raise ValueError(f"Invalid ls-tree metadata prefix: {meta!r}")

            mode, type_str, oid = parts
            entries.append(
                GitTreeEntry(
                    mode=mode,
                    type=GitObjectType(type_str),
                    oid=oid,
                    path=path,
                )
            )
        return cls(entries=entries, hash_algo=hash_algo)


@dataclass(frozen=True)
class GitCommit(GitObject):
    """Git commit object."""

    tree_oid: str
    author: str
    committer: str
    parent_oids: list[str] = field(default_factory=list)
    message: str = ""
    extra_headers: list[tuple[str, str]] = field(default_factory=list)
    hash_algo: str = "sha1"

    @property
    def type(self) -> GitObjectType:
        return GitObjectType.COMMIT

    def to_payload(self) -> bytes:
        """Format commit payload."""
        lines: list[str] = [f"tree {self.tree_oid}"]
        for parent in self.parent_oids:
            lines.append(f"parent {parent}")
        lines.append(f"author {self.author}")
        lines.append(f"committer {self.committer}")
        for key, val in self.extra_headers:
            # Multi-line headers (e.g. gpgsig) indent subsequent lines with a space in Git
            indented_val = val.replace("\n", "\n ")
            lines.append(f"{key} {indented_val}")

        header_block = "\n".join(lines) + "\n\n"
        return header_block.encode("utf-8") + self.message.encode("utf-8")

    @classmethod
    def from_payload(cls, payload: bytes, hash_algo: str = "sha1") -> GitCommit:
        """Parse Git commit payload bytes."""
        sep_idx = payload.find(b"\n\n")
        if sep_idx == -1:
            raise ValueError("Malformed commit: missing header/body separator (\\n\\n)")

        header_bytes = payload[:sep_idx]
        message = payload[sep_idx + 2 :].decode("utf-8", errors="replace")

        # Parse headers, accounting for multi-line headers prefixed with space
        raw_lines = header_bytes.decode("utf-8", errors="replace").splitlines()
        header_lines: list[str] = []
        for line in raw_lines:
            if line.startswith(" ") and header_lines:
                header_lines[-1] += "\n" + line[1:]
            else:
                header_lines.append(line)

        tree_oid: str | None = None
        parent_oids: list[str] = []
        author: str | None = None
        committer: str | None = None
        extra_headers: list[tuple[str, str]] = []

        for hline in header_lines:
            if not hline:
                continue
            key, _, val = hline.partition(" ")
            if key == "tree":
                tree_oid = val
            elif key == "parent":
                parent_oids.append(val)
            elif key == "author":
                author = val
            elif key == "committer":
                committer = val
            else:
                extra_headers.append((key, val))

        if tree_oid is None or author is None or committer is None:
            raise ValueError("Missing required commit fields (tree, author, or committer)")

        return cls(
            tree_oid=tree_oid,
            parent_oids=parent_oids,
            author=author,
            committer=committer,
            message=message,
            extra_headers=extra_headers,
            hash_algo=hash_algo,
        )


@dataclass(frozen=True)
class GitTag(GitObject):
    """Git annotated tag object."""

    object_oid: str
    object_type: GitObjectType
    tag_name: str
    tagger: str = ""
    message: str = ""
    extra_headers: list[tuple[str, str]] = field(default_factory=list)
    hash_algo: str = "sha1"

    @property
    def type(self) -> GitObjectType:
        return GitObjectType.TAG

    def to_payload(self) -> bytes:
        lines: list[str] = [
            f"object {self.object_oid}",
            f"type {self.object_type.value}",
            f"tag {self.tag_name}",
        ]
        if self.tagger:
            lines.append(f"tagger {self.tagger}")
        for key, val in self.extra_headers:
            indented_val = val.replace("\n", "\n ")
            lines.append(f"{key} {indented_val}")

        header_block = "\n".join(lines) + "\n\n"
        return header_block.encode("utf-8") + self.message.encode("utf-8")

    @classmethod
    def from_payload(cls, payload: bytes, hash_algo: str = "sha1") -> GitTag:
        sep_idx = payload.find(b"\n\n")
        if sep_idx == -1:
            raise ValueError("Malformed tag: missing header/body separator (\\n\\n)")

        header_bytes = payload[:sep_idx]
        message = payload[sep_idx + 2 :].decode("utf-8", errors="replace")

        raw_lines = header_bytes.decode("utf-8", errors="replace").splitlines()
        header_lines: list[str] = []
        for line in raw_lines:
            if line.startswith(" ") and header_lines:
                header_lines[-1] += "\n" + line[1:]
            else:
                header_lines.append(line)

        object_oid: str | None = None
        object_type: GitObjectType | None = None
        tag_name: str | None = None
        tagger: str = ""
        extra_headers: list[tuple[str, str]] = []

        for hline in header_lines:
            if not hline:
                continue
            key, _, val = hline.partition(" ")
            if key == "object":
                object_oid = val
            elif key == "type":
                object_type = GitObjectType(val)
            elif key == "tag":
                tag_name = val
            elif key == "tagger":
                tagger = val
            else:
                extra_headers.append((key, val))

        if object_oid is None or object_type is None or tag_name is None:
            raise ValueError("Missing required tag fields (object, type, or tag)")

        return cls(
            object_oid=object_oid,
            object_type=object_type,
            tag_name=tag_name,
            tagger=tagger,
            message=message,
            extra_headers=extra_headers,
            hash_algo=hash_algo,
        )
