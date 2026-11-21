#!/usr/bin/env python3
"""Verify a Continuity release candidate or published pre-release.

Usage:
  tools/verify_release.py v0.1.0-test.3
  tools/verify_release.py --local dist/release/v0.1.0-test.3 --expect-commit SHA

Standard library only. One PASS/FAIL/WARN/SKIP line per check; exits non-zero on any FAIL.
A tag input downloads the GitHub release assets into a temporary directory. Set GH_TOKEN or
GITHUB_TOKEN for API access; the token is never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

REPO = "Surz-Mulls/Connectivity-for-freebuff"
API = "https://api.github.com"
FORBIDDEN = (b"/opt/freestyle", b"/home/", b"/root/")
HEX64 = re.compile(rb"\b[a-f0-9]{64}\b")


class Report:
    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    def line(self, status: str, name: str, detail: str = "") -> None:
        print(f"{status}: {name}" + (f" — {detail}" if detail else ""))
        if status == "FAIL":
            self.failures += 1
        elif status == "WARN":
            self.warnings += 1

    def fail(self, name: str, detail: str) -> None:
        self.line("FAIL", name, detail)

    def warn(self, name: str, detail: str) -> None:
        self.line("WARN", name, detail)

    def ok(self, name: str, detail: str = "") -> None:
        self.line("PASS", name, detail)

    def skip(self, name: str, detail: str) -> None:
        self.line("SKIP", name, detail)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def token() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def api_request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": "continuity-release-verifier/1"}
    value = token()
    if value:
        headers["Authorization"] = f"Bearer {value}"
    return urllib.request.Request(url, headers=headers)


def api_json(url: str) -> dict:
    with urllib.request.urlopen(api_request(url), timeout=60) as response:
        return json.load(response)


def download(url: str, destination: pathlib.Path) -> None:
    with urllib.request.urlopen(
        api_request(url, accept="application/octet-stream"), timeout=300
    ) as response, destination.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def tag_commit(tag: str, report: Report) -> str | None:
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        refs = {}
        for line in result.stdout.splitlines():
            sha, ref = line.split(maxsplit=1)
            refs[ref] = sha
        if f"refs/tags/{tag}^{{}}" in refs:
            report.ok("tag resolves", f"{tag} -> peeled {refs[f'refs/tags/{tag}^{{}}']}")
            return refs[f"refs/tags/{tag}^{{}}"]
        if f"refs/tags/{tag}" in refs:
            report.ok("tag resolves", f"{tag} -> {refs[f'refs/tags/{tag}']}")
            return refs[f"refs/tags/{tag}"]
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    # Fallback for a checkout without git/remotes.
    try:
        ref = api_json(f"{API}/repos/{REPO}/git/ref/tags/{tag}")["object"]
        sha = ref["sha"]
        if ref.get("type") == "tag":
            sha = api_json(f"{API}/repos/{REPO}/git/tags/{sha}")["object"]["sha"]
        report.ok("tag resolves (API)", f"{tag} -> {sha}")
        return sha
    except (OSError, KeyError, urllib.error.URLError) as exc:
        report.fail("tag resolves", f"cannot resolve {tag}: {exc}")
        return None


def safe_asset_name(name: str) -> str | None:
    """Return a plain file name, or None for a path/name that must never be joined to a directory."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        return None
    candidate = pathlib.PurePosixPath(name)
    if candidate.name != name or ".." in candidate.parts:
        return None
    return name


def download_release(tag: str, target: pathlib.Path, report: Report) -> bool:
    try:
        release = api_json(f"{API}/repos/{REPO}/releases/tags/{tag}")
    except (OSError, urllib.error.URLError) as exc:
        report.fail("release exists", f"{tag}: {exc}")
        return False
    assets = release.get("assets") or []
    if not assets:
        report.fail("release assets", "release has no assets")
        return False
    report.ok("release exists", f"{tag}: {len(assets)} assets")
    for asset in assets:
        raw_name = str(asset.get("name", ""))
        name = safe_asset_name(raw_name)
        if name is None:
            report.fail("download", f"unsafe asset name {raw_name!r}")
            return False
        destination = target / name
        try:
            download(asset["browser_download_url"], destination)
        except (OSError, urllib.error.URLError) as exc:
            report.fail("download", f"{name}: {exc}")
            return False
    return True


