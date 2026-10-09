"""Git bundle interoperability bridge for Plain-Text Git Bundles (ptbundle).

Implements bidirectional conversion between standard Git binary .bundle files
(# v2 / # v3 git bundle) and human-auditable ptbundle plain-text directory trees
using isolated bare Git repository plumbing.
"""

from __future__ import annotations

import dataclasses
import subprocess
import tempfile
import zipfile
from pathlib import Path

from ptbundle.manifest import (
    Manifest,
    ManifestPrerequisite,
    ManifestRef,
    validate_oid,
    validate_ref_name,
)
from ptbundle.pack import pack_bundle
from ptbundle.policy import WhitelistPolicy
from ptbundle.repo import GitRepo
from ptbundle.unpack import unpack_bundle


@dataclasses.dataclass(frozen=True)
class GitBundleHeader:
    """Header metadata parsed from a canonical Git bundle file."""

    version: int
    prerequisites: list[ManifestPrerequisite]
    refs: list[ManifestRef]


def read_bundle_header(bundle_path: Path | str) -> GitBundleHeader:
    """Read and parse the ASCII header of a canonical Git bundle file.

    Supports both '# v2 git bundle' and '# v3 git bundle' formats.
    Raises ValueError if the header is malformed.
    """
    path = Path(bundle_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Git bundle file not found: {path}")

    # Read binary bytes until the blank line separating header from PACK
    raw_data = path.read_bytes()
    # The header is ASCII/UTF-8 text terminated by an empty line (b"\n\n" or b"\r\n\r\n")
    double_nl = raw_data.find(b"\n\n")
    if double_nl == -1:
        double_nl = raw_data.find(b"\r\n\r\n")
        if double_nl == -1:
            raise ValueError(f"Malformed Git bundle {path}: missing blank line separator")
        header_bytes = raw_data[:double_nl]
    else:
        header_bytes = raw_data[:double_nl]

    try:
        header_text = header_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Malformed Git bundle header: not valid UTF-8 text") from None

    lines = header_text.splitlines()
    if not lines:
        raise ValueError("Empty Git bundle header")

    first_line = lines[0].strip()
    if first_line == "# v2 git bundle":
        version = 2
    elif first_line == "# v3 git bundle":
        version = 3
    else:
        raise ValueError(
            f"Unsupported or invalid Git bundle header: {first_line!r} (expected '# v2 git bundle' or '# v3 git bundle')"
        )

    prerequisites: list[ManifestPrerequisite] = []
    refs: list[ManifestRef] = []

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("@"):
            # Empty line or v3 capability line (e.g. @object-format=sha1)
            continue

        if stripped.startswith("-"):
            # Prerequisite line: -<oid> [comment]
            body = stripped[1:].strip()
            if not body:
                raise ValueError(f"Malformed prerequisite line in bundle header: {line!r}")
            oid, _, comment = body.partition(" ")
            clean_oid = validate_oid(oid.strip(), "sha1")
            prerequisites.append(ManifestPrerequisite(oid=clean_oid, comment=comment.strip()))
        else:
            # Reference head line: <oid> <ref_name>
            parts = stripped.split(" ", 1)
            if len(parts) != 2:
                raise ValueError(f"Malformed reference line in bundle header: {line!r}")
            clean_oid = validate_oid(parts[0].strip(), "sha1")
            ref_raw = parts[1].strip()
            normalized = ref_raw if ref_raw.startswith("refs/") else f"refs/heads/{ref_raw}"
            clean_ref = validate_ref_name(normalized)
            refs.append(ManifestRef(name=clean_ref, oid=clean_oid))

    if not refs:
        raise ValueError("Git bundle header declares no reference heads")

    return GitBundleHeader(version=version, prerequisites=prerequisites, refs=refs)


def convert_from_bundle(
    bundle_path: Path | str,
    output_dir: Path | str,
    repo_path: Path | str | None = None,
    whitelist_policy: WhitelistPolicy | None = None,
    enable_delta: bool = True,
    thin: bool = True,
) -> Manifest:
    """Convert a canonical Git .bundle file into a plain-text ptbundle directory."""
    b_path = Path(bundle_path).resolve()
    header = read_bundle_header(b_path)

    with tempfile.TemporaryDirectory(prefix="ptbundle-from-") as tmpdir:
        tmp_path = Path(tmpdir)

        # Initialize scratch bare repo
        if repo_path:
            base_repo = GitRepo.discover(repo_path)
            subprocess.run(
                ["git", "clone", "--bare", "--shared", str(base_repo.root), str(tmp_path)],
                check=True,
                capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "init", "--bare", str(tmp_path)],
                check=True,
                capture_output=True,
            )

        scratch_repo = GitRepo(root=tmp_path, git_dir=tmp_path)

        # Fetch bundle into scratch repo
        fetch_specs = [
            "HEAD:refs/heads/HEAD" if r.name == "refs/heads/HEAD" else f"{r.name}:{r.name}"
            for r in header.refs
        ]
        scratch_repo.run_git(["fetch", str(b_path), *fetch_specs])

        # Formulate rev_range for pack_bundle
        target_ref = header.refs[0].name

        if header.prerequisites:
            range_spec = f"{header.prerequisites[0].oid}..{target_ref}"
        else:
            range_spec = target_ref

        manifest = pack_bundle(
            scratch_repo,
            range_spec,
            output_dir=output_dir,
            whitelist_policy=whitelist_policy,
            ref_name=target_ref,
            enable_delta=enable_delta,
            thin=thin,
        )
        return manifest


