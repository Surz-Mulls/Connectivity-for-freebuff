#!/usr/bin/env python3
"""Assemble one release directory from the artifacts a release-candidate build produced.

Nothing is rebuilt here. The input must contain the APK, AppImage, portable archive and exactly one
makepkg Arch package. The manual layout archive from package-linux.sh is never accepted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"@[A-Z0-9_]+@")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def kind(name: str) -> str:
    if name.endswith(".apk"):
        return "apk"
    if name.endswith(".AppImage"):
        return "appimage"
    if name.endswith("portable.tar.zst"):
        return "portable"
    if name.endswith(".pkg.tar.zst"):
        return "arch-makepkg"
    if name.endswith(".desktop"):
        return "desktop-entry"
    return "file"


def table(paths: list[pathlib.Path]) -> str:
    lines = ["| Asset | Size (B) | SHA-256 |", "|---|---:|---|"]
    for path in sorted(paths, key=lambda p: p.name):
        lines.append(f"| `{path.name}` | {path.stat().st_size} | `{sha256(path)}` |")
    return "\n".join(lines)


def render(template: pathlib.Path, output: pathlib.Path, values: dict[str, str]) -> None:
    text = template.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"@{key}@", value)
    left = sorted(set(PLACEHOLDER.findall(text)))
    if left:
        raise SystemExit(f"{template.name}: unfilled placeholders {left}")
    output.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ci-run", default="")
    parser.add_argument("--glibc", default="2.34")
    parser.add_argument("--dist", type=pathlib.Path, default=ROOT / "dist")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit(f"commit must be a full 40-character SHA: {args.commit!r}")

    required = {
        "apk": args.dist / "continuity-android-debug.apk",
        "appimage": args.dist / "continuity-linux-x86_64.AppImage",
        "portable": args.dist / "continuity-linux-x86_64-portable.tar.zst",
    }
    for label, path in required.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"missing {label}: {path}")

    packages = sorted((args.dist / "makepkg").glob("*.pkg.tar.zst"))
    if len(packages) != 1:
        raise SystemExit(f"expected exactly one makepkg package, found {packages}")
    package = packages[0]
    if package.name == "continuity-linux-x86_64.pkg.tar.zst":
        raise SystemExit("refusing the manually assembled layout archive name")

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    for source in [*required.values(), package, ROOT / "packaging/continuity.desktop"]:
        target = args.out / source.name
        shutil.copy2(source, target)
        if target.suffix == ".AppImage" or target.name.endswith(".AppImage"):
            target.chmod(0o755)

    assets = sorted(p for p in args.out.iterdir() if p.is_file())
    manifest_assets = []
    for path in assets:
        item = {"name": path.name, "type": kind(path.name), "size": path.stat().st_size,
                "sha256": sha256(path)}
        if item["type"] == "apk":
            item["signing"] = "debug"
        if item["type"] == "arch-makepkg":
            item["built_by_makepkg"] = True
            item["install"] = "sudo pacman -U " + path.name
        manifest_assets.append(item)

    manifest = {
        "schema": "continuity.release-manifest/1",
        "tag": args.tag,
        "commit": args.commit,
        "run_id": args.run_id,
        "run_url": f"https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/{args.run_id}",
        "built_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "GitHub Actions release-candidate workflow",
        "glibc_floor": args.glibc,
        "assets": manifest_assets,
        "notes": [
            "APK is debug-signed, not production-signed.",
            "Hardware/device journeys are not tested by this build.",
            "The Arch package is a genuine makepkg product and was installed with pacman -U in an Arch container.",
        ],
    }
    manifest_path = args.out / "BUILD-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    ci_text = (
        f"green `ci` run [`{args.ci_run}`](https://github.com/Surz-Mulls/"
        f"Connectivity-for-freebuff/actions/runs/{args.ci_run}) on the same commit"
        if args.ci_run
        else "not recorded in this build (the branch `ci` run on this commit must be green before dispatch)"
    )
    values = {
        "TAG": args.tag,
        "COMMIT": args.commit,
        "COMMIT_SHORT": args.commit[:7],
        "RUN_ID": args.run_id,
        "RUN_URL": f"https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/{args.run_id}",
        "CI_RUN_TEXT": ci_text,
        "GLIBC": args.glibc,
        "ARCH_ASSET": package.name,
        "DATE": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "ASSET_TABLE": table(assets),
    }
    notes = args.out / f"RELEASE_NOTES_{args.tag}.md"
    report = args.out / f"VALIDATION_REPORT_{args.tag}.md"
    render(ROOT / "docs/RELEASE_NOTES_TEMPLATE.md", notes, values)
    render(ROOT / "docs/RELEASE_REPORT_TEMPLATE.md", report, values)

    all_files = sorted(p for p in args.out.iterdir() if p.is_file())
    sums = args.out / "SHA256SUMS"
    with sums.open("w", encoding="utf-8") as fh:
        for path in all_files:
            fh.write(f"{sha256(path)}  {path.name}\n")

    print(f"assembled {len(all_files)} files in {args.out}")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verify_release.py"),
            "--local",
            str(args.out),
            "--expect-commit",
            args.commit,
        ],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