def find_one(files: list[pathlib.Path], pattern: str, label: str, report: Report) -> pathlib.Path | None:
    matches = sorted(p for p in files if re.search(pattern, p.name))
    if len(matches) != 1:
        report.fail(label, f"expected exactly one match for {pattern}, found {len(matches)}")
        return None
    return matches[0]


def parse_sums(path: pathlib.Path, report: Report) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[a-f0-9]{64}", parts[0]):
            report.fail("SHA256SUMS syntax", f"line {number}: {line!r}")
            continue
        name = safe_asset_name(parts[1].lstrip("*"))
        if name is None:
            report.fail("SHA256SUMS syntax", f"line {number}: unsafe asset name {parts[1]!r}")
            continue
        entries[name] = parts[0]
    if not entries:
        report.fail("SHA256SUMS syntax", "no entries")
    return entries


def check_sums(directory: pathlib.Path, report: Report) -> tuple[dict[str, str], list[pathlib.Path]]:
    sums_path = directory / "SHA256SUMS"
    if not sums_path.is_file():
        report.fail("SHA256SUMS", "missing")
        return {}, []
    entries = parse_sums(sums_path, report)
    files = [p for p in directory.iterdir() if p.is_file()]
    for name, expected in entries.items():
        path = directory / name
        if not path.is_file():
            report.fail("SHA256SUMS entry", f"{name} listed but missing")
            continue
        actual = sha256(path)
        if actual != expected:
            report.fail("SHA256SUMS entry", f"{name}: expected {expected}, measured {actual}")
    if entries:
        report.ok("SHA256SUMS entries", f"{len(entries)} files match")
    for path in files:
        if path.name in {"SHA256SUMS", "BUILD-MANIFEST.json"}:
            continue
        if path.name.startswith(("RELEASE_NOTES_", "VALIDATION_REPORT_")):
            continue
        if path.name not in entries:
            report.warn("unlisted asset", f"{path.name} is not covered by SHA256SUMS")
    return entries, files


def check_manifest(
    directory: pathlib.Path, expected_commit: str | None, report: Report
) -> None:
    path = directory / "BUILD-MANIFEST.json"
    if not path.is_file():
        report.fail("BUILD-MANIFEST.json", "missing")
        return
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.fail("BUILD-MANIFEST.json", f"invalid JSON: {exc}")
        return
    report.ok("BUILD-MANIFEST.json", f"{len(manifest.get('assets', []))} assets")
    commit = str(manifest.get("commit", ""))
    if expected_commit:
        if commit == expected_commit:
            report.ok("manifest commit", commit)
        else:
            report.fail("manifest commit", f"manifest {commit!r} != expected {expected_commit!r}")
    else:
        report.skip("manifest commit", "no tag or --expect-commit supplied")
    for asset in manifest.get("assets", []):
        raw_name = str(asset.get("name", ""))
        name = safe_asset_name(raw_name)
        if name is None:
            report.fail("manifest asset", f"unsafe name {raw_name!r}")
            continue
        target = directory / name
        if not target.is_file():
            report.fail("manifest asset", f"{name} missing")
            continue
        if sha256(target) != asset.get("sha256"):
            report.fail("manifest asset", f"{name} hash does not match manifest")
    if (directory / "BUILD-MANIFEST.json").is_file():
        report.ok("manifest assets present")


