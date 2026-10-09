# Plain-Text Git Bundles (`ptbundle`)

A transparent, auditable, and security-scanner-friendly serialization format for Git bundles—engineered specifically for secure domain transfer, cross-domain solutions (CDS), and air-gapped ingress environments.

---

## 1. Problem Statement

Standard `git bundle` files are opaque binaries. Underneath a thin ASCII header, they append a raw Git packfile (`PACK`) containing zlib-compressed streams and binary delta-compression chains.

In high-security environments—such as air-gapped networks, dioded transfers, or cross-domain ingress guards:
- **Ingress is heavily scrutinized**: Automated DLP, anti-virus, static analysis (SAST), and human reviewers inspect all inbound data.
- **Egress is prohibited**: Inbound bundles cannot query remote servers to resolve dependencies.
- **Opaque binaries are high-risk**: Scanners cannot reliably inspect compressed Git packfiles without running Git binaries inside the ingress boundary, exposing the boundary to potential parser vulnerabilities.
- **Strict format whitelisting**: Security gateways frequently permit plain text (`.txt` / UTF-8) while restricting or quarantining executable scripts, arbitrary binary files, and deep folder structures.

**Plain-Text Git Bundles (`ptbundle`)** solve this by decomposing Git deltas into a flat, human- and scanner-auditable directory of plain-text objects, relying on Git's own cryptographic indices to preserve 100% bit-exact repository integrity.

---

## 2. Core Concepts

### A. Git Is Already Near-Plain-Text
Peeling back packfile compression reveals that Git's fundamental data structures are almost entirely plain text:
- **Commits**: Structured UTF-8 text (tree pointer, parent pointers, author/committer timestamps, commit message).
- **Tags**: Structured UTF-8 text (object pointer, tagger, GPG signature, tag message).
- **Trees**: Directory indices mapping mode, type, and hash to file paths.
- **Blobs**: Source code payloads that are already text files.

### B. Letting Git's Indices Do the Work
Instead of inventing a bespoke archive hierarchy, `ptbundle` stores objects partitioned by type and hash prefix. Git's internal indices naturally route references:
1. The bundle manifest points to target **commit** objects.
2. The commit points to a root **tree** object.
3. The tree points to subtrees and **blobs** with their original file modes and paths.

Every object is verifiable: hashing the canonical Git payload (`<type> <size>\0<payload>`) yields the exact Git Object ID (OID).

---

## 3. Bundle Structure

A plain-text bundle is an uncompressed directory or native `.zip` archive structured as follows:

```text
my-feature-delta/
├── manifest.txt                 # Transfer metadata, prerequisites, and ref heads
├── commits/
│   └── 4a/
│       └── 5b6c7d8e9f...txt     # Plain-text commit objects
├── trees/
│   └── d8/
│       └── 329fc1cc93...txt     # Human-readable ls-tree indices
├── blobs/
│   ├── e6/
│   │   └── 9de29bb2d1...txt     # UTF-8 text file payloads
│   └── 8f/
│       └── 3d82a10b42.png       # Whitelisted binary payloads (retaining native ext)
└── tags/                        # Annotated tag objects (if any)
    └── 1f/
        └── 8a2b3c4d5e...txt
```

### Manifest Format (`manifest.txt`)
Directly maps prerequisites (base commits required in the target repository) and the target refs being advanced:
```text
# ptbundle v1
prerequisite 4a5b6c7d8e9f0123456789abcdef0123456789ab [main]
ref refs/heads/feature-xyz 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b

# Summary Metrics
commits: 3
trees_full: 2
trees_delta: 5
blobs_text: 12
blobs_delta: 20
blobs_binary: 1
blobs_quarantined: 0
```

### Commit Representation (`commits/xx/xxxx.txt`)
Exact commit payload (no null bytes):
```text
tree d8329fc1cc938780ffdd9f94e0d364e0ea74f579
parent 4a5b6c7d8e9f0123456789abcdef0123456789ab
author Alice Smith <alice@example.com> 1727045000 -0400
committer Alice Smith <alice@example.com> 1727045000 -0400

Fix edge case in packet parsing
```

### Tree Representation (`trees/xx/xxxx.txt` or `.delta.txt`)
- **Full Trees (`trees/xx/<sha>.txt`)**: Formatted using Git's standard tab-separated `ls-tree` notation (clean text, no binary SHA bytes):
  ```text
  100644 blob e69de29bb2d1d6434b8b29ae775ad8c2e48c5391	README.md
  100755 blob 8f3d82a10b42c9434b8b29ae775ad8c2e48c5391	build.sh
  040000 tree 710f09b2d1d6434b8b29ae775ad8c2e48c539100	src
  ```
- **Delta Trees (`trees/xx/<sha>.delta.txt`)**: Unified diff against a predecessor tree (either earlier in the bundle or an external basis tree reachable from a prerequisite commit in thin bundles), showing directory-level additions, deletions, and entry modifications:
  ```text
  # ptbundle delta v1
  type: tree
  path: src/
  base: d8329fc1cc938780ffdd9f94e0d364e0ea74f579
  target: 9a4e21b0cc938780ffdd9f94e0d364e0ea74f123

  @@ -4,3 +4,3 @@
   100644 blob e69de29bb2d1d6434b8b29ae775ad8c2e48c5391	__init__.py
  -100644 blob a1b2c3d4e5f678901234567890abcdef12345678	cli.py
  +100644 blob 4f8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a	cli.py
  ```

