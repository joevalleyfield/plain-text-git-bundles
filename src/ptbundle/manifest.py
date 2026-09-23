"""Manifest specification and parser/serializer for Plain-Text Git Bundles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BUNDLE_FORMAT_VERSION = 1
SUPPORTED_HASH_ALGOS = ("sha1", "sha256")

# Disallowed characters and patterns for Git reference names
_ILLEGAL_REF_CHARS = set(" ~^:?*[\\")
_HEX_RE_SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
_HEX_RE_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_oid(oid: str, hash_algo: str = "sha1") -> str:
    """Validate and normalize an object ID (OID) for the given hash algorithm.

    Returns the lowercase normalized OID string.
    Raises ValueError if the OID is malformed.
    """
    if hash_algo not in SUPPORTED_HASH_ALGOS:
        raise ValueError(
            f"Unsupported hash algorithm {hash_algo!r}. Supported: {SUPPORTED_HASH_ALGOS}"
        )

    expected_len = 40 if hash_algo == "sha1" else 64
    regex = _HEX_RE_SHA1 if hash_algo == "sha1" else _HEX_RE_SHA256

    if len(oid) != expected_len or not regex.match(oid):
        raise ValueError(f"Invalid {hash_algo} OID {oid!r}: must be {expected_len} hex characters")
    return oid.lower()


def validate_ref_name(name: str) -> str:
    """Validate a Git reference name for ingress safety and canonical structure.

    Enforces that the ref starts with 'refs/', contains no directory traversal ('..'),
    no reflog syntax ('@{'), no consecutive slashes ('//'), and no forbidden Git ref characters.
    """
    if not name:
        raise ValueError("Reference name cannot be empty")
    if not name.startswith("refs/"):
        raise ValueError(
            f"Invalid reference name {name!r}: must start with 'refs/' (e.g. 'refs/heads/...')"
        )
    if ".." in name:
        raise ValueError(f"Invalid reference name {name!r}: directory traversal '..' forbidden")
    if "@{" in name:
        raise ValueError(f"Invalid reference name {name!r}: reflog syntax '@{{' forbidden")
    if "//" in name:
        raise ValueError(f"Invalid reference name {name!r}: consecutive slashes forbidden")
    if name.endswith("/") or name.endswith(".lock") or name.endswith("."):
        raise ValueError(f"Invalid reference name {name!r}: illegal trailing characters")

    for ch in name:
        if ch in _ILLEGAL_REF_CHARS or ord(ch) < 32 or ord(ch) == 127:
            raise ValueError(f"Invalid reference name {name!r}: contains illegal character {ch!r}")

    # Check component rules (no component starting with dot)
    parts = name.split("/")
    for part in parts:
        if not part or part.startswith("."):
            raise ValueError(
                f"Invalid reference name {name!r}: components cannot be empty or start with '.'"
            )

    return name


@dataclass(frozen=True)
class ManifestPrerequisite:
    """A commit that must exist in the target repository before unpacking."""

    oid: str
    comment: str = ""

    def to_line(self) -> str:
        if self.comment:
            return f"prerequisite {self.oid} {self.comment}"
        return f"prerequisite {self.oid}"


@dataclass(frozen=True)
class ManifestRef:
    """A target reference head or tag being transferred."""

    name: str
    oid: str

    def to_line(self) -> str:
        return f"ref {self.name} {self.oid}"


@dataclass(frozen=True)
class ManifestMetrics:
    """Audit summary counts of objects contained in the bundle."""

    commits: int = 0
    trees: int = 0
    blobs_text: int = 0
    blobs_binary: int = 0
    blobs_quarantined: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "commits",
            "trees",
            "blobs_text",
            "blobs_binary",
            "blobs_quarantined",
        ):
            val = getattr(self, field_name)
            if not isinstance(val, int) or val < 0:
                raise ValueError(
                    f"Invalid metric {field_name}={val!r}: must be a non-negative integer"
                )

    def to_lines(self) -> list[str]:
        return [
            f"commits: {self.commits}",
            f"trees: {self.trees}",
            f"blobs_text: {self.blobs_text}",
            f"blobs_binary: {self.blobs_binary}",
            f"blobs_quarantined: {self.blobs_quarantined}",
        ]


@dataclass
class Manifest:
    """Plain-Text Git Bundle Transfer Manifest."""

    version: int = BUNDLE_FORMAT_VERSION
    hash_algo: str = "sha1"
    prerequisites: list[ManifestPrerequisite] = field(default_factory=list)
    refs: list[ManifestRef] = field(default_factory=list)
    metrics: ManifestMetrics = field(default_factory=ManifestMetrics)

    def validate(self) -> None:
        """Validate integrity and security constraints of the manifest."""
        if self.version != BUNDLE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported manifest version {self.version}. Only version {BUNDLE_FORMAT_VERSION} is supported."
            )
        if self.hash_algo not in SUPPORTED_HASH_ALGOS:
            raise ValueError(
                f"Unsupported hash algorithm {self.hash_algo!r}. Supported: {SUPPORTED_HASH_ALGOS}"
            )

        for prereq in self.prerequisites:
            validate_oid(prereq.oid, self.hash_algo)

        if not self.refs:
            raise ValueError("Manifest must declare at least one reference ('ref')")

        for r in self.refs:
            validate_ref_name(r.name)
            validate_oid(r.oid, self.hash_algo)

        # Trigger metrics validation
        self.metrics.__post_init__()

    def to_text(self) -> str:
        """Serialize manifest into canonical plain-text format."""
        self.validate()
        lines: list[str] = [
            f"# ptbundle v{self.version}",
            f"hash-algo {self.hash_algo}",
            "",
        ]

        if self.prerequisites:
            for prereq in self.prerequisites:
                lines.append(prereq.to_line())
            lines.append("")

        for r in self.refs:
            lines.append(r.to_line())
        lines.append("")

        lines.append("# Summary Metrics")
        lines.extend(self.metrics.to_lines())
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_text(cls, text: str) -> Manifest:
        """Parse a plain-text manifest file into a Manifest instance."""
        raw_lines = text.splitlines()

        # Find header
        version: int | None = None
        header_idx = -1
        for idx, line in enumerate(raw_lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("# ptbundle v"):
                version_str = stripped[len("# ptbundle v") :].strip()
                try:
                    version = int(version_str)
                except ValueError:
                    raise ValueError(
                        f"Malformed manifest version in header: {stripped!r}"
                    ) from None
                header_idx = idx
                break
            else:
                raise ValueError(
                    f"Manifest must start with '# ptbundle v<version>' header, found: {stripped!r}"
                )

        if version is None or header_idx == -1:
            raise ValueError("Manifest missing required '# ptbundle v<version>' header")

        hash_algo = "sha1"
        prerequisites: list[ManifestPrerequisite] = []
        refs: list[ManifestRef] = []
        metric_values: dict[str, int] = {}

        for line in raw_lines[header_idx + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                # Comment line
                continue

            # Check for standard git bundle prerequisite alias: -<oid> [comment]
            if stripped.startswith("-"):
                prereq_body = stripped[1:].strip()
                if not prereq_body:
                    raise ValueError(f"Malformed prerequisite alias line: {line!r}")
                oid, _, comment = prereq_body.partition(" ")
                clean_oid = validate_oid(oid.strip(), hash_algo)
                prerequisites.append(ManifestPrerequisite(oid=clean_oid, comment=comment.strip()))
                continue

            # Key-value / keyword parsing
            parts = stripped.split()
            cmd = parts[0].lower()

            if cmd in ("hash-algo", "object-format", "objectformat"):
                if len(parts) != 2:
                    raise ValueError(f"Malformed hash algorithm line: {line!r}")
                hash_algo = parts[1].lower()
                if hash_algo not in SUPPORTED_HASH_ALGOS:
                    raise ValueError(f"Unsupported hash algorithm: {hash_algo!r}")

            elif cmd == "prerequisite":
                if len(parts) < 2:
                    raise ValueError(f"Malformed prerequisite line: {line!r}")
                oid = parts[1]
                comment = stripped[len("prerequisite") :].strip()[len(oid) :].strip()
                clean_oid = validate_oid(oid, hash_algo)
                prerequisites.append(ManifestPrerequisite(oid=clean_oid, comment=comment))

            elif cmd == "ref":
                if len(parts) != 3:
                    raise ValueError(f"Malformed ref line: {line!r}")
                ref_name = validate_ref_name(parts[1])
                ref_oid = validate_oid(parts[2], hash_algo)
                refs.append(ManifestRef(name=ref_name, oid=ref_oid))

            elif ":" in cmd or (len(parts) >= 2 and parts[0].endswith(":")):
                # Metric in key: value format
                colon_idx = stripped.find(":")
                key = stripped[:colon_idx].strip().lower()
                val_str = stripped[colon_idx + 1 :].strip()
                try:
                    val = int(val_str)
                except ValueError:
                    raise ValueError(
                        f"Invalid non-integer metric value for {key}: {val_str!r}"
                    ) from None
                metric_values[key] = val

            elif cmd == "metric" and len(parts) == 3:
                key = parts[1].lower()
                try:
                    val = int(parts[2])
                except ValueError:
                    raise ValueError(
                        f"Invalid non-integer metric value for {key}: {parts[2]!r}"
                    ) from None
                metric_values[key] = val

            else:
                raise ValueError(f"Unknown or malformed manifest entry: {line!r}")

        metrics = ManifestMetrics(
            commits=metric_values.get("commits", 0),
            trees=metric_values.get("trees", 0),
            blobs_text=metric_values.get("blobs_text", 0),
            blobs_binary=metric_values.get("blobs_binary", 0),
            blobs_quarantined=metric_values.get("blobs_quarantined", 0),
        )

        manifest = cls(
            version=version,
            hash_algo=hash_algo,
            prerequisites=prerequisites,
            refs=refs,
            metrics=metrics,
        )
        manifest.validate()
        return manifest
