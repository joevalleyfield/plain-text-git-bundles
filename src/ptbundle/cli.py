"""CLI entrypoint for ptbundle."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from ptbundle import __version__
from ptbundle.bundle import convert_from_bundle, convert_to_bundle
from ptbundle.pack import pack_bundle
from ptbundle.policy import WhitelistPolicy
from ptbundle.repo import GitRepo
from ptbundle.unpack import unpack_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptbundle",
        description="Plain-Text Git Bundles serialization format and tooling",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--repo",
        default=".",
        metavar="REPO_PATH",
        help="Path to the Git repository (default: current working directory)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # pack subcommand
    pack_parser = subparsers.add_parser(
        "pack",
        help="Serialize a Git delta range into a plain-text bundle",
    )
    pack_parser.add_argument(
        "rev_range",
        metavar="REV_RANGE",
        help="Revision range to pack (e.g. origin/main..feature)",
    )
    pack_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT_DIR",
        help="Destination directory for the plain-text bundle",
    )
    pack_parser.add_argument(
        "--whitelist-ext",
        default="",
        metavar="EXTENSIONS",
        help="Comma-separated list of allowed binary file extensions (e.g. png,jpg,svg)",
    )
    pack_parser.add_argument(
        "--no-delta",
        action="store_true",
        help="Disable plain-text delta compression for blobs and trees",
    )
    pack_parser.add_argument(
        "--thin",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delta-compress against repository basis objects (default: true; use --no-thin to disable)",
    )

    # unpack subcommand
    unpack_parser = subparsers.add_parser(
        "unpack",
        help="Verify and unpack a plain-text bundle into the target Git repository",
    )
    unpack_parser.add_argument(
        "bundle_dir",
        metavar="BUNDLE_DIR",
        help="Path to the plain-text bundle directory",
    )
    unpack_parser.add_argument(
        "--sidechannel",
        metavar="QUARANTINE_DIR",
        help="Path to an optional quarantine side-channel directory",
    )

    # from-bundle subcommand
    from_bundle_parser = subparsers.add_parser(
        "from-bundle",
        help="Convert a canonical Git .bundle file into a plain-text ptbundle directory",
    )
    from_bundle_parser.add_argument(
        "bundle_file",
        metavar="BUNDLE_FILE",
        help="Path to the canonical Git .bundle binary file",
    )
    from_bundle_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT_DIR",
        help="Destination directory for the plain-text bundle",
    )
    from_bundle_parser.add_argument(
        "--whitelist-ext",
        default="",
        metavar="EXTENSIONS",
        help="Comma-separated list of allowed binary file extensions",
    )
    from_bundle_parser.add_argument(
        "--no-delta",
        action="store_true",
        help="Disable plain-text delta compression for blobs and trees",
    )
    from_bundle_parser.add_argument(
        "--thin",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delta-compress against repository basis objects (default: true; use --no-thin to disable)",
    )

    # to-bundle subcommand
    to_bundle_parser = subparsers.add_parser(
        "to-bundle",
        help="Convert a plain-text ptbundle directory into a canonical Git .bundle binary file",
    )
    to_bundle_parser.add_argument(
        "bundle_dir",
        metavar="BUNDLE_DIR",
        help="Path to the plain-text bundle directory",
    )
    to_bundle_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT_BUNDLE",
        help="Destination path for the canonical Git .bundle file",
    )

    return parser


def cmd_pack(args: argparse.Namespace) -> int:
    """Execute bundle pack workflow."""
    try:
        repo = GitRepo.discover(args.repo)
        policy = WhitelistPolicy.from_extensions(
            args.whitelist_ext.split(",") if args.whitelist_ext else None
        )
        manifest = pack_bundle(
            repo,
            args.rev_range,
            args.output,
            whitelist_policy=policy,
            enable_delta=not args.no_delta,
            thin=args.thin,
        )
        sys.stdout.write(f"Created ptbundle at {args.output}\n")
        sys.stdout.write(f"Target ref: {manifest.refs[0].name} ({manifest.refs[0].oid})\n")
        sys.stdout.write(f"Commits: {manifest.metrics.commits}\n")
        sys.stdout.write(f"Trees: {manifest.metrics.trees}\n")
        if manifest.metrics.trees_delta > 0:
            sys.stdout.write(f"Trees (delta): {manifest.metrics.trees_delta}\n")
        sys.stdout.write(f"Blobs (text): {manifest.metrics.blobs_text}\n")
        if manifest.metrics.blobs_delta > 0:
            sys.stdout.write(f"Blobs (delta): {manifest.metrics.blobs_delta}\n")
        sys.stdout.write(f"Blobs (binary): {manifest.metrics.blobs_binary}\n")
        sys.stdout.write(f"Blobs (quarantined): {manifest.metrics.blobs_quarantined}\n")
        return 0
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as err:
        sys.stderr.write(f"Error packing bundle: {err}\n")
        return 1


def cmd_unpack(args: argparse.Namespace) -> int:
    """Execute bundle unpack workflow."""
    try:
        repo = GitRepo.discover(args.repo)
        res = unpack_bundle(
            repo,
            args.bundle_dir,
            sidechannel_dir=args.sidechannel,
        )
        sys.stdout.write(f"Successfully unpacked bundle into repository at {repo.root}\n")
        sys.stdout.write(f"Updated ref: {res.target_ref} -> {res.target_oid}\n")
        sys.stdout.write(f"Total objects injected: {res.objects_injected}\n")
        return 0
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as err:
        sys.stderr.write(f"Error unpacking bundle: {err}\n")
        return 1


def cmd_from_bundle(args: argparse.Namespace) -> int:
    """Execute conversion from canonical Git .bundle to ptbundle directory."""
    try:
        policy = WhitelistPolicy.from_extensions(
            args.whitelist_ext.split(",") if args.whitelist_ext else None
        )
        # Check if repo path is provided or discoverable
        repo_path: Path | None = None
        try:
            repo_path = GitRepo.discover(args.repo).root
        except Exception:
            repo_path = None

        manifest = convert_from_bundle(
            bundle_path=args.bundle_file,
            output_dir=args.output,
            repo_path=repo_path,
            whitelist_policy=policy,
            enable_delta=not args.no_delta,
            thin=args.thin,
        )
        sys.stdout.write(f"Converted Git bundle {args.bundle_file} to ptbundle at {args.output}\n")
        sys.stdout.write(f"Target ref: {manifest.refs[0].name} ({manifest.refs[0].oid})\n")
        sys.stdout.write(f"Commits: {manifest.metrics.commits}\n")
        sys.stdout.write(f"Trees: {manifest.metrics.trees}\n")
        if manifest.metrics.trees_delta > 0:
            sys.stdout.write(f"Trees (delta): {manifest.metrics.trees_delta}\n")
        sys.stdout.write(f"Blobs (text): {manifest.metrics.blobs_text}\n")
        if manifest.metrics.blobs_delta > 0:
            sys.stdout.write(f"Blobs (delta): {manifest.metrics.blobs_delta}\n")
        sys.stdout.write(f"Blobs (binary): {manifest.metrics.blobs_binary}\n")
        sys.stdout.write(f"Blobs (quarantined): {manifest.metrics.blobs_quarantined}\n")
        return 0
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as err:
        sys.stderr.write(f"Error converting from Git bundle: {err}\n")
        return 1


def cmd_to_bundle(args: argparse.Namespace) -> int:
    """Execute conversion from ptbundle directory to canonical Git .bundle file."""
    try:
        repo_path: Path | None = None
        try:
            repo_path = GitRepo.discover(args.repo).root
        except Exception:
            repo_path = None

        out_path = convert_to_bundle(
            bundle_dir=args.bundle_dir,
            output_bundle=args.output,
            repo_path=repo_path,
        )
        sys.stdout.write(f"Converted ptbundle at {args.bundle_dir} to Git bundle at {out_path}\n")
        return 0
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as err:
        sys.stderr.write(f"Error converting to Git bundle: {err}\n")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "pack":
        return cmd_pack(args)
    if args.command == "unpack":
        return cmd_unpack(args)
    if args.command == "from-bundle":
        return cmd_from_bundle(args)
    assert args.command == "to-bundle"
    return cmd_to_bundle(args)