### Blob Representation (`blobs/xx/xxxx.<ext>`)
- **Full Text Files**: Saved as `<sha>.txt`. Content is the exact UTF-8 file payload.
- **Delta Text Files (`blobs/xx/<sha>.delta.txt`)**: Saved as a human- and scanner-readable unified diff against a predecessor blob (either earlier in the bundle or an external basis blob reachable from a prerequisite commit in thin bundles), drastically reducing transfer size for iterative edits:
  ```text
  # ptbundle delta v1
  type: blob
  path: src/ptbundle/cli.py
  base: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
  target: 4f8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a

  @@ -15,3 +15,5 @@
   unchanged context line
  +new line 1
  +new line 2
  ```
- **Whitelisted Binaries**: Saved with their native extension (e.g. `<sha>.png`). The payload is preserved uncompressed as-is so binary sanitizers and virus scanners can inspect the raw bytes.

---

## 4. Binary Handling & Quarantine Strategy

In secure ingress boundaries, binary assets must be treated with care:

```
                      [ git rev-list delta ]
                                │
                 Is blob UTF-8 plain text?
                    ├── YES ──► Emit .txt (or .delta.txt if smaller)
                    └── NO  ──► Check Whitelist
                                  ├── ON WHITELIST  ──► blobs/xx/<sha>.<ext>
                                  └── NOT ALLOWED   ──► quarantine/
                                                           ├── <sha>.<ext>
                                                           └── quarantine-manifest.txt
```

1. **Fast-Path Text**: UTF-8 code and configuration travel directly through text-only ingress filters as full text or readable unified diffs.
2. **Whitelisted Binaries**: Allowed formats (e.g. `.png`, `.jpg`, `.pdf`, `.json`) travel as raw files with their natural extensions for inspection by dedicated file validators.
3. **Quarantine (Side-Channel)**: Disallowed or high-risk binaries are diverted to a separate `quarantine/` package with an audit manifest. These can be burned to optical media (CD-R) or sent through manual inspection workflows before being merged at the destination.

---

## 5. Tooling Workflow

### Export / Packing (Source / Egress Side)
```bash
# Export as a plain-text directory
ptbundle pack origin/main..feature-branch \
    --output ./transfers/feature-xyz-bundle/ \
    --whitelist-ext png,jpg,svg

# Or export directly as a single .zip archive
ptbundle pack origin/main..feature-branch \
    --output ./transfers/feature-xyz-bundle.zip \
    --whitelist-ext png,jpg,svg
```
1. Identifies the delta object set via `git rev-list --objects`.
2. Emits `manifest.txt` with base prerequisites and tip references.
3. Compresses iterative text blobs and trees into `.delta.txt` when diffs are smaller than full text:
   - **`--thin` (default)**: Delta-compresses against basis objects in the repository reachable from prerequisite commits (`base..head`), omitting the basis objects from the bundle to minimize transfer size.
   - **`--no-thin`**: Disables external basis deltas, ensuring all objects lacking an internal basis within the bundle are stored in full (`.txt`) for complete standalone self-containment.
   - **`--no-delta`**: Disables delta compression entirely.
4. Partitions commits, trees, and blobs into `commits/`, `trees/`, and `blobs/` (written to directory or directly into `.zip`).
5. Routes non-whitelisted binaries to `quarantine/`.

### Import / Unpacking (Target / Ingress Side)
```bash
# Unpack from directory
ptbundle unpack ./transfers/feature-xyz-bundle/ \
    [--sidechannel ./cdrom/quarantine/]

# Or unpack directly from a .zip archive
ptbundle unpack ./transfers/feature-xyz-bundle.zip \
    [--sidechannel ./cdrom/quarantine/]
```
1. **Prerequisite Check**: Validates that the target repository contains all required base commits.
2. **Cryptographic Verification**: Reconstitutes Git objects from plain-text files and verifies that SHA calculations match the file names.
3. **Delta Patching**: Reconstitutes `.delta.txt` trees and blobs deterministically. Base objects are resolved from the bundle or looked up directly in the target repository's object database for thin bundles. Verifies bit-exact OIDs before injection.
4. **Object Injection**: Writes verified loose objects directly into the target `.git/objects` store.
5. **Ref Update**: Atomically updates or creates the specified branch reference.

### Native Git Bundle Interoperability

Convert between canonical Git `.bundle` binary files and plain-text `ptbundle` directories or `.zip` archives without checking out branches:

```bash
# Convert a canonical Git bundle into an auditable plain-text bundle directory or .zip archive
ptbundle from-bundle ./feature.bundle --output ./transfers/feature-xyz-bundle.zip

# Synthesize a canonical Git bundle from an inspected plain-text bundle directory or .zip archive
ptbundle to-bundle ./transfers/feature-xyz-bundle.zip --output ./feature.bundle
```

---

## 6. Implementation Plan & Roadmap

- **Phase 1: Python 3 Reference Implementation**
  - Zero external dependencies (Python standard library only: `hashlib`, `pathlib`, `argparse`).
  - Bit-exact SHA-1 and SHA-256 tree/commit/blob verification against canonical Git.
  - Support for delta packs (`base..head`), text blobs, and whitelisted extensions.
  - Quarantine generation and side-channel reconciliation.
- **Phase 2: Tooling Interop & Plain-Text Delta Compression**
  - **Git Bundle Bridge**: Bidirectional conversion between `.bundle` binaries and `ptbundle` directories (`from-bundle` and `to-bundle`).
  - **CVS/RCS-Style Delta Engine**: Plain-text unified diffs for iterative text blobs and trees with byte-exact Git OID validation and EOF handling.
  - **Size & Performance Optimization**: Drastically smaller bundle footprints for deep histories while preserving 100% human and scanner readability.
- **Phase 3: Standalone Native Binary (Rust/Go)**
  - Single statically linked binary for environments where Python interpreters are restricted.