def convert_to_bundle(
    bundle_dir: Path | str,
    output_bundle: Path | str,
    repo_path: Path | str | None = None,
) -> Path:
    """Convert a plain-text ptbundle directory or .zip archive into a canonical Git .bundle binary file."""
    b_path = Path(bundle_dir).resolve()
    manifest: Manifest
    if str(bundle_dir).endswith(".zip") or (b_path.is_file() and zipfile.is_zipfile(b_path)):
        if not b_path.is_file():
            raise FileNotFoundError(f"Missing bundle archive {b_path}")
        try:
            with zipfile.ZipFile(b_path, "r") as zf:
                if "manifest.txt" not in zf.namelist():
                    raise FileNotFoundError(f"Missing manifest.txt in {b_path}")
                manifest = Manifest.from_text(zf.read("manifest.txt").decode("utf-8"))
        except zipfile.BadZipFile as err:
            raise ValueError(f"Corrupt or invalid zip archive {b_path}: {err}") from err
    else:
        manifest_file = b_path / "manifest.txt"
        if not manifest_file.is_file():
            raise FileNotFoundError(f"Missing manifest.txt in {b_path}")
        manifest = Manifest.from_text(manifest_file.read_text(encoding="utf-8"))

    out_bundle = Path(output_bundle).resolve()
    out_bundle.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ptbundle-to-") as tmpdir:
        tmp_path = Path(tmpdir)

        if repo_path:
            base_repo = GitRepo.discover(repo_path)
            subprocess.run(
                ["git", "clone", "--bare", "--shared", str(base_repo.root), str(tmp_path)],
                check=True,
                capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "init", "--bare", str(tmp_path)],
                check=True,
                capture_output=True,
            )

        scratch_repo = GitRepo(root=tmp_path, git_dir=tmp_path)

        # Unpack the ptbundle into the scratch repo
        unpack_bundle(scratch_repo, b_path)

        # Create git bundle
        bundle_args = ["bundle", "create", str(out_bundle)]
        for r in manifest.refs:
            bundle_args.append(r.name)
        for p in manifest.prerequisites:
            bundle_args.append(f"^{p.oid}")

        scratch_repo.run_git(bundle_args)

    return out_bundle
