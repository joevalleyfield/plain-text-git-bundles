"""Unit tests for ptbundle manifest specification, validation, and parsing."""

import pytest

from ptbundle.manifest import (
    Manifest,
    ManifestMetrics,
    ManifestPrerequisite,
    ManifestRef,
    validate_oid,
    validate_ref_name,
)


def test_validate_oid_sha1_and_sha256() -> None:
    valid_sha1 = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    valid_sha256 = "a" * 64

    assert validate_oid(valid_sha1, "sha1") == valid_sha1
    assert validate_oid(valid_sha1.upper(), "sha1") == valid_sha1
    assert validate_oid(valid_sha256, "sha256") == valid_sha256

    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        validate_oid(valid_sha1, "md5")

    with pytest.raises(ValueError, match="Invalid sha1 OID"):
        validate_oid("short", "sha1")

    with pytest.raises(ValueError, match="Invalid sha1 OID"):
        validate_oid("z" * 40, "sha1")

    with pytest.raises(ValueError, match="Invalid sha256 OID"):
        validate_oid("a" * 63, "sha256")


def test_validate_ref_name_valid_and_invalid() -> None:
    assert validate_ref_name("refs/heads/main") == "refs/heads/main"
    assert validate_ref_name("refs/tags/v1.0.0") == "refs/tags/v1.0.0"
    assert validate_ref_name("refs/heads/feature/sub-branch") == "refs/heads/feature/sub-branch"

    with pytest.raises(ValueError, match="cannot be empty"):
        validate_ref_name("")

    with pytest.raises(ValueError, match="must start with 'refs/'"):
        validate_ref_name("main")

    with pytest.raises(ValueError, match="directory traversal"):
        validate_ref_name("refs/heads/../../etc/passwd")

    with pytest.raises(ValueError, match="reflog syntax"):
        validate_ref_name("refs/heads/main@{1}")

    with pytest.raises(ValueError, match="consecutive slashes"):
        validate_ref_name("refs/heads//main")

    with pytest.raises(ValueError, match="illegal trailing characters"):
        validate_ref_name("refs/heads/main.lock")

    with pytest.raises(ValueError, match="illegal trailing characters"):
        validate_ref_name("refs/heads/main/")

    with pytest.raises(ValueError, match="illegal trailing characters"):
        validate_ref_name("refs/heads/main.")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main branch")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main^")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main~1")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main:foo")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main?bar")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main*bar")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main[bar]")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main\\bar")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main\x01bar")

    with pytest.raises(ValueError, match="illegal character"):
        validate_ref_name("refs/heads/main\x7fbar")

    with pytest.raises(ValueError, match="components cannot be empty or start with"):
        validate_ref_name("refs/heads/.hidden")


def test_manifest_metrics_validation() -> None:
    metrics = ManifestMetrics(
        commits=3,
        trees=7,
        trees_delta=2,
        blobs_text=10,
        blobs_delta=4,
        blobs_binary=2,
        blobs_quarantined=1,
    )
    assert metrics.commits == 3
    assert metrics.trees_delta == 2
    assert metrics.blobs_delta == 4
    lines = metrics.to_lines()
    assert "trees_delta: 2" in lines
    assert "blobs_delta: 4" in lines

    with pytest.raises(ValueError, match="Invalid metric commits=-1"):
        ManifestMetrics(commits=-1)

    with pytest.raises(ValueError, match="must be a non-negative integer"):
        ManifestMetrics(trees="seven")  # type: ignore[arg-type]


def test_manifest_roundtrip_sha1() -> None:
    prereq_oid = "4a5b6c7d8e9f0123456789abcdef0123456789ab"
    prereq_oid2 = "5a5b6c7d8e9f0123456789abcdef0123456789ab"
    head_oid = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"

    manifest = Manifest(
        version=1,
        hash_algo="sha1",
        prerequisites=[
            ManifestPrerequisite(oid=prereq_oid, comment="[origin/main]"),
            ManifestPrerequisite(oid=prereq_oid2, comment=""),
        ],
        refs=[ManifestRef(name="refs/heads/feature-xyz", oid=head_oid)],
        metrics=ManifestMetrics(
            commits=3, trees=7, blobs_text=32, blobs_binary=1, blobs_quarantined=0
        ),
    )

    text = manifest.to_text()
    assert text.startswith("# ptbundle v1\nhash-algo sha1\n")
    assert f"prerequisite {prereq_oid} [origin/main]" in text
    assert f"prerequisite {prereq_oid2}\n" in text
    assert f"ref refs/heads/feature-xyz {head_oid}" in text
    assert "commits: 3" in text

    parsed = Manifest.from_text(text)
    assert parsed.version == 1
    assert parsed.hash_algo == "sha1"
    assert len(parsed.prerequisites) == 2
    assert parsed.prerequisites[0].oid == prereq_oid
    assert parsed.prerequisites[0].comment == "[origin/main]"
    assert parsed.prerequisites[1].oid == prereq_oid2
    assert parsed.prerequisites[1].comment == ""
    assert len(parsed.refs) == 1
    assert parsed.refs[0].name == "refs/heads/feature-xyz"
    assert parsed.refs[0].oid == head_oid
    assert parsed.metrics.commits == 3
    assert parsed.metrics.trees == 7
    assert parsed.metrics.blobs_text == 32
    assert parsed.metrics.blobs_binary == 1
    assert parsed.metrics.blobs_quarantined == 0


