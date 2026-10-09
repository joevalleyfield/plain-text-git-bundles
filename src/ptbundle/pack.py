"""Pack orchestrator: extracts Git revision deltas into plain-text bundles."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Protocol

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


class BundleWriter(Protocol):
    """Protocol for emitting bundle artifacts to disk or an archive."""

    def write_bytes(self, rel_path: str, data: bytes) -> None: ...

    def write_text(self, rel_path: str, text: str, encoding: str = "utf-8") -> None: ...

    def close(self) -> None: ...


class DirectoryBundleWriter:
    """Emits bundle files into a directory hierarchy."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        dest = self.root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def write_text(self, rel_path: str, text: str, encoding: str = "utf-8") -> None:
        dest = self.root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding=encoding)

    def close(self) -> None:
        pass


class ZipBundleWriter:
    """Emits bundle files directly into a standard or uncompressed zip archive."""

    def __init__(self, zip_path: Path, compression: int = zipfile.ZIP_DEFLATED) -> None:
        self.zip_path = zip_path
        self.zip_path.parent.mkdir(parents=True, exist_ok=True)
        self.zf = zipfile.ZipFile(zip_path, mode="w", compression=compression)

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        self.zf.writestr(rel_path, data)

    def write_text(self, rel_path: str, text: str, encoding: str = "utf-8") -> None:
        self.zf.writestr(rel_path, text.encode(encoding))

    def close(self) -> None:
        self.zf.close()


def pack_bundle(
    repo: GitRepo,
    rev_range: str,
    output_dir: Path | str,
    whitelist_policy: WhitelistPolicy | None = None,
    ref_name: str | None = None,
    enable_delta: bool = True,
    thin: bool = True,
    zip_compression: int = zipfile.ZIP_DEFLATED,
) -> Manifest:
    """Extract a revision delta from repo and emit a plain-text bundle directory or .zip archive."""
    out_path = Path(output_dir).resolve()
    writer: BundleWriter
    if str(output_dir).endswith(".zip"):
        writer = ZipBundleWriter(out_path, compression=zip_compression)
    else:
        writer = DirectoryBundleWriter(out_path)

    delta = discover_delta(repo, rev_range, ref_name=ref_name)
    policy = whitelist_policy or WhitelistPolicy()
    classifier = BlobClassifier(policy)

    commits_count = 0
    trees_full_count = 0
    trees_delta_count = 0
    blobs_text_count = 0
    blobs_delta_count = 0
    blobs_binary_count = 0
    blobs_quarantined_count = 0

    quarantine_records: list[QuarantineRecord] = []
    last_seen_by_path: dict[tuple[GitObjectType, str], DeltaObject] = {}

    try:
        for obj in delta.objects:
            fanout = obj.oid[:2]
            rest = obj.oid[2:]

            if obj.type == GitObjectType.COMMIT:
                commit = GitCommit.from_payload(obj.payload)
                # Write exact commit payload as text
                writer.write_bytes(f"commits/{fanout}/{rest}.txt", commit.to_payload())
                commits_count += 1

            elif obj.type == GitObjectType.TREE:
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
                        writer.write_text(f"trees/{fanout}/{rest}.delta.txt", tree_delta.to_text())
                        trees_delta_count += 1
                        delta_created = True
                elif enable_delta and thin and delta.prerequisites:
                    for prereq in delta.prerequisites:
                        base_info = repo.get_object_at_revision(
                            prereq, obj.path, GitObjectType.TREE
                        )
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
                                writer.write_text(
                                    f"trees/{fanout}/{rest}.delta.txt", tree_delta.to_text()
                                )
                                trees_delta_count += 1
                                delta_created = True
                                break

                if not delta_created:
                    # Write plain-text ls-tree notation (zero null bytes)
                    writer.write_text(f"trees/{fanout}/{rest}.txt", curr_tree.to_text())
                    trees_full_count += 1

                last_seen_by_path[key] = obj

            else:
                classification, reason = classifier.classify(obj.payload, obj.path)

                if classification == BlobClassification.TEXT:
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
                                writer.write_text(
                                    f"blobs/{fanout}/{rest}.delta.txt", blob_delta.to_text()
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
                                        writer.write_text(
                                            f"blobs/{fanout}/{rest}.delta.txt",
                                            blob_delta.to_text(),
                                        )
                                        blobs_delta_count += 1
                                        delta_created = True
                                        break

                    if not delta_created:
                        writer.write_bytes(f"blobs/{fanout}/{rest}.txt", obj.payload)
                        blobs_text_count += 1

                    last_seen_by_path[key] = obj

                elif classification == BlobClassification.BINARY_WHITELISTED:
                    ext = extract_extension(obj.path) or "bin"
                    writer.write_bytes(f"blobs/{fanout}/{rest}.{ext}", obj.payload)
                    blobs_binary_count += 1
                    last_seen_by_path[(GitObjectType.BLOB, obj.path)] = obj

                else:
                    ext = extract_extension(obj.path) or "bin"
                    writer.write_bytes(f"quarantine/{obj.oid}.{ext}", obj.payload)
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
            writer.write_text("quarantine/quarantine-manifest.txt", q_manifest.to_text())

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

        writer.write_text("manifest.txt", manifest.to_text())
        return manifest
    finally:
        writer.close()
