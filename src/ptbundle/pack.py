"""Pack orchestrator: extracts Git revision deltas into plain-text bundles."""

from __future__ import annotations

from pathlib import Path

from ptbundle.delta import create_text_delta
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
from ptbundle.repo import DeltaObject, GitRepo, discover_delta


def pack_bundle(
    repo: GitRepo,
    rev_range: str,
    output_dir: Path | str,
    whitelist_policy: WhitelistPolicy | None = None,
    ref_name: str | None = None,
    enable_delta: bool = True,
    thin: bool = True,
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
    trees_full_count = 0
    trees_delta_count = 0
    blobs_text_count = 0
    blobs_delta_count = 0
    blobs_binary_count = 0
    blobs_quarantined_count = 0

    quarantine_records: list[QuarantineRecord] = []
    last_seen_by_path: dict[tuple[GitObjectType, str], DeltaObject] = {}

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
            curr_tree = GitTree.from_binary_payload(obj.payload)
            curr_tree_text = curr_tree.to_text().encode("utf-8")

            # Check for tree delta opportunity against previously seen tree at the same path
            key = (GitObjectType.TREE, obj.path)
            delta_created = False
            if enable_delta and key in last_seen_by_path:
                prev_obj = last_seen_by_path[key]
                prev_tree = GitTree.from_binary_payload(prev_obj.payload)
                prev_tree_text = prev_tree.to_text().encode("utf-8")
                tree_delta = create_text_delta(
                    base_payload=prev_tree_text,
                    target_payload=curr_tree_text,
                    base_oid=prev_obj.oid,
                    target_oid=obj.oid,
                    object_type=GitObjectType.TREE,
                    path=obj.path,
                )
                if tree_delta is not None:
                    (tree_dir / f"{rest}.delta.txt").write_text(
                        tree_delta.to_text(), encoding="utf-8"
                    )
                    trees_delta_count += 1
                    delta_created = True
            elif enable_delta and thin and delta.prerequisites:
                for prereq in delta.prerequisites:
                    base_info = repo.get_object_at_revision(prereq, obj.path, GitObjectType.TREE)
                    if base_info is not None and base_info[0] != obj.oid:
                        base_oid, base_payload = base_info
                        prev_tree = GitTree.from_binary_payload(base_payload)
                        prev_tree_text = prev_tree.to_text().encode("utf-8")
                        tree_delta = create_text_delta(
                            base_payload=prev_tree_text,
                            target_payload=curr_tree_text,
                            base_oid=base_oid,
                            target_oid=obj.oid,
                            object_type=GitObjectType.TREE,
                            path=obj.path,
                        )
                        if tree_delta is not None:
                            (tree_dir / f"{rest}.delta.txt").write_text(
                                tree_delta.to_text(), encoding="utf-8"
                            )
                            trees_delta_count += 1
                            delta_created = True
                            break

            if not delta_created:
                # Write plain-text ls-tree notation (zero null bytes)
                (tree_dir / f"{rest}.txt").write_text(curr_tree.to_text(), encoding="utf-8")
                trees_full_count += 1

            last_seen_by_path[key] = obj

        else:
            classification, reason = classifier.classify(obj.payload, obj.path)

            if classification == BlobClassification.TEXT:
                blob_dir = blobs_dir / fanout
                blob_dir.mkdir(parents=True, exist_ok=True)

                # Check for blob delta opportunity against previously seen blob at the same path
                key = (GitObjectType.BLOB, obj.path)
                delta_created = False
                if enable_delta and key in last_seen_by_path:
                    prev_obj = last_seen_by_path[key]
                    if classifier.is_text_payload(prev_obj.payload):
                        blob_delta = create_text_delta(
                            base_payload=prev_obj.payload,
                            target_payload=obj.payload,
                            base_oid=prev_obj.oid,
                            target_oid=obj.oid,
                            object_type=GitObjectType.BLOB,
                            path=obj.path,
                        )
                        if blob_delta is not None:
                            (blob_dir / f"{rest}.delta.txt").write_text(
                                blob_delta.to_text(), encoding="utf-8"
                            )
                            blobs_delta_count += 1
                            delta_created = True
                elif enable_delta and thin and delta.prerequisites:
                    for prereq in delta.prerequisites:
                        base_info = repo.get_object_at_revision(
                            prereq, obj.path, GitObjectType.BLOB
                        )
                        if base_info is not None:
                            base_oid, base_payload = base_info
                            if base_oid != obj.oid and classifier.is_text_payload(base_payload):
                                blob_delta = create_text_delta(
                                    base_payload=base_payload,
                                    target_payload=obj.payload,
                                    base_oid=base_oid,
                                    target_oid=obj.oid,
                                    object_type=GitObjectType.BLOB,
                                    path=obj.path,
                                )
                                if blob_delta is not None:
                                    (blob_dir / f"{rest}.delta.txt").write_text(
                                        blob_delta.to_text(), encoding="utf-8"
                                    )
                                    blobs_delta_count += 1
                                    delta_created = True
                                    break

                if not delta_created:
                    (blob_dir / f"{rest}.txt").write_bytes(obj.payload)
                    blobs_text_count += 1

                last_seen_by_path[key] = obj

            elif classification == BlobClassification.BINARY_WHITELISTED:
                blob_dir = blobs_dir / fanout
                blob_dir.mkdir(parents=True, exist_ok=True)
                ext = extract_extension(obj.path) or "bin"
                (blob_dir / f"{rest}.{ext}").write_bytes(obj.payload)
                blobs_binary_count += 1
                last_seen_by_path[(GitObjectType.BLOB, obj.path)] = obj

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
                last_seen_by_path[(GitObjectType.BLOB, obj.path)] = obj

    if quarantine_records:
        q_manifest = QuarantineManifest(records=quarantine_records)
        (quarantine_dir / "quarantine-manifest.txt").write_text(
            q_manifest.to_text(), encoding="utf-8"
        )

    prerequisites = [ManifestPrerequisite(oid=p) for p in delta.prerequisites]
    refs = [ManifestRef(name=delta.target_ref, oid=delta.target_oid)]
    metrics = ManifestMetrics(
        commits=commits_count,
        trees=trees_full_count,
        trees_delta=trees_delta_count,
        blobs_text=blobs_text_count,
        blobs_delta=blobs_delta_count,
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