def test_manifest_roundtrip_sha256_and_no_prereqs() -> None:
    head_oid = "a" * 64
    manifest = Manifest(
        version=1,
        hash_algo="sha256",
        prerequisites=[],
        refs=[ManifestRef(name="refs/heads/main", oid=head_oid)],
        metrics=ManifestMetrics(commits=1, trees=1, blobs_text=2),
    )

    text = manifest.to_text()
    assert "hash-algo sha256" in text
    assert "prerequisite" not in text

    parsed = Manifest.from_text(text)
    assert parsed.hash_algo == "sha256"
    assert len(parsed.prerequisites) == 0
    assert len(parsed.refs) == 1
    assert parsed.refs[0].oid == head_oid


def test_manifest_parsing_alias_and_formats() -> None:
    oid1 = "1" * 40
    oid2 = "2" * 40
    ref_oid = "3" * 40

    # Test git bundle '-' prerequisite alias, object-format line, and metric keyword line
    raw = f"""
    # ptbundle v1
    object-format sha1

    # Standard git bundle prerequisite format
    -{oid1} base-commit
    prerequisite {oid2}

    ref refs/heads/main {ref_oid}

    metric commits 10
    trees: 20
    blobs_text: 30
    blobs_binary: 0
    blobs_quarantined: 0
    """

    parsed = Manifest.from_text(raw)
    assert parsed.hash_algo == "sha1"
    assert len(parsed.prerequisites) == 2
    assert parsed.prerequisites[0].oid == oid1
    assert parsed.prerequisites[0].comment == "base-commit"
    assert parsed.prerequisites[1].oid == oid2
    assert parsed.prerequisites[1].comment == ""
    assert parsed.metrics.commits == 10
    assert parsed.metrics.trees == 20
    assert parsed.metrics.blobs_text == 30


def test_manifest_missing_or_invalid_headers() -> None:
    with pytest.raises(ValueError, match="missing required"):
        Manifest.from_text("")

    with pytest.raises(ValueError, match="Manifest must start with"):
        Manifest.from_text("prerequisite 1234\n")

    with pytest.raises(ValueError, match="Malformed manifest version"):
        Manifest.from_text("# ptbundle vNotANumber\n")

    with pytest.raises(ValueError, match="Unsupported manifest version 2"):
        Manifest.from_text("# ptbundle v2\nref refs/heads/main " + "0" * 40)

    # In validate() directly
    m = Manifest(version=99, refs=[ManifestRef("refs/heads/m", "0" * 40)])
    with pytest.raises(ValueError, match="Unsupported manifest version"):
        m.validate()


def test_manifest_validation_rules() -> None:
    head_oid = "0" * 40

    # Unsupported hash algorithm in Manifest
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        Manifest(hash_algo="invalid", refs=[ManifestRef("refs/heads/main", head_oid)]).validate()

    # No refs declared
    with pytest.raises(ValueError, match="declare at least one reference"):
        Manifest(refs=[]).validate()

    # Bad prerequisite OID
    with pytest.raises(ValueError, match="Invalid sha1 OID"):
        Manifest(
            prerequisites=[ManifestPrerequisite(oid="bad")],
            refs=[ManifestRef("refs/heads/main", head_oid)],
        ).validate()


def test_manifest_parser_syntax_errors() -> None:
    head_oid = "0" * 40

    # Malformed prerequisite alias
    with pytest.raises(ValueError, match="Malformed prerequisite alias"):
        Manifest.from_text("# ptbundle v1\n-\n")

    # Malformed prerequisite line
    with pytest.raises(ValueError, match="Malformed prerequisite line"):
        Manifest.from_text("# ptbundle v1\nprerequisite\n")

    # Malformed ref line
    with pytest.raises(ValueError, match="Malformed ref line"):
        Manifest.from_text("# ptbundle v1\nref refs/heads/main\n")

    # Malformed hash-algo line
    with pytest.raises(ValueError, match="Malformed hash algorithm line"):
        Manifest.from_text("# ptbundle v1\nhash-algo sha1 extra\n")

    # Unsupported hash algorithm in parser
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        Manifest.from_text("# ptbundle v1\nhash-algo md5\n")

    # Invalid non-integer metric (key: val)
    with pytest.raises(ValueError, match="Invalid non-integer metric"):
        Manifest.from_text(f"# ptbundle v1\nref refs/heads/m {head_oid}\ncommits: abc\n")

    # Invalid non-integer metric (metric key val)
    with pytest.raises(ValueError, match="Invalid non-integer metric"):
        Manifest.from_text(f"# ptbundle v1\nref refs/heads/m {head_oid}\nmetric commits abc\n")

    # Unknown or malformed line
    with pytest.raises(ValueError, match="Unknown or malformed manifest entry"):
        Manifest.from_text(
            f"# ptbundle v1\nref refs/heads/m {head_oid}\nrandom unrecognized stuff\n"
        )
