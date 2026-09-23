"""Inspection and quarantine policy engine for Plain-Text Git Bundles."""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ptbundle.manifest import validate_oid
from ptbundle.objects import GitObjectType, compute_oid

# Common file signatures (magic bytes) for anti-spoofing verification
_KNOWN_SIGNATURES: dict[str, list[bytes]] = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"],
    "pdf": [b"%PDF-"],
}


class BlobClassification(enum.Enum):
    """Classification of Git blob payloads for ingress and packaging."""

    TEXT = "text"
    BINARY_WHITELISTED = "binary_whitelisted"
    QUARANTINED = "quarantined"


def extract_extension(path: str) -> str:
    """Extract a clean, lowercase file extension without leading dot from a repository path.

    Returns an empty string if there is no extension (e.g. 'bin/tool', '.gitignore', 'foo.').
    """
    name = Path(path).name
    if "." not in name:
        return ""
    base, _, ext = name.rpartition(".")
    if not base or not ext:
        return ""
    return ext.lower()


@dataclass(frozen=True)
class WhitelistPolicy:
    """Binary extension whitelist policy with magic-byte anti-spoofing verification."""

    allowed_extensions: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_extensions(cls, extensions: Iterable[str] | None) -> WhitelistPolicy:
        """Create a WhitelistPolicy from an iterable or comma-delimited strings."""
        if not extensions:
            return cls()
        clean_exts: set[str] = set()
        for ext in extensions:
            for part in ext.split(","):
                cleaned = part.strip().lstrip(".").lower()
                if cleaned:
                    clean_exts.add(cleaned)
        return cls(allowed_extensions=frozenset(clean_exts))

    def is_allowed(self, ext: str) -> bool:
        """Check if an extension is on the whitelist."""
        normalized = ext.strip().lstrip(".").lower()
        return normalized in self.allowed_extensions

    def verify_signature(self, ext: str, payload: bytes) -> bool:
        """Verify that a binary payload matches expected magic bytes for known formats.

        Returns True if the format has no known signature or if the payload matches.
        Returns False if the format is known but the payload does not match (spoofing).
        """
        normalized = ext.strip().lstrip(".").lower()
        expected_prefixes = _KNOWN_SIGNATURES.get(normalized)
        if expected_prefixes is None:
            return True
        return any(payload.startswith(prefix) for prefix in expected_prefixes)


class BlobClassifier:
    """Classifies Git blob payloads into TEXT, BINARY_WHITELISTED, or QUARANTINED."""

    def __init__(self, policy: WhitelistPolicy | None = None) -> None:
        self.policy = policy or WhitelistPolicy()

    def is_text_payload(self, payload: bytes) -> bool:
        """Check if payload is valid UTF-8 and contains no null bytes (\\0)."""
        if b"\x00" in payload:
            return False
        try:
            payload.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    def classify(self, payload: bytes, path: str = "") -> tuple[BlobClassification, str]:
        """Classify a blob payload and return (classification, reason)."""
        if self.is_text_payload(payload):
            return BlobClassification.TEXT, "utf8_text"

        ext = extract_extension(path)
        if not ext:
            return BlobClassification.QUARANTINED, "missing_extension"

        if not self.policy.is_allowed(ext):
            return BlobClassification.QUARANTINED, f"extension_not_whitelisted:{ext}"

        if not self.policy.verify_signature(ext, payload):
            return BlobClassification.QUARANTINED, f"signature_mismatch:{ext}"

        return BlobClassification.BINARY_WHITELISTED, f"whitelisted:{ext}"


@dataclass(frozen=True)
class QuarantineRecord:
    """Record of a quarantined object in quarantine-manifest.txt."""

    oid: str
    path: str
    size: int
    reason: str

    def to_line(self) -> str:
        return f"quarantine {self.oid} {self.path} {self.size} {self.reason}"


@dataclass
class QuarantineManifest:
    """Quarantine manifest for out-of-band side-channel object delivery."""

    records: list[QuarantineRecord] = field(default_factory=list)

    def to_text(self) -> str:
        """Serialize quarantine manifest to plain-text string."""
        lines = ["# ptbundle quarantine manifest v1", ""]
        for r in self.records:
            lines.append(r.to_line())
        lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_text(cls, text: str, hash_algo: str = "sha1") -> QuarantineManifest:
        """Parse quarantine-manifest.txt into a QuarantineManifest instance."""
        raw_lines = text.splitlines()
        header_found = False
        records: list[QuarantineRecord] = []

        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == "# ptbundle quarantine manifest v1":
                header_found = True
                continue
            if stripped.startswith("#"):
                continue
            if not header_found:
                raise ValueError(f"Missing quarantine manifest header, found: {stripped!r}")

            parts = stripped.split()
            if len(parts) < 5 or parts[0] != "quarantine":
                raise ValueError(f"Malformed quarantine record line: {line!r}")

            _, oid, path, size_str = parts[0], parts[1], parts[2], parts[3]
            reason = " ".join(parts[4:])
            clean_oid = validate_oid(oid, hash_algo)
            try:
                size = int(size_str)
            except ValueError:
                raise ValueError(f"Invalid non-integer quarantine size: {size_str!r}") from None
            if size < 0:
                raise ValueError(f"Negative quarantine size: {size}")

            records.append(QuarantineRecord(oid=clean_oid, path=path, size=size, reason=reason))

        if not header_found:
            raise ValueError("Missing required '# ptbundle quarantine manifest v1' header")

        return cls(records=records)


def load_sidechannel_objects(
    sidechannel_dir: Path | str,
    manifest: QuarantineManifest | None = None,
    hash_algo: str = "sha1",
) -> dict[str, bytes]:
    """Scan side-channel directory recursively, compute Git blob OIDs, and verify against manifest.

    Returns a mapping of {oid: payload_bytes}.
    Raises FileNotFoundError if sidechannel_dir does not exist.
    Raises ValueError if expected objects in manifest are missing from the side-channel media.
    """
    root = Path(sidechannel_dir)
    if not root.is_dir():
        raise FileNotFoundError(
            f"Side-channel directory does not exist or is not a directory: {root}"
        )

    loaded: dict[str, bytes] = {}
    for entry in root.rglob("*"):
        if entry.is_file() and not entry.name.startswith("."):
            if entry.name == "quarantine-manifest.txt":
                continue
            payload = entry.read_bytes()
            oid = compute_oid(GitObjectType.BLOB, payload, hash_algo=hash_algo)
            loaded[oid] = payload

    if manifest is not None:
        expected_oids = {r.oid for r in manifest.records}
        missing_oids = expected_oids - set(loaded.keys())
        if missing_oids:
            raise ValueError(
                f"Missing {len(missing_oids)} expected quarantine object(s) in side-channel directory: {sorted(missing_oids)}"
            )

    return loaded
