"""CLI entrypoint for ptbundle."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ptbundle import __version__


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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "pack":
        sys.stdout.write(f"Packing {args.rev_range} to {args.output}\n")
        return 0

    assert args.command == "unpack"
    sys.stdout.write(f"Unpacking {args.bundle_dir}\n")
    return 0
