"""Git repository discovery, revision delta traversal, and loose object I/O."""

from __future__ import annotations

import io
import os
import subprocess
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from ptbundle.manifest import validate_ref_name
from ptbundle.objects import GitObjectType, compute_oid, format_git_object


@dataclass(frozen=True)
class DeltaObject:
    """Git object discovered in a delta with its repository path and payload."""

    oid: str
    type: GitObjectType
    path: str
    payload: bytes


@dataclass
class DeltaSpec:
    """Specification of a revision delta to pack or transfer."""

    range_spec: str
    target_ref: str
    target_oid: str
    prerequisites: list[str] = field(default_factory=list)
    objects: list[DeltaObject] = field(default_factory=list)


class GitRepo:
    """Interface to a local Git repository."""

    def __init__(self, root: Path, git_dir: Path) -> None:
        self.root = root.resolve()
        self.git_dir = git_dir.resolve()

    @classmethod
    def discover(cls, start_path: Path | str = ".") -> GitRepo:
        """Discover the Git repository root and git directory by walking upward.

        Supports standard '.git' directories and worktree/submodule '.git' files (gitdir: ...).
        Raises ValueError if no repository is found.
        """
        curr = Path(start_path).resolve()
        while True:
            git_path = curr / ".git"
            if git_path.is_dir():
                return cls(root=curr, git_dir=git_path)
            elif git_path.is_file():
                # Worktree or submodule pointer
                content = git_path.read_text(encoding="utf-8").strip()
                if not content.startswith("gitdir:"):
                    raise ValueError(f"Malformed .git pointer file (missing 'gitdir:'): {git_path}")
                target = content[len("gitdir:") :].strip()
                resolved_git_dir = (curr / target).resolve()
                return cls(root=curr, git_dir=resolved_git_dir)

            parent = curr.parent
            if parent == curr:
                break
            curr = parent

        raise ValueError(f"Not a git repository (or any of the parent directories): {start_path}")

    def run_git(
        self,
        args: list[str],
        input: bytes | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute a git command within the repository root."""
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            input=input,
            capture_output=True,
            check=check,
        )

    def read_raw_object(self, oid: str, obj_type: GitObjectType | None = None) -> bytes | None:
        """Read a raw object payload from the repository by OID.

        Returns payload bytes if found, or None if missing or wrong type.
        """
        type_arg = obj_type.value if obj_type is not None else None
        if type_arg is not None:
            proc = self.run_git(["cat-file", type_arg, oid], check=False)
        else:
            proc = self.run_git(["cat-file", "-p", oid], check=False)

        if proc.returncode == 0:
            return proc.stdout
        return None

    def get_object_at_revision(
        self,
        rev: str,
        path: str,
        obj_type: GitObjectType,
    ) -> tuple[str, bytes] | None:
        """Resolve the OID and raw payload for a path at a given revision/commit.

        Returns (oid, payload) if found, or None if not present or wrong type.
        """
        if obj_type == GitObjectType.TREE:
            target = f"{rev}^{{tree}}" if not path else f"{rev}:{path}"
        else:
            if not path:
                return None
            target = f"{rev}:{path}"

        proc = self.run_git(["rev-parse", "--verify", target], check=False)
        if proc.returncode != 0:
            return None
        oid = proc.stdout.decode("utf-8").strip()
        payload = self.read_raw_object(oid, obj_type)
        if payload is None:
            return None
        return oid, payload


def discover_delta(
    repo: GitRepo,
    range_spec: str,
    ref_name: str | None = None,
) -> DeltaSpec:
    """Discover boundary prerequisites and object delta using git rev-list and cat-file."""
    # 1. Resolve target tip and target reference
    if "..." in range_spec:
        tip = range_spec.split("...")[-1].strip()
    elif ".." in range_spec:
        tip = range_spec.split("..")[-1].strip()
    else:
        tip = range_spec.strip()

    tip_oid_proc = repo.run_git(["rev-parse", "--verify", tip])
    target_oid = tip_oid_proc.stdout.decode("utf-8").strip()

    if ref_name:
        target_ref = validate_ref_name(ref_name)
    else:
        ref_proc = repo.run_git(["rev-parse", "--symbolic-full-name", tip], check=False)
        full_name = ref_proc.stdout.decode("utf-8").strip()
        if full_name and full_name.startswith("refs/"):
            target_ref = full_name
        else:
            head_proc = repo.run_git(["symbolic-ref", "HEAD"], check=False)
            head_ref = head_proc.stdout.decode("utf-8").strip()
            if head_ref and head_ref.startswith("refs/"):
                target_ref = head_ref
            else:
                target_ref = "refs/heads/main"

    # 2. Discover boundary commits (prerequisites)
    prerequisites: list[str] = []
    if ".." in range_spec:
        boundary_proc = repo.run_git(["rev-list", "--boundary", range_spec])
        for line in boundary_proc.stdout.decode("utf-8").splitlines():
            line = line.strip()
            if line.startswith("-"):
                prerequisites.append(line[1:].strip())

    # 3. Discover delta objects and their associated tree paths
    obj_proc = repo.run_git(["rev-list", "--objects", range_spec])
    lines = obj_proc.stdout.decode("utf-8", errors="replace").splitlines()

    oid_to_path: dict[str, str] = {}
    oids_to_fetch: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(" ", 1)
        oid = parts[0]
        path = parts[1] if len(parts) > 1 else ""
        if oid not in oid_to_path:
            oid_to_path[oid] = path
            oids_to_fetch.append(oid)

    # 4. Batch fetch object types and raw payloads
    objects: list[DeltaObject] = []
    if oids_to_fetch:
        batch_input = "\n".join(oids_to_fetch).encode("utf-8") + b"\n"
        cat_proc = repo.run_git(["cat-file", "--batch"], input=batch_input)
        stream = io.BytesIO(cat_proc.stdout)

        while True:
            header_line = stream.readline()
            if not header_line:
                break
            header_str = header_line.decode("utf-8", errors="replace").strip()
            parts = header_str.split()
            if len(parts) != 3:
                # Could be "<oid> missing"
                continue
            oid, type_str, size_str = parts
            size = int(size_str)
            payload = stream.read(size)
            stream.read(1)  # Consume trailing delimiter newline

            try:
                obj_type = GitObjectType(type_str)
            except ValueError:
                continue

            objects.append(
                DeltaObject(
                    oid=oid,
                    type=obj_type,
                    path=oid_to_path.get(oid, ""),
                    payload=payload,
                )
            )

    return DeltaSpec(
        range_spec=range_spec,
        target_ref=target_ref,
        target_oid=target_oid,
        prerequisites=prerequisites,
        objects=objects,
    )


def verify_prerequisites(repo: GitRepo, prerequisites: list[str]) -> None:
    """Verify that all prerequisite commits exist in the target repository.

    Raises ValueError if any prerequisite commit is missing.
    """
    for prereq in prerequisites:
        proc = repo.run_git(["cat-file", "-e", f"{prereq}^{{commit}}"], check=False)
        if proc.returncode != 0:
            raise ValueError(f"Missing prerequisite commit in target repository: {prereq}")


def inject_loose_object(
    repo: GitRepo,
    obj_type: GitObjectType,
    payload: bytes,
    hash_algo: str = "sha1",
) -> str:
    """Inject a loose object into the repository object database (.git/objects).

    Atomically writes via a temporary file and os.replace.
    Returns the computed object ID.
    """
    formatted = format_git_object(obj_type, payload)
    oid = compute_oid(obj_type, payload, hash_algo=hash_algo)

    objects_dir = repo.git_dir / "objects"
    fanout_dir = objects_dir / oid[:2]
    dest_file = fanout_dir / oid[2:]

    if dest_file.is_file():
        return oid

    fanout_dir.mkdir(parents=True, exist_ok=True)
    compressed = zlib.compress(formatted)

    tmp_file = objects_dir / f"tmp_obj_{oid}_{os.getpid()}"
    tmp_file.write_bytes(compressed)
    os.replace(tmp_file, dest_file)

    return oid


def update_reference(repo: GitRepo, ref_name: str, oid: str) -> None:
    """Update or create a Git reference in the repository using git update-ref."""
    valid_ref = validate_ref_name(ref_name)
    repo.run_git(["update-ref", valid_ref, oid])
