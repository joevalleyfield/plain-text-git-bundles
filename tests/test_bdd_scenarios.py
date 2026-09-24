"""BDD Acceptance Test Suite using pytest-bdd."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from ptbundle.cli import main

# Bind Gherkin feature files
scenarios("features/delta_transfer.feature")
scenarios("features/quarantine_sidechannel.feature")
scenarios("features/ingress_tamper_defense.feature")
scenarios("features/phase2_interop_deltas.feature")


@pytest.fixture
def bdd_ctx() -> dict[str, Any]:
    return {}


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "BDD Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "bdd@example.com"], cwd=path, check=True)
    return path


# --- Steps for delta_transfer.feature ---


@given('a source repository with a base commit on branch "main"')
@given("a source repository with a base commit")
def step_given_source_repo_base(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_repo")
    (src / "base.txt").write_text("Base content\n")
    subprocess.run(["git", "add", "base.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=src, check=True)
    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = tmp_path / "bundle"


@given('a feature branch "feature" with text commits ahead of "main"')
def step_given_feature_branch_text(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=src, check=True)
    (src / "feature.txt").write_text("Feature text\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Feature text commit"], cwd=src, check=True)


@given("a source repository with a feature branch")
def step_given_source_repo_feature_branch(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_repo")
    (src / "base.txt").write_text("Base content\n")
    subprocess.run(["git", "add", "base.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=src, check=True)
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=src, check=True)
    (src / "feature.txt").write_text("Feature text\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Feature text commit"], cwd=src, check=True)
    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = tmp_path / "bundle"


@given('a target repository cloned from "main"')
@given("a target repository possessing the base commit")
def step_given_target_repo_cloned(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    dst = tmp_path / "dst_repo"
    src = bdd_ctx["src_repo"]
    subprocess.run(
        ["git", "clone", "--branch", "main", "--single-branch", str(src), str(dst)],
        capture_output=True,
        check=True,
    )
    bdd_ctx["dst_repo"] = dst


@when(parsers.parse('I pack the delta "{rev_range}" into a bundle'))
def step_when_pack_delta(rev_range: str, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(src), "pack", rev_range, "-o", str(bundle_dir)])
    assert code == 0


@when("I unpack the bundle into the target repository")
def step_when_unpack_into_target(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(dst), "unpack", str(bundle_dir)])
    assert code == 0


@then('the target repository should have branch "feature" matching the source')
def step_then_target_branch_matches(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    dst = bdd_ctx["dst_repo"]
    src_oid = (
        subprocess.run(
            ["git", "rev-parse", "refs/heads/feature"], cwd=src, capture_output=True, check=True
        )
        .stdout.decode()
        .strip()
    )
    dst_oid = (
        subprocess.run(
            ["git", "rev-parse", "refs/heads/feature"], cwd=dst, capture_output=True, check=True
        )
        .stdout.decode()
        .strip()
    )
    assert dst_oid == src_oid

    # Verify checkout and file content
    subprocess.run(["git", "checkout", "feature"], cwd=dst, capture_output=True, check=True)
    assert (dst / "feature.txt").read_text() == "Feature text\n"


@then("git fsck in the target repository should report no corruption")
def step_then_fsck_clean_target(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    proc = subprocess.run(["git", "fsck"], cwd=dst, capture_output=True)
    assert proc.returncode == 0


@given('a source repository with an initial commit on branch "main"')
def step_given_source_repo_initial(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_full_repo")
    (src / "init.txt").write_text("Initial repo\n")
    subprocess.run(["git", "add", "init.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Initial full repo"], cwd=src, check=True)
    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = tmp_path / "bundle_full"


@given("an empty destination repository")
def step_given_empty_destination_repo(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    dst = _init_git_repo(tmp_path / "dst_full_repo")
    bdd_ctx["dst_repo"] = dst


@when(parsers.parse('I pack the full branch "{branch}" into a bundle'))
def step_when_pack_full_branch(branch: str, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(src), "pack", branch, "-o", str(bundle_dir)])
    assert code == 0


@when("I unpack the bundle into the destination repository")
def step_when_unpack_into_destination(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(dst), "unpack", str(bundle_dir)])
    assert code == 0


@then('the destination repository should have branch "main" matching the source')
def step_then_destination_matches_source(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    dst = bdd_ctx["dst_repo"]
    src_oid = (
        subprocess.run(
            ["git", "rev-parse", "refs/heads/main"], cwd=src, capture_output=True, check=True
        )
        .stdout.decode()
        .strip()
    )
    dst_oid = (
        subprocess.run(
            ["git", "rev-parse", "refs/heads/main"], cwd=dst, capture_output=True, check=True
        )
        .stdout.decode()
        .strip()
    )
    assert dst_oid == src_oid


@then("git fsck in the destination repository should report no corruption")
def step_then_fsck_clean_destination(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    proc = subprocess.run(["git", "fsck"], cwd=dst, capture_output=True)
    assert proc.returncode == 0


# --- Steps for quarantine_sidechannel.feature ---


@given(
    'a feature branch containing text files, a whitelisted "png" image, and a non-whitelisted "bin" file'
)
def step_given_feature_with_mixed_assets(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=src, check=True)
    (src / "code.py").write_text("print('code')\n")
    (src / "asset.png").write_bytes(b"\x89PNG\r\n\x1a\nvalid_png_content")
    (src / "payload.bin").write_bytes(b"\x00\x01\x02binary_bytes")
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Add mixed assets"], cwd=src, check=True)


@when(parsers.parse('I pack the delta with whitelist extension "{ext}"'))
def step_when_pack_with_whitelist(ext: str, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(
        [
            "--repo",
            str(src),
            "pack",
            "main..feature",
            "-o",
            str(bundle_dir),
            "--whitelist-ext",
            ext,
        ]
    )
    assert code == 0


@then("the bundle should contain the whitelisted image in the blobs directory")
def step_then_bundle_contains_whitelisted(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["bundle_dir"]
    png_files = list((bundle_dir / "blobs").rglob("*.png"))
    assert len(png_files) == 1


@then(
    "the non-whitelisted file should be segregated into the quarantine directory with an audit manifest"
)
def step_then_quarantined_segregated(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["bundle_dir"]
    q_dir = bundle_dir / "quarantine"
    assert (q_dir / "quarantine-manifest.txt").is_file()
    q_bin_files = list(q_dir.glob("*.bin"))
    assert len(q_bin_files) == 1


@given("a bundle containing quarantined binary objects")
def step_given_bundle_with_quarantine(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_q_repo")
    (src / "base.txt").write_text("Base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=src, check=True)

    subprocess.run(["git", "checkout", "-b", "feature"], cwd=src, check=True)
    (src / "data.bin").write_bytes(b"\x00\x01\x02quarantine_me")
    subprocess.run(["git", "add", "data.bin"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Commit with binary"], cwd=src, check=True)

    bundle_dir = tmp_path / "q_bundle"
    code = main(["--repo", str(src), "pack", "main..feature", "-o", str(bundle_dir)])
    assert code == 0

    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = bundle_dir


@when("I attempt to unpack the bundle without specifying a sidechannel directory")
def step_when_unpack_no_sidechannel(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(dst), "unpack", str(bundle_dir)])
    bdd_ctx["unpack_exit_code"] = code


@then("the unpack operation should fail with a quarantine error")
def step_then_unpack_fails_quarantine(bdd_ctx: dict[str, Any]) -> None:
    assert bdd_ctx["unpack_exit_code"] != 0


@then("the target repository reference should remain unchanged")
def step_then_target_ref_unchanged(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "refs/heads/feature"], cwd=dst, capture_output=True
    )
    assert proc.returncode != 0


@given("a mounted sidechannel media directory containing the quarantined objects")
def step_given_sidechannel_media(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["bundle_dir"]
    bdd_ctx["sidechannel_dir"] = bundle_dir / "quarantine"


@when("I unpack the bundle with the sidechannel directory specified")
def step_when_unpack_with_sidechannel(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    sidechannel_dir = bdd_ctx["sidechannel_dir"]
    code = main(
        [
            "--repo",
            str(dst),
            "unpack",
            str(bundle_dir),
            "--sidechannel",
            str(sidechannel_dir),
        ]
    )
    bdd_ctx["unpack_exit_code"] = code


@then("the unpack operation should succeed")
def step_then_unpack_succeeds(bdd_ctx: dict[str, Any]) -> None:
    assert bdd_ctx["unpack_exit_code"] == 0


@then("the target repository should checkout all files including the quarantined binary")
def step_then_target_checkout_quarantined(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    subprocess.run(["git", "checkout", "feature"], cwd=dst, capture_output=True, check=True)
    assert (dst / "data.bin").read_bytes() == b"\x00\x01\x02quarantine_me"


# --- Steps for ingress_tamper_defense.feature ---


@given("a valid bundle created from a feature branch")
def step_given_valid_bundle_from_feature(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_tamper")
    (src / "base.txt").write_text("Base text\n")
    subprocess.run(["git", "add", "base.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=src, check=True)

    subprocess.run(["git", "checkout", "-b", "feature"], cwd=src, check=True)
    (src / "code.txt").write_text("Original code\n")
    subprocess.run(["git", "add", "code.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Feature commit"], cwd=src, check=True)

    bundle_dir = tmp_path / "bundle_tamper"
    code = main(["--repo", str(src), "pack", "main..feature", "-o", str(bundle_dir)])
    assert code == 0

    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = bundle_dir


@when("an attacker alters the content of a blob file in the bundle")
def step_when_attacker_alters_blob(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["bundle_dir"]
    blobs = list((bundle_dir / "blobs").rglob("*.txt"))
    assert len(blobs) > 0
    blobs[0].write_bytes(b"TAMPERED MALICIOUS CONTENT\n")


@when("I attempt to unpack the altered bundle into the target repository")
@when("I attempt to unpack the bundle into the target repository")
def step_when_unpack_tampered_bundle(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(dst), "unpack", str(bundle_dir)])
    bdd_ctx["tamper_exit_code"] = code


@then("the unpack operation should fail with a cryptographic mismatch error")
@then("the unpack operation should fail with a missing prerequisite error")
def step_then_unpack_fails_cryptographic(bdd_ctx: dict[str, Any]) -> None:
    assert bdd_ctx["tamper_exit_code"] != 0


@given("a valid bundle requiring a specific base commit")
def step_given_bundle_requiring_prereq(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_prereq")
    (src / "base.txt").write_text("Base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Base commit"], cwd=src, check=True)

    subprocess.run(["git", "checkout", "-b", "feature"], cwd=src, check=True)
    (src / "feat.txt").write_text("Feature\n")
    subprocess.run(["git", "add", "feat.txt"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Feat"], cwd=src, check=True)

    bundle_dir = tmp_path / "bundle_prereq"
    code = main(["--repo", str(src), "pack", "main..feature", "-o", str(bundle_dir)])
    assert code == 0

    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = bundle_dir


@given("an empty target repository lacking the prerequisite commit")
def step_given_empty_target_lacking_prereq(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    dst = _init_git_repo(tmp_path / "dst_empty_target")
    bdd_ctx["dst_repo"] = dst


@then("the target repository should contain no references")
def step_then_target_contains_no_refs(bdd_ctx: dict[str, Any]) -> None:
    dst = bdd_ctx["dst_repo"]
    proc = subprocess.run(["git", "show-ref"], cwd=dst, capture_output=True)
    assert proc.stdout.strip() == b""


# --- Steps for phase2_interop_deltas.feature ---


@given("a source repository with an initial commit containing a multi-file tree")
def step_given_multi_file_source(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_delta_repo")
    for i in range(12):
        (src / f"module_{i:02d}.py").write_text(f"# module {i}\n" + "def worker(): pass\n" * 20)
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Initial tree"], cwd=src, check=True)
    bdd_ctx["src_repo"] = src
    bdd_ctx["bundle_dir"] = tmp_path / "ptbundle_delta"


@given("multiple successive commits iteratively modifying text files")
def step_given_iterative_commits(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    # Commit 2
    (src / "module_00.py").write_text("# module 0 updated v2\n" + "def worker(): pass\n" * 20)
    subprocess.run(["git", "add", "module_00.py"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Update module 0 v2"], cwd=src, check=True)

    # Commit 3
    (src / "module_00.py").write_text("# module 0 updated v3\n" + "def worker(): pass\n" * 20)
    subprocess.run(["git", "add", "module_00.py"], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Update module 0 v3"], cwd=src, check=True)


@when("I pack the revision delta with plain-text delta compression enabled")
def step_when_pack_with_deltas(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    code = main(["--repo", str(src), "pack", "HEAD~2..HEAD", "-o", str(bundle_dir)])
    assert code == 0


@then("the generated bundle should contain delta tree and blob files")
def step_then_verify_delta_files(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["bundle_dir"]
    tree_deltas = list((bundle_dir / "trees").rglob("*.delta.txt"))
    blob_deltas = list((bundle_dir / "blobs").rglob("*.delta.txt"))
    assert len(tree_deltas) > 0
    assert len(blob_deltas) > 0


@then(
    "unpacking the bundle into a target repository reproduces the exact Git commits and tree state"
)
def step_then_unpack_and_verify_exact(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    bundle_dir = bdd_ctx["bundle_dir"]
    dst = tmp_path / "dst_delta_repo"
    subprocess.run(
        ["git", "clone", "--branch", "main", "--single-branch", str(src), str(dst)],
        capture_output=True,
        check=True,
    )
    # Reset dst back to base commit HEAD~2
    subprocess.run(["git", "reset", "--hard", "HEAD~2"], cwd=dst, check=True, capture_output=True)

    code = main(["--repo", str(dst), "unpack", str(bundle_dir)])
    assert code == 0

    # Reset working tree to updated main and check exact byte match
    subprocess.run(["git", "reset", "--hard", "main"], cwd=dst, check=True, capture_output=True)
    assert (dst / "module_00.py").read_text() == (src / "module_00.py").read_text()
    src_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True).stdout
    dst_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dst, capture_output=True).stdout
    assert src_head == dst_head


@given("a canonical Git bundle created from the feature branch")
def step_given_canonical_git_bundle(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    git_bundle = tmp_path / "canonical.bundle"
    subprocess.run(
        ["git", "bundle", "create", str(git_bundle), "feature"],
        cwd=src,
        check=True,
        capture_output=True,
    )
    bdd_ctx["git_bundle"] = git_bundle


@when("I convert the canonical Git bundle into a ptbundle directory")
def step_when_convert_from_git_bundle(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    git_bundle = bdd_ctx["git_bundle"]
    pt_dir = tmp_path / "converted_ptbundle"
    code = main(["--repo", str(src), "from-bundle", str(git_bundle), "-o", str(pt_dir)])
    assert code == 0
    bdd_ctx["converted_ptbundle"] = pt_dir


@when("I convert the ptbundle directory back into a canonical Git bundle")
def step_when_convert_to_git_bundle(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    pt_dir = bdd_ctx["converted_ptbundle"]
    synth_bundle = tmp_path / "synthesized.bundle"
    code = main(["--repo", str(src), "to-bundle", str(pt_dir), "-o", str(synth_bundle)])
    assert code == 0
    bdd_ctx["synth_bundle"] = synth_bundle


@then("the synthesized Git bundle passes canonical git bundle verification")
def step_then_verify_synthesized_bundle(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    synth_bundle = bdd_ctx["synth_bundle"]
    proc = subprocess.run(
        ["git", "bundle", "verify", str(synth_bundle)],
        cwd=src,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "is okay" in proc.stdout or "is okay" in proc.stderr


@then("cloning from the synthesized Git bundle matches the source repository")
def step_then_clone_from_synthesized_bundle(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_repo"]
    synth_bundle = bdd_ctx["synth_bundle"]
    clone_dir = tmp_path / "clone_from_synth"
    subprocess.run(
        ["git", "clone", "-b", "feature", str(synth_bundle), str(clone_dir)],
        capture_output=True,
        check=True,
    )
    src_feat = subprocess.run(
        ["git", "rev-parse", "refs/heads/feature"], cwd=src, capture_output=True
    ).stdout.strip()
    clone_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=clone_dir, capture_output=True
    ).stdout.strip()
    assert src_feat == clone_head
    assert (clone_dir / "feature.txt").read_text() == "Feature text\n"


@given('a source repository with a wide multi-file tree on "main"')
def step_given_wide_tree_main(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = _init_git_repo(tmp_path / "src_wide_repo")
    sub = src / "pkg"
    sub.mkdir()
    for i in range(20):
        (src / f"root_mod_{i:02d}.py").write_text(f"# Root module {i}\n" + "def fn(): pass\n" * 50)
        (sub / f"sub_mod_{i:02d}.py").write_text(
            f"# Sub module {i}\n" + "def sub_fn(): pass\n" * 50
        )
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Initial wide tree"], cwd=src, check=True)
    bdd_ctx["src_wide_repo"] = src


@given("a single-commit feature branch modifying text files and directory trees")
def step_given_single_commit_feature(bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_wide_repo"]
    subprocess.run(["git", "checkout", "-b", "feature_single"], cwd=src, check=True)
    (src / "root_mod_00.py").write_text("# Root module 00 MODIFIED\n" + "def fn(): pass\n" * 50)
    (src / "pkg" / "sub_mod_00.py").write_text(
        "# Sub module 00 MODIFIED\n" + "def sub_fn(): pass\n" * 50
    )
    (src / "pkg" / "brand_new.py").write_text("# Brand new file\n")
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(["git", "commit", "-m", "Single commit feature"], cwd=src, check=True)


@when("I pack the revision delta as a thin bundle")
def step_when_pack_thin_bundle(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_wide_repo"]
    bundle_dir = tmp_path / "thin_bundle_bdd"
    code = main(
        ["--repo", str(src), "pack", "main..feature_single", "-o", str(bundle_dir), "--thin"]
    )
    assert code == 0
    bdd_ctx["thin_bundle_bdd"] = bundle_dir


@then('the generated bundle contains thin deltas referencing basis objects from "main"')
def step_then_verify_thin_deltas(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["thin_bundle_bdd"]
    deltas = list(bundle_dir.rglob("*.delta.txt"))
    assert len(deltas) >= 2


@then('the basis objects from "main" are not bundled in the package')
def step_then_verify_bases_not_bundled(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["thin_bundle_bdd"]
    deltas = list(bundle_dir.rglob("*.delta.txt"))
    for d in deltas:
        for line in d.read_text().splitlines():
            if line.startswith("base: "):
                base_oid = line.split()[1]
                assert not (bundle_dir / "blobs" / base_oid[:2] / f"{base_oid[2:]}.txt").exists()
                assert not (bundle_dir / "trees" / base_oid[:2] / f"{base_oid[2:]}.txt").exists()


@then('unpacking the thin bundle into a clone of "main" reproduces the exact feature state')
def step_then_unpack_thin_bundle_clone(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_wide_repo"]
    bundle_dir = bdd_ctx["thin_bundle_bdd"]
    dst = tmp_path / "dst_clone_main"
    subprocess.run(
        ["git", "clone", "--branch", "main", "--single-branch", str(src), str(dst)],
        check=True,
        capture_output=True,
    )
    code = main(["--repo", str(dst), "unpack", str(bundle_dir)])
    assert code == 0
    subprocess.run(
        ["git", "reset", "--hard", "refs/heads/feature_single"],
        cwd=dst,
        check=True,
        capture_output=True,
    )
    assert (dst / "root_mod_00.py").read_text() == (src / "root_mod_00.py").read_text()
    assert (dst / "pkg" / "sub_mod_00.py").read_text() == (
        src / "pkg" / "sub_mod_00.py"
    ).read_text()
    assert (dst / "pkg" / "brand_new.py").read_text() == "# Brand new file\n"


@when("I pack the revision delta with no-thin specified")
def step_when_pack_nothin_bundle(tmp_path: Path, bdd_ctx: dict[str, Any]) -> None:
    src = bdd_ctx["src_wide_repo"]
    bundle_dir = tmp_path / "thick_bundle_bdd"
    code = main(
        ["--repo", str(src), "pack", "main..feature_single", "-o", str(bundle_dir), "--no-thin"]
    )
    assert code == 0
    bdd_ctx["thick_bundle_bdd"] = bundle_dir


@then("the generated bundle contains zero delta files")
def step_then_verify_zero_deltas(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["thick_bundle_bdd"]
    assert len(list(bundle_dir.rglob("*.delta.txt"))) == 0


@then("all objects are stored in full for standalone self-containment")
def step_then_verify_all_full(bdd_ctx: dict[str, Any]) -> None:
    bundle_dir = bdd_ctx["thick_bundle_bdd"]
    assert (bundle_dir / "manifest.txt").is_file()
    assert len(list((bundle_dir / "blobs").rglob("*.txt"))) >= 3