def is_elf(path: pathlib.Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def check_appimage(image: pathlib.Path, report: Report) -> None:
    try:
        os.chmod(image, 0o755)
    except OSError:
        pass
    with tempfile.TemporaryDirectory(prefix="continuity-verify-") as tmp:
        work = pathlib.Path(tmp)
        env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
        try:
            subprocess.run(
                [str(image.resolve()), "--appimage-extract"],
                cwd=work,
                env=env,
                capture_output=True,
                timeout=240,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            report.fail("AppImage extract", str(exc))
            return
        root = work / "squashfs-root"
        if not root.is_dir():
            report.fail("AppImage extract", "no squashfs-root")
            return
        report.ok("AppImage extract", "squashfs-root created")
        binaries = sorted(p for p in (root / "usr/bin").iterdir() if p.is_file())
        if not binaries:
            report.fail("AppImage usr/bin", "empty")
        else:
            bad = [p.name for p in binaries if not is_elf(p)]
            if bad:
                report.fail("AppImage usr/bin ELF", f"non-ELF: {bad}")
            else:
                report.ok("AppImage usr/bin ELF", f"{len(binaries)} files")
        launchers = [root / "AppRun", root / "appenv.sh", root / "qml_launcher.py"]
        launchers += sorted(root.glob("*.desktop"))
        launchers += binaries
        hits = []
        for path in launchers:
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if any(needle in data for needle in FORBIDDEN):
                hits.append(path.relative_to(root).as_posix())
        if hits:
            report.fail("AppImage host paths", f"forbidden paths in {hits}")
        else:
            report.ok("AppImage host paths", "no /opt/freestyle, /home/ or /root/ in launchers")
        home = work / "home"
        home.mkdir()
        try:
            result = subprocess.run(
                [str(root / "AppRun"), "--self-test"],
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": str(home),
                    "QT_QPA_PLATFORM": "offscreen",
                },
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            report.fail("AppImage self-test", str(exc))
            return
        if result.returncode == 0 and "self-test ok" in result.stdout:
            report.ok("AppImage self-test", result.stdout.strip().splitlines()[-1])
        else:
            report.fail(
                "AppImage self-test",
                f"exit {result.returncode}: {(result.stdout + result.stderr).strip()[-300:]}",
            )


def apk_has_v2_signature(data: bytes) -> bool:
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        return False
    try:
        cd_offset = struct.unpack_from("<I", data, eocd + 16)[0]
        if cd_offset < 24 or data[cd_offset - 16 : cd_offset] != b"APK Sig Block 42":
            return False
        trailing = struct.unpack_from("<Q", data, cd_offset - 24)[0]
        block_start = cd_offset - trailing - 8
        if block_start < 0:
            return False
        leading = struct.unpack_from("<Q", data, block_start)[0]
        return leading == trailing
    except struct.error:
        return False


def check_apk(apk: pathlib.Path, report: Report) -> None:
    try:
        with zipfile.ZipFile(apk) as archive:
            bad = archive.testzip()
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        report.fail("APK zip", str(exc))
        return
    if bad:
        report.fail("APK zip", f"corrupt member {bad}")
    elif "AndroidManifest.xml" not in names:
        report.fail("APK zip", "AndroidManifest.xml missing")
    else:
        report.ok("APK zip", f"{len(names)} members")
    data = apk.read_bytes()
    if apk_has_v2_signature(data):
        report.ok("APK signature", "v2+ signing block present")
    else:
        report.fail("APK signature", "no v2+ APK Signing Block")


def tar_names(path: pathlib.Path, report: Report) -> list[str]:
    try:
        result = subprocess.run(
            ["tar", "--zstd", "-tf", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report.fail("tar", f"{path.name}: {exc}")
        return []
    if result.returncode != 0:
        report.fail("tar", f"{path.name}: {result.stderr.strip()[:200]}")
        return []
    return [line for line in result.stdout.splitlines() if line]


def check_arch(package: pathlib.Path, report: Report) -> None:
    raw = tar_names(package, report)
    names = {name[2:] if name.startswith("./") else name for name in raw}
    if not names:
        return
    for required in (".PKGINFO", ".BUILDINFO"):
        if required in names:
            report.ok("Arch metadata", required)
        else:
            report.fail("Arch metadata", f"{required} missing")
    if ".MTREE" in names:
        report.ok("Arch metadata", ".MTREE")
    else:
        report.warn("Arch metadata", ".MTREE missing — package was not built by makepkg")
    if names:
        report.ok("Arch package", f"{len(names)} entries")


def check_portable(portable: pathlib.Path, report: Report) -> None:
    raw = tar_names(portable, report)
    names = [name[2:] if name.startswith("./") else name for name in raw]
    names = [name for name in names if name and name != "."]
    if not names:
        report.fail("portable layout", "empty archive")
        return
    tops = {name.split("/", 1)[0] for name in names}
    unsafe = [name for name in names if name.startswith("/") or name.startswith("../")]
    if len(tops) != 1 or unsafe:
        report.fail(
            "portable layout",
            f"expected one safe top-level directory, found {sorted(tops)}"
            + (f", unsafe entries {unsafe[:3]}" if unsafe else ""),
        )
    else:
        top = next(iter(tops))
        if not all(name == top or name.startswith(top + "/") for name in names):
            report.fail("portable layout", f"entries do not all live under {top}")
        else:
            report.ok("portable layout", f"single top-level directory {top}")


def check_report(directory: pathlib.Path, entries: dict[str, str], report: Report) -> None:
    reports = sorted(directory.glob("VALIDATION_REPORT_*.md"))
    if not reports:
        report.skip("validation report", "no report asset")
        return
    known = set(entries.values())
    mismatched: list[tuple[str, str]] = []
    quoted_count = 0
    for path in reports:
        quoted = {m.decode() for m in HEX64.findall(path.read_bytes())}
        quoted_count += len(quoted)
        mismatched.extend((path.name, digest) for digest in sorted(quoted - known))
    if mismatched:
        first = ", ".join(f"{name}:{digest[:12]}" for name, digest in mismatched[:3])
        report.warn("validation report hashes",
                    f"{len(mismatched)} digest(s) in {len(reports)} report(s) not in SHA256SUMS ({first})")
    else:
        report.ok("validation report hashes",
                  f"{len(reports)} report(s), {quoted_count} quoted SHA-256 value(s) match SHA256SUMS")


def verify(directory: pathlib.Path, expected_commit: str | None, report: Report) -> None:
    if not directory.is_dir():
        report.fail("candidate directory", f"missing {directory}")
        return
    entries, files = check_sums(directory, report)
    check_manifest(directory, expected_commit, report)
    appimage = find_one(files, r"\.AppImage$", "AppImage present", report)
    if appimage:
        check_appimage(appimage, report)
    apk = find_one(files, r"\.apk$", "APK present", report)
    if apk:
        check_apk(apk, report)
    arch = find_one(files, r"\.pkg\.tar\.zst$", "Arch package present", report)
    if arch:
        check_arch(arch, report)
    portable = find_one(files, r"portable\.tar\.zst$", "portable archive present", report)
    if portable:
        check_portable(portable, report)
    check_report(directory, entries, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", nargs="?")
    parser.add_argument("--local", type=pathlib.Path)
    parser.add_argument("--expect-commit")
    args = parser.parse_args()
    if bool(args.tag) == bool(args.local):
        parser.error("provide exactly one of TAG or --local DIR")
    report = Report()
    if args.local:
        verify(args.local.resolve(), args.expect_commit, report)
    else:
        # Resolve exactly once: a second network lookup could disagree and produce a false FAIL.
        expected = tag_commit(args.tag, report)
        with tempfile.TemporaryDirectory(prefix=f"continuity-{args.tag}-") as tmp:
            target = pathlib.Path(tmp)
            if not download_release(args.tag, target, report):
                print(f"FAIL: release {args.tag} could not be downloaded")
                return 1
            verify(target, expected, report)
    print(
        f"\n{report.failures} FAIL, {report.warnings} WARN"
        + ("" if report.failures == 0 else " — release must not be published")
    )
    return 0 if report.failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
