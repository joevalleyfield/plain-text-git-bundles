"""Unpack orchestrator: verifies and injects plain-text bundles into Git repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ptbundle.delta import TextDelta, apply_text_delta
from ptbundle.manifest import Manifest, ManifestMetrics
from ptbundle.objects import GitCommit, GitObjectType, GitTree, compute_oid
from ptbundle.policy import QuarantineManifest, load_sidechannel_objects
from ptbundle.repo import GitRepo, inject_loose_object, update_reference, verify_prerequisites


@dataclass(frozen=True)
class UnpackResult:
    """Outcome of a successful bundle unpack operation."""

    target_ref: str
    target_oid: str
    objects_injected: int
    metrics: ManifestMetrics


def unpack_bundle(
    repo: GitRepo,
    bundle_dir: Path | str,
    sidechannel_dir: Path | str | None = None,
) -> UnpackResult:
    """Verify and unpack a plain-text bundle into the target Git repository."""
    b_dir = Path(bundle_dir).resolve()
    manifest_file = b_dir / "manifest.txt"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Bundle directory missing manifest.txt: {b_dir}")

    manifest = Manifest.from_text(manifest_file.read_text(encoding="utf-8"))

    # 1. Prerequisite verification
    verify_prerequisites(repo, [p.oid for p in manifest.prerequisites])

    # 2. Cryptographic verification & collection (Phase 1)
    objects_to_inject: list[tuple[GitObjectType, bytes]] = []

    # Commits
    commits_dir = b_dir / "commits"
    if commits_dir.is_dir():
        for file in commits_dir.rglob("*.txt"):
            expected_oid = file.parent.name + file.stem
            payload = file.read_bytes()
            commit = GitCommit.from_payload(payload, hash_algo=manifest.hash_algo)
            if commit.oid != expected_oid:
                raise ValueError(
                    f"Commit OID mismatch in {file.name}: expected {expected_oid}, computed {commit.oid}"
                )
            objects_to_inject.append((GitObjectType.COMMIT, commit.to_payload()))

    # Trees (Full and Delta)
    trees_dir = b_dir / "trees"
    if trees_dir.is_dir():
        resolved_trees: dict[str, GitTree] = {}
        pending_tree_deltas: list[TextDelta] = []

        for file in trees_dir.rglob("*.txt"):
            if file.name.endswith(".delta.txt"):
                rest = file.name[:-10]
                expected_oid = file.parent.name + rest
                delta = TextDelta.from_text(
                    file.read_text(encoding="utf-8"),
                    hash_algo=manifest.hash_algo,
                )
                if delta.target_oid != expected_oid:
                    raise ValueError(
                        f"Tree delta target OID mismatch in {file.name}: expected {expected_oid}, found {delta.target_oid}"
                    )
                pending_tree_deltas.append(delta)
            else:
                expected_oid = file.parent.name + file.stem
                tree_text = file.read_text(encoding="utf-8")
                tree = GitTree.from_text(tree_text, hash_algo=manifest.hash_algo)
                if tree.oid != expected_oid:
                    raise ValueError(
                        f"Tree OID mismatch in {file.name}: expected {expected_oid}, computed {tree.oid}"
                    )
                resolved_trees[expected_oid] = tree

        # Topologically resolve tree deltas
        while pending_tree_deltas:
            progress = False
            for delta in list(pending_tree_deltas):
                base_tree_text: bytes | None = None
                if delta.base_oid in resolved_trees:
                    base_tree = resolved_trees[delta.base_oid]
                    base_tree_text = base_tree.to_text().encode("utf-8")
                else:
                    # Attempt to resolve external base tree from target repository
                    raw_tree = repo.read_raw_object(delta.base_oid, GitObjectType.TREE)
                    if raw_tree is not None:
                        base_tree = GitTree.from_binary_payload(
                            raw_tree, hash_algo=manifest.hash_algo
                        )
                        base_tree_text = base_tree.to_text().encode("utf-8")

                if base_tree_text is not None:
                    binary_payload = apply_text_delta(
                        base_tree_text, delta, hash_algo=manifest.hash_algo
                    )
                    resolved_trees[delta.target_oid] = GitTree.from_binary_payload(
                        binary_payload, hash_algo=manifest.hash_algo
                    )
                    pending_tree_deltas.remove(delta)
                    progress = True
            if not progress:
                unresolved = sorted({d.target_oid for d in pending_tree_deltas})
                raise ValueError(
                    f"Unresolvable tree deltas (missing base objects in bundle and target repo): {unresolved}"
                )

        for tree in resolved_trees.values():
            objects_to_inject.append((GitObjectType.TREE, tree.to_binary_payload()))

    # Blobs (Full, Delta, and Quarantined)
    blobs_dir = b_dir / "blobs"
    resolved_blobs: dict[str, bytes] = {}
    pending_blob_deltas: list[TextDelta] = []

    if blobs_dir.is_dir():
        for file in blobs_dir.rglob("*"):
            if not file.is_file() or file.name.startswith("."):
                continue

            if file.name.endswith(".delta.txt"):
                rest = file.name[:-10]
                expected_oid = file.parent.name + rest
                delta = TextDelta.from_text(
                    file.read_text(encoding="utf-8"),
                    hash_algo=manifest.hash_algo,
                )
                if delta.target_oid != expected_oid:
                    raise ValueError(
                        f"Blob delta target OID mismatch in {file.name}: expected {expected_oid}, found {delta.target_oid}"
                    )
                pending_blob_deltas.append(delta)
            else:
                expected_oid = file.parent.name + file.stem
                payload = file.read_bytes()
                computed_oid = compute_oid(
                    GitObjectType.BLOB, payload, hash_algo=manifest.hash_algo
                )
                if computed_oid != expected_oid:
                    raise ValueError(
                        f"Blob OID mismatch in {file.name}: expected {expected_oid}, computed {computed_oid}"
                    )
                resolved_blobs[expected_oid] = payload

        # Topologically resolve blob deltas
        while pending_blob_deltas:
            progress = False
            for delta in list(pending_blob_deltas):
                base_payload: bytes | None = None
                if delta.base_oid in resolved_blobs:
                    base_payload = resolved_blobs[delta.base_oid]
                else:
                    # Attempt to resolve external base blob from target repository
                    base_payload = repo.read_raw_object(delta.base_oid, GitObjectType.BLOB)

                if base_payload is not None:
                    reconstructed = apply_text_delta(
                        base_payload, delta, hash_algo=manifest.hash_algo
                    )
                    resolved_blobs[delta.target_oid] = reconstructed
                    pending_blob_deltas.remove(delta)
                    progress = True
            if not progress:
                unresolved = sorted({d.target_oid for d in pending_blob_deltas})
                raise ValueError(
                    f"Unresolvable blob deltas (missing base objects in bundle and target repo): {unresolved}"
                )

    # Quarantined side-channel objects
    if manifest.metrics.blobs_quarantined > 0:
        if sidechannel_dir is None:
            raise ValueError(
                f"Bundle requires {manifest.metrics.blobs_quarantined} quarantined object(s), "
                f"but --sidechannel directory was not specified."
            )
        q_manifest_file = b_dir / "quarantine" / "quarantine-manifest.txt"
        q_manifest = (
            QuarantineManifest.from_text(
                q_manifest_file.read_text(encoding="utf-8"),
                hash_algo=manifest.hash_algo,
            )
            if q_manifest_file.is_file()
            else None
        )
        sidechannel_objects = load_sidechannel_objects(
            sidechannel_dir,
            manifest=q_manifest,
            hash_algo=manifest.hash_algo,
        )
        for oid, payload in sidechannel_objects.items():
            resolved_blobs[oid] = payload

    for payload in resolved_blobs.values():
        objects_to_inject.append((GitObjectType.BLOB, payload))

    # 3. Object injection (Phase 2)
    for obj_type, payload in objects_to_inject:
        inject_loose_object(repo, obj_type, payload, hash_algo=manifest.hash_algo)

    # 4. Reference updates (Phase 3)
    for ref_entry in manifest.refs:
        update_reference(repo, ref_entry.name, ref_entry.oid)

    return UnpackResult(
        target_ref=manifest.refs[0].name,
        target_oid=manifest.refs[0].oid,
        objects_injected=len(objects_to_inject),
        metrics=manifest.metrics,
    )
