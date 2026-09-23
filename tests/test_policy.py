"""Unit tests for inspection and quarantine policy engine."""

from pathlib import Path

import pytest

from ptbundle.objects import GitObjectType, compute_oid
from ptbundle.policy import (
    BlobClassification,
    BlobClassifier,
    QuarantineManifest,
    QuarantineRecord,
    WhitelistPolicy,
    extract_extension,
    load_sidechannel_objects,
)


def test_extract_extension() -> None:
    assert extract_extension("README.md") == "md"
    assert extract_extension("docs/image.PNG") == "png"
    assert extract_extension("archive.tar.gz") == "gz"
    assert extract_extension("bin/tool") == ""
    assert extract_extension(".gitignore") == ""
    assert extract_extension("foo.") == ""
    assert extract_extension("") == ""


def test_whitelist_policy_creation_and_checks() -> None:
    policy_empty = WhitelistPolicy.from_extensions(None)
    assert not policy_empty.is_allowed("png")

    policy = WhitelistPolicy.from_extensions(["png,,jpg,", "PDF", ".svg"])
    assert policy.is_allowed("png")
    assert policy.is_allowed("PNG")
    assert policy.is_allowed(".jpg")
    assert policy.is_allowed("pdf")
    assert policy.is_allowed("svg")
    assert not policy.is_allowed("exe")


def test_whitelist_policy_verify_signature() -> None:
    policy = WhitelistPolicy.from_extensions(["png", "jpg", "gif", "pdf", "custom"])

    # PNG
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
    invalid_png = b"MZ\x90\x00\x03fake-executable"
    assert policy.verify_signature("png", valid_png)
    assert not policy.verify_signature("png", invalid_png)

    # JPEG
    valid_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    invalid_jpg = b"random binary bytes"
    assert policy.verify_signature("jpg", valid_jpg)
    assert not policy.verify_signature("jpg", invalid_jpg)

    # GIF
    assert policy.verify_signature("gif", b"GIF87a\x01\x00...")
    assert policy.verify_signature("gif", b"GIF89a\x01\x00...")
    assert not policy.verify_signature("gif", b"not-a-gif")

    # PDF
    assert policy.verify_signature("pdf", b"%PDF-1.7\n...")
    assert not policy.verify_signature("pdf", b"not-a-pdf")

    # Unlisted signature format
    assert policy.verify_signature("custom", b"\x00\x01\x02\x03")


def test_blob_classifier_text_detection() -> None:
    classifier = BlobClassifier()

    # Empty payload is valid text
    assert classifier.is_text_payload(b"")

    # Standard ASCII and UTF-8
    assert classifier.is_text_payload(b"Hello world\n")
    assert classifier.is_text_payload("H\u00e9llo w\u00f6rld \u2728\n".encode("utf-8"))

    # Null byte in text makes it binary
    assert not classifier.is_text_payload(b"Hello\x00world")

    # Invalid UTF-8 sequence without null bytes
    assert not classifier.is_text_payload(b"\xff\xfe\xaa\xbb")


def test_blob_classifier_classification() -> None:
    policy = WhitelistPolicy.from_extensions(["png", "jpg"])
    classifier = BlobClassifier(policy)

    # UTF-8 text file
    c, reason = classifier.classify(b"print('hello')\n", "script.py")
    assert c == BlobClassification.TEXT
    assert reason == "utf8_text"

    # Non-text file without extension
    c, reason = classifier.classify(b"\x00\x01\x02", "bin/tool")
    assert c == BlobClassification.QUARANTINED
    assert reason == "missing_extension"

    # Non-text file with disallowed extension
    c, reason = classifier.classify(b"\x00\x01\x02", "document.docx")
    assert c == BlobClassification.QUARANTINED
    assert reason == "extension_not_whitelisted:docx"

    # Non-text file with whitelisted extension and valid signature
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00image-data"
    c, reason = classifier.classify(valid_png, "assets/logo.png")
    assert c == BlobClassification.BINARY_WHITELISTED
    assert reason == "whitelisted:png"

    # Non-text file with whitelisted extension but spoofed signature
    spoofed_png = b"\x7fELF\x02\x01\x01\x00not-a-png"
    c, reason = classifier.classify(spoofed_png, "assets/exploit.png")
    assert c == BlobClassification.QUARANTINED
    assert reason == "signature_mismatch:png"


