"""Pack orchestrator: extracts Git revision deltas into plain-text bundles."""

from __future__ import annotations

from pathlib import Path

from ptbundle.manifest import Manifest, ManifestMetrics, ManifestPrerequisite, ManifestRef
from ptbundle.objects import GitCommit, GitObjectType, GitTree
from ptbundle.policy import (
    BlobClassification,
    BlobClassifier,
    QuarantineManifest,
    QuarantineRecord,
    WhitelistPolicy,
    extract_extension,
)
from ptbundle.repo import GitRepo, discover_delta


def pack_bundle(
    repo: GitRepo,
    rev_range: str,
    output_dir: Path | str,
    whitelist_policy: WhitelistPolicy | None = None,
    ref_name: str | None = None,
) -> Manifest:
    """Extract a revision delta from repo and emit a plain-text bundle directory."""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    delta = discover_delta(repo, rev_range, ref_name=ref_name)
    policy = whitelist_policy or WhitelistPolicy()
    classifier = BlobClassifier(policy)

    commits_dir = out / "commits"
    trees_dir = out / "trees"
    blobs_dir = out / "blobs"
    quarantine_dir = out / "quarantine"

    commits_count = 0
    trees_count = 0
    blobs_text_count = 0
    blobs_binary_count = 0
    blobs_quarantined_count = 0

    quarantine_records: list[QuarantineRecord] = []

    for obj in delta.objects:
        fanout = obj.oid[:2]
        rest = obj.oid[2:]

        if obj.type == GitObjectType.COMMIT:
            commit_dir = commits_dir / fanout
            commit_dir.mkdir(parents=True, exist_ok=True)
            commit = GitCommit.from_payload(obj.payload)
            # Write exact commit payload as text
            (commit_dir / f"{rest}.txt").write_bytes(commit.to_payload())
            commits_count += 1

        elif obj.type == GitObjectType.TREE:
            tree_dir = trees_dir / fanout
            tree_dir.mkdir(parents=True, exist_ok=True)
            tree = GitTree.from_binary_payload(obj.payload)
            # Write plain-text ls-tree notation (zero null bytes)
            (tree_dir / f"{rest}.txt").write_text(tree.to_text(), encoding="utf-8")
            trees_count += 1

        else:
            classification, reason = classifier.classify(obj.payload, obj.path)

            if classification == BlobClassification.TEXT:
                blob_dir = blobs_dir / fanout
                blob_dir.mkdir(parents=True, exist_ok=True)
                (blob_dir / f"{rest}.txt").write_bytes(obj.payload)
                blobs_text_count += 1

            elif classification == BlobClassification.BINARY_WHITELISTED:
                blob_dir = blobs_dir / fanout
                blob_dir.mkdir(parents=True, exist_ok=True)
                ext = extract_extension(obj.path) or "bin"
                (blob_dir / f"{rest}.{ext}").write_bytes(obj.payload)
                blobs_binary_count += 1

            else:
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                ext = extract_extension(obj.path) or "bin"
                (quarantine_dir / f"{obj.oid}.{ext}").write_bytes(obj.payload)
                quarantine_records.append(
                    QuarantineRecord(
                        oid=obj.oid,
                        path=obj.path,
                        size=len(obj.payload),
                        reason=reason,
                    )
                )
                blobs_quarantined_count += 1

    if quarantine_records:
        q_manifest = QuarantineManifest(records=quarantine_records)
        (quarantine_dir / "quarantine-manifest.txt").write_text(
            q_manifest.to_text(), encoding="utf-8"
        )

    prerequisites = [ManifestPrerequisite(oid=p) for p in delta.prerequisites]
    refs = [ManifestRef(name=delta.target_ref, oid=delta.target_oid)]
    metrics = ManifestMetrics(
        commits=commits_count,
        trees=trees_count,
        blobs_text=blobs_text_count,
        blobs_binary=blobs_binary_count,
        blobs_quarantined=blobs_quarantined_count,
    )

    manifest = Manifest(
        version=1,
        hash_algo="sha1",
        prerequisites=prerequisites,
        refs=refs,
        metrics=metrics,
    )

    (out / "manifest.txt").write_text(manifest.to_text(), encoding="utf-8")
    return manifest
