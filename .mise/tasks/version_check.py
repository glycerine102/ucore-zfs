#!/usr/bin/env python3
"""
check_ublue_versions.py

Compares the latest akmods-zfs kernel version against kinoite-main images
on ghcr.io/ublue-os to find a matching kernel build.

Repos checked:
  - ghcr.io/ublue-os/akmods-zfs      (tags like coreos-stable-43-6.19.14-101.fc43)
  - ghcr.io/ublue-os/kinoite-main    (tags like 43-20260506.1, label ostree.linux)

Usage:
  python3 check_ublue_versions.py [--fedora-version 43] [--channel stable|testing]
                                   [--max-kernel 6.19] [--inspect-count 20]
                                   [--json] [--debug]

Requirements:
  - crane  (https://github.com/google/go-containerregistry)
  - Python 3.8+, no third-party packages needed
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AKMODS_REPO      = "ghcr.io/ublue-os/akmods-zfs"
KINOITE_REPO     = "ghcr.io/ublue-os/kinoite-main"
KINOITE_PLATFORM = "linux/amd64"

# How many of the most-recent kinoite tags to inspect for ostree.linux labels.
# Increase if your kernel is older than the last N builds.
KINOITE_INSPECT_COUNT = 20


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AkmodsTag:
    """Parsed akmods-zfs tag."""
    tag: str
    fedora_version: str   # e.g. "43"
    kernel_version: str   # e.g. "6.19.14"
    kernel_release: str   # e.g. "101"
    full_kernel: str      # e.g. "6.19.14-101.fc43"

    def kernel_tuple(self):
        """Return (major, minor, patch, release) ints for sorting."""
        m = re.match(r"(\d+)\.(\d+)\.(\d+)-(\d+)", self.full_kernel)
        if m:
            return tuple(int(x) for x in m.groups())
        return (0, 0, 0, 0)


@dataclass
class KinoiteTag:
    """Parsed kinoite-main tag with optional ostree.linux label."""
    tag: str
    fedora_version: str      # e.g. "43"
    build_date: str          # e.g. "20260506"
    build_num: str           # e.g. "1"
    ostree_linux: str = ""   # e.g. "6.19.14-200.fc43.x86_64"

    def kernel_version(self) -> str:
        """Extract the x.y.z part from ostree.linux (e.g. '6.19.14')."""
        m = re.match(r"(\d+\.\d+\.\d+)", self.ostree_linux)
        return m.group(1) if m else ""

    def build_tuple(self):
        """Return (date, build_num) ints for sorting newest-first."""
        try:
            return (int(self.build_date), int(self.build_num))
        except ValueError:
            return (0, 0)


# ---------------------------------------------------------------------------
# crane helpers
# ---------------------------------------------------------------------------

def _run(cmd: list) -> str:
    """Run a subprocess and return stdout. Raises RuntimeError on non-zero exit."""
    import os
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def crane_ls(repo: str, platform: Optional[str] = None) -> list:
    """Return all tags for a repo using `crane ls -O`."""
    cmd = ["crane", "ls", "-O", repo]
    if platform:
        cmd += ["--platform", platform]
    output = _run(cmd)
    return [line for line in output.splitlines() if line.strip()]


def crane_config(repo: str, tag: str, platform: Optional[str] = None) -> dict:
    """Fetch the image config JSON for a specific tag."""
    cmd = ["crane", "config", f"{repo}:{tag}"]
    if platform:
        cmd += ["--platform", platform]
    return json.loads(_run(cmd))


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_akmods_tag(tag: str, fedora_version: str, channel: str = "stable") -> Optional[AkmodsTag]:
    """
    Parse a tag like:  coreos-stable-43-6.19.14-101.fc43
    Pattern:           coreos-{channel}-{FV}-{kernel_ver}-{release}.fc{FV}
    """
    if "sha256" in tag:
        return None
    prefix = f"coreos-{channel}-{fedora_version}-"
    if not tag.startswith(prefix):
        return None
    rest = tag[len(prefix):]  # "6.19.14-101.fc43"
    m = re.fullmatch(r"(\d+\.\d+\.\d+)-(\d+)\.fc(\d+)", rest)
    if not m:
        return None
    kernel_ver, release, fc = m.groups()
    if fc != fedora_version:
        return None
    return AkmodsTag(
        tag=tag,
        fedora_version=fedora_version,
        kernel_version=kernel_ver,
        kernel_release=release,
        full_kernel=f"{kernel_ver}-{release}.fc{fc}",
    )


def parse_kinoite_tag(tag: str, fedora_version: str) -> Optional[KinoiteTag]:
    """
    Parse a tag like:  43-20260506.1
    Pattern:           {FV}-{YYYYMMDD}.{build}
    """
    if "sha256" in tag:
        return None
    m = re.fullmatch(rf"({re.escape(fedora_version)})-(\d{{8}})\.(\d+)", tag)
    if not m:
        return None
    fv, date, num = m.groups()
    return KinoiteTag(tag=tag, fedora_version=fv, build_date=date, build_num=num)


def extract_ostree_linux(config: dict) -> str:
    """Pull the ostree.linux label out of an image config."""
    labels: dict = (
        config.get("config", {}).get("Labels", {})
        or config.get("Labels", {})
        or {}
    )
    return labels.get("ostree.linux", "")


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def parse_kernel_prefix(value: str) -> tuple:
    """
    Validate and parse a MAJOR.MINOR kernel prefix string (e.g. "6.19").
    Returns a tuple of ints, e.g. (6, 19).
    Raises argparse.ArgumentTypeError on bad input.
    """
    m = re.fullmatch(r"(\d+)\.(\d+)", value.strip())
    if not m:
        raise argparse.ArgumentTypeError(
            f"Invalid kernel prefix {value!r} — expected MAJOR.MINOR (e.g. '6.19')"
        )
    return tuple(int(x) for x in m.groups())


def within_kernel_prefix(kernel_version: str, prefix: Optional[tuple]) -> bool:
    """
    True if kernel_version (e.g. '6.19.14') matches the given MAJOR.MINOR
    prefix tuple, or if no prefix is set (always True).
    """
    if prefix is None:
        return True
    m = re.match(r"(\d+)\.(\d+)", kernel_version)
    if not m:
        return False
    return tuple(int(x) for x in m.groups()) == prefix


def kernel_versions_match(akmods_kv: str, ostree_kv: str) -> bool:
    """
    True when both share the same x.y.z kernel version.
    e.g. "6.19.14" matches "6.19.14-200.fc43.x86_64"
    """
    m = re.match(r"(\d+\.\d+\.\d+)", ostree_kv)
    if not m:
        return False
    return m.group(1) == akmods_kv


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def find_latest_akmods(
    fedora_version: str,
    channel: str,
    max_kernel: Optional[tuple],
    debug: bool,
) -> AkmodsTag:
    print(f"[1/4] Listing tags for {AKMODS_REPO} …")
    all_tags = crane_ls(AKMODS_REPO)

    if debug:
        print(f"      Total tags fetched: {len(all_tags)}")

    parsed = [
        t for raw in all_tags
        if (t := parse_akmods_tag(raw, fedora_version, channel)) is not None
    ]

    if max_kernel is not None:
        prefix_str = ".".join(str(x) for x in max_kernel)
        before = len(parsed)
        parsed = [t for t in parsed if within_kernel_prefix(t.kernel_version, max_kernel)]
        print(f"      Filtered to kernel {prefix_str}.x: {len(parsed)} of {before} tag(s) match")

    if not parsed:
        hint = (
            f" within kernel prefix {'.'.join(str(x) for x in max_kernel)}.x"
            if max_kernel else ""
        )
        print(
            f"\nERROR: No akmods-zfs tags found matching "
            f"coreos-{channel}-{fedora_version}-*{hint} (excluding sha256).\n"
            f"  Check your Fedora version, channel, and kernel prefix.",
            file=sys.stderr,
        )
        sys.exit(1)

    parsed.sort(key=lambda t: t.kernel_tuple(), reverse=True)

    print(f"      Found {len(parsed)} matching tag(s). Latest: {parsed[0].tag}")
    if debug:
        for t in parsed[:5]:
            print(f"        {t.tag}")

    return parsed[0]


def find_matching_kinoite(
    latest_akmods: AkmodsTag,
    fedora_version: str,
    inspect_count: int,
    debug: bool,
) -> Optional[KinoiteTag]:
    print(f"\n[2/4] Listing tags for {KINOITE_REPO} …")
    all_tags = crane_ls(KINOITE_REPO, platform=KINOITE_PLATFORM)

    if debug:
        print(f"      Total tags fetched: {len(all_tags)}")

    parsed = [
        t for raw in all_tags
        if (t := parse_kinoite_tag(raw, fedora_version)) is not None
    ]

    if not parsed:
        print(
            f"\nERROR: No kinoite-main tags found matching Fedora {fedora_version}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Sort newest first by (date, build_num)
    parsed.sort(key=lambda t: t.build_tuple(), reverse=True)
    candidates = parsed[:inspect_count]

    print(
        f"      Found {len(parsed)} matching tag(s). "
        f"Inspecting the {len(candidates)} most recent …"
    )

    target_kv = latest_akmods.kernel_version  # e.g. "6.19.14"

    print(f"\n[3/4] Fetching image configs to read ostree.linux labels …")
    print(f"      Looking for kernel version: {target_kv}")

    match: Optional[KinoiteTag] = None

    for i, kt in enumerate(candidates, 1):
        print(f"      [{i:2d}/{len(candidates)}] {kt.tag}", end="", flush=True)
        try:
            cfg = crane_config(KINOITE_REPO, kt.tag, KINOITE_PLATFORM)
            kt.ostree_linux = extract_ostree_linux(cfg)
        except RuntimeError as exc:
            print(f"  ← SKIP (config error: {exc})")
            continue

        kv = kt.kernel_version()
        print(f"  ostree.linux={kt.ostree_linux!r}", end="")

        if kernel_versions_match(target_kv, kt.ostree_linux):
            print("  ✓ MATCH")
            if match is None:
                match = kt  # keep the newest match
        else:
            print(f"  (kernel {kv or '?'} ≠ {target_kv})")

    return match


def print_results(
    latest_akmods: AkmodsTag,
    match: Optional[KinoiteTag],
    channel: str,
    max_kernel: Optional[tuple],
    inspect_count: int,
    as_json: bool,
) -> None:
    print("\n" + "═" * 60)
    print("[4/4] Results")
    print("═" * 60)

    if as_json:
        result = {
            "akmods_zfs": {
                "repo": AKMODS_REPO,
                "channel": channel,
                "max_kernel": ".".join(str(x) for x in max_kernel) if max_kernel else None,
                "tag": latest_akmods.tag,
                "kernel_version": latest_akmods.kernel_version,
                "full_kernel": latest_akmods.full_kernel,
            },
            "kinoite_main": {
                "repo": KINOITE_REPO,
                "tag": match.tag if match else None,
                "ostree_linux": match.ostree_linux if match else None,
                "matched": match is not None,
            },
        }
        print(json.dumps(result, indent=2))
        return

    print(f"\nakmods-zfs latest tag  : {latest_akmods.tag}")
    print(f"  repo                 : {AKMODS_REPO}")
    print(f"  channel              : coreos-{channel}")
    if max_kernel:
        print(f"  kernel pin           : {'.'.join(str(x) for x in max_kernel)}.x")
    print(f"  kernel version       : {latest_akmods.kernel_version}")
    print(f"  full kernel string   : {latest_akmods.full_kernel}")

    if match:
        print(f"\nkinoite-main match tag : {match.tag}")
        print(f"  repo                 : {KINOITE_REPO}")
        print(f"  ostree.linux label   : {match.ostree_linux}")
        print(f"\n✅  Match found!")
        print(f"\n    akmods-zfs   → {AKMODS_REPO}:{latest_akmods.tag}")
        print(f"    kinoite-main → {KINOITE_REPO}:{match.tag}")
    else:
        print(
            f"\n❌  No kinoite-main tag found with kernel {latest_akmods.kernel_version} "
            f"in the last {inspect_count} builds."
        )
        print(
            f"    Try passing --inspect-count N (currently {inspect_count}) "
            f"to search further back."
        )

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare ublue-os akmods-zfs and kinoite-main kernel versions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s                          # Fedora 43, stable channel, any kernel
  %(prog)s -k 6.19                  # Pin to kernel 6.19.x
  %(prog)s -c testing -k 6.19      # Testing channel, kernel 6.19.x
  %(prog)s -f 42 -k 6.12           # Fedora 42, kernel 6.12.x
  %(prog)s -k 6.19 --json          # Machine-readable output
  %(prog)s -k 6.19 -n 40           # Search the last 40 kinoite builds
        """,
    )
    parser.add_argument(
        "--fedora-version", "-f",
        default="43",
        metavar="VER",
        help="Fedora major version to filter on (default: 43)",
    )
    parser.add_argument(
        "--channel", "-c",
        default="stable",
        choices=["stable", "testing"],
        help="CoreOS channel to filter akmods-zfs tags on (default: stable)",
    )
    parser.add_argument(
        "--max-kernel", "-k",
        type=parse_kernel_prefix,
        default=None,
        metavar="MAJOR.MINOR",
        help="Pin to a specific kernel major.minor (e.g. '6.19'). "
             "Tags with a different major.minor are ignored.",
    )
    parser.add_argument(
        "--inspect-count", "-n",
        type=int,
        default=KINOITE_INSPECT_COUNT,
        metavar="N",
        help=f"Number of recent kinoite tags to inspect for ostree.linux labels "
             f"(default: {KINOITE_INSPECT_COUNT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output final result as JSON",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print extra diagnostic info",
    )
    args = parser.parse_args()

    # --- Step 1: find latest akmods-zfs tag ---------------------------------
    latest_akmods = find_latest_akmods(
        fedora_version=args.fedora_version,
        channel=args.channel,
        max_kernel=args.max_kernel,
        debug=args.debug,
    )

    # --- Steps 2 & 3: find matching kinoite-main tag ------------------------
    match = find_matching_kinoite(
        latest_akmods=latest_akmods,
        fedora_version=args.fedora_version,
        inspect_count=args.inspect_count,
        debug=args.debug,
    )

    # --- Step 4: display results --------------------------------------------
    print_results(
        latest_akmods=latest_akmods,
        match=match,
        channel=args.channel,
        max_kernel=args.max_kernel,
        inspect_count=args.inspect_count,
        as_json=args.json,
    )

    sys.exit(0 if match else 1)


if __name__ == "__main__":
    main()