def test_quarantine_manifest_roundtrip() -> None:
    oid1 = "1" * 40
    oid2 = "2" * 40
    records = [
        QuarantineRecord(
            oid=oid1, path="bin/malware.exe", size=1024, reason="extension_not_whitelisted:exe"
        ),
        QuarantineRecord(oid=oid2, path="logo.png", size=512, reason="signature_mismatch:png"),
    ]
    manifest = QuarantineManifest(records=records)
    text = manifest.to_text()

    assert text.startswith("# ptbundle quarantine manifest v1\n")
    assert f"quarantine {oid1} bin/malware.exe 1024 extension_not_whitelisted:exe" in text
    assert f"quarantine {oid2} logo.png 512 signature_mismatch:png" in text

    parsed = QuarantineManifest.from_text(text)
    assert len(parsed.records) == 2
    assert parsed.records[0] == records[0]
    assert parsed.records[1] == records[1]


def test_quarantine_manifest_parsing_edge_cases() -> None:
    oid = "0" * 40

    # With comments and blank lines
    raw = f"""
    # ptbundle quarantine manifest v1
    # Auditor notes here
    quarantine {oid} lib/native.so 4096 extension_not_whitelisted:so (contains binary code)
    """
    parsed = QuarantineManifest.from_text(raw)
    assert len(parsed.records) == 1
    assert parsed.records[0].oid == oid
    assert parsed.records[0].path == "lib/native.so"
    assert parsed.records[0].size == 4096
    assert parsed.records[0].reason == "extension_not_whitelisted:so (contains binary code)"

    # Missing header
    with pytest.raises(ValueError, match="Missing required"):
        QuarantineManifest.from_text("")

    # Not first non-empty line
    with pytest.raises(ValueError, match="Missing quarantine manifest header"):
        QuarantineManifest.from_text(f"quarantine {oid} foo 10 reason\n")

    # Malformed record line
    with pytest.raises(ValueError, match="Malformed quarantine record line"):
        QuarantineManifest.from_text("# ptbundle quarantine manifest v1\nquarantine\n")

    with pytest.raises(ValueError, match="Malformed quarantine record line"):
        QuarantineManifest.from_text("# ptbundle quarantine manifest v1\nother_cmd 123 456\n")

    # Invalid non-integer size
    with pytest.raises(ValueError, match="Invalid non-integer quarantine size"):
        QuarantineManifest.from_text(
            f"# ptbundle quarantine manifest v1\nquarantine {oid} path abc reason\n"
        )

    # Negative size
    with pytest.raises(ValueError, match="Negative quarantine size"):
        QuarantineManifest.from_text(
            f"# ptbundle quarantine manifest v1\nquarantine {oid} path -5 reason\n"
        )


def test_load_sidechannel_objects(tmp_path: Path) -> None:
    sidechannel = tmp_path / "cdrom"
    sidechannel.mkdir()

    # Non-existent directory raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        load_sidechannel_objects(tmp_path / "nonexistent")

    # Create nested quarantine files
    sub = sidechannel / "bin"
    sub.mkdir()
    payload1 = b"\x00\x01\x02\x03\x04"
    payload2 = b"\x89PNG\r\n\x1a\nvalid_png_content"

    file1 = sub / "tool.bin"
    file1.write_bytes(payload1)
    file2 = sidechannel / "image.png"
    file2.write_bytes(payload2)

    # Hidden file and quarantine-manifest.txt should be ignored
    (sidechannel / ".hidden").write_bytes(b"hidden")
    (sidechannel / "quarantine-manifest.txt").write_text("# ptbundle quarantine manifest v1\n")

    oid1 = compute_oid(GitObjectType.BLOB, payload1)
    oid2 = compute_oid(GitObjectType.BLOB, payload2)

    loaded = load_sidechannel_objects(sidechannel)
    assert len(loaded) == 2
    assert loaded[oid1] == payload1
    assert loaded[oid2] == payload2

    # Verification with matching manifest succeeds
    manifest = QuarantineManifest(
        records=[
            QuarantineRecord(oid=oid1, path="bin/tool.bin", size=len(payload1), reason="no_ext"),
            QuarantineRecord(oid=oid2, path="image.png", size=len(payload2), reason="whitelisted"),
        ]
    )
    loaded_checked = load_sidechannel_objects(sidechannel, manifest=manifest)
    assert loaded_checked == loaded

    # Verification with missing OID in manifest fails
    missing_oid = "f" * 40
    bad_manifest = QuarantineManifest(
        records=[
            QuarantineRecord(oid=missing_oid, path="missing.bin", size=10, reason="missing"),
        ]
    )
    with pytest.raises(ValueError, match="Missing 1 expected quarantine object"):
        load_sidechannel_objects(sidechannel, manifest=bad_manifest)
