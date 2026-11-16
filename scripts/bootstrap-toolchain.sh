#!/usr/bin/env bash
# Unprivileged, workspace-local Android toolchain. No sudo, nothing outside .toolchain/.
#
# Every downloaded archive is checked against a hard-coded SHA-256 before it is unpacked or
# executed. Versions are pinned to versioned URLs, not "latest" endpoints. The measured digests and
# their provenance are recorded in docs/PINNED_TOOLING.md; a mismatch is fatal.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$ROOT/.toolchain"
mkdir -p "$T" "$ROOT/artifacts/logs"

# Eclipse Temurin JDK 21.0.13+9 (LTS), x86_64 Linux. The checksum is the upstream
# OpenJDK21U-jdk_x64_linux_hotspot_21.0.13_9.tar.gz.sha256.txt value.
JDK_VERSION="21.0.13+9"
JDK_NAME="OpenJDK21U-jdk_x64_linux_hotspot_21.0.13_9.tar.gz"
JDK_URL="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/${JDK_NAME}"
JDK_SHA256="d7f5d5cf865a2902b70ff549b97586a7d3f234e016f041ab447ea740c7d66d1c"

# Android command-line tools build 11076708 contains the versioned sdkmanager. This artifact is
# what dl.google.com publishes for that build; pin its digest so a changed server response fails.
CMDLINE_TOOLS="commandlinetools-linux-11076708_latest.zip"
# Measured 2026-11-16: this build now contains command-line-tools 12.0 (153607504 bytes).
# The earlier cached zip was 10.0 and has a different digest; CI caught the rotation.
CMDLINE_TOOLS_SHA256="2d2d50857e4eb553af5a6dc3ad507a17adf43d115264b1afc116f95c92e5e258"

GRADLE_VERSION="8.11.1"
GRADLE_SHA256="f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6"

checksums="$ROOT/artifacts/logs/toolchain-checksums.txt"
: > "$checksums"

verify_sha256() {
  local file="$1" expected="$2" label="$3" actual
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
  if [ "$actual" != "$expected" ]; then
    echo "FATAL: $label checksum mismatch (pinned $expected, measured $actual)" >&2
    exit 1
  fi
  printf '%s  %s\n' "$actual" "$(basename "$file")" | tee -a "$checksums"
}

fetch_pinned() {
  local url="$1" target="$2" expected="$3" label="$4"
  if [ -f "$target" ]; then
    echo "== using cached $label"
    verify_sha256 "$target" "$expected" "$label"
    return
  fi
  echo "== fetch $label"
  local tmp
  tmp="$(mktemp "$target.part.XXXXXX")"
  if ! curl -fL --retry 3 --connect-timeout 20 -o "$tmp" "$url"; then
    rm -f "$tmp"
    echo "FATAL: could not download $label from $url" >&2
    exit 1
  fi
  verify_sha256 "$tmp" "$expected" "$label"
  mv "$tmp" "$target"
}

if [ ! -x "$T/jdk/bin/java" ]; then
  rm -rf "$T/jdk"
  mkdir -p "$T/jdk"
  fetch_pinned "$JDK_URL" "$T/jdk.tar.gz" "$JDK_SHA256" "Temurin JDK $JDK_VERSION"
  tar xzf "$T/jdk.tar.gz" -C "$T/jdk" --strip-components=1
else
  echo "== reusing $T/jdk ($(. "$T/jdk/release"; echo "$JAVA_VERSION"))"
  [ -f "$T/jdk.tar.gz" ] && verify_sha256 "$T/jdk.tar.gz" "$JDK_SHA256" "Temurin JDK $JDK_VERSION"
fi

if [ ! -x "$T/sdk/cmdline-tools/latest/bin/sdkmanager" ]; then
  fetch_pinned "https://dl.google.com/android/repository/$CMDLINE_TOOLS" \
    "$T/cmdline-tools.zip" "$CMDLINE_TOOLS_SHA256" "Android command-line tools"
  mkdir -p "$T/sdk/cmdline-tools"
  unzip -q -o "$T/cmdline-tools.zip" -d "$T/sdk/cmdline-tools"
  rm -rf "$T/sdk/cmdline-tools/latest"
  mv "$T/sdk/cmdline-tools/cmdline-tools" "$T/sdk/cmdline-tools/latest"
else
  echo "== reusing $T/sdk/cmdline-tools/latest"
  [ -f "$T/cmdline-tools.zip" ] && verify_sha256 "$T/cmdline-tools.zip" \
    "$CMDLINE_TOOLS_SHA256" "Android command-line tools"
fi

export JAVA_HOME="$T/jdk"
export ANDROID_HOME="$T/sdk"
# `yes` receives SIGPIPE when sdkmanager has read enough input. With pipefail that would turn a
# successful licence acceptance into exit 141, so judge only sdkmanager's status.
set +o pipefail
yes 2>/dev/null | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$ANDROID_HOME" \
  "platform-tools" "platforms;android-35" "build-tools;35.0.0" >/dev/null
sdk_rc=${PIPESTATUS[1]}
set -o pipefail
if [ "$sdk_rc" -ne 0 ]; then
  echo "FATAL: sdkmanager failed with exit $sdk_rc" >&2
  exit "$sdk_rc"
fi

if [ ! -x "$T/gradle-$GRADLE_VERSION/bin/gradle" ]; then
  fetch_pinned "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip" \
    "$T/gradle.zip" "$GRADLE_SHA256" "Gradle $GRADLE_VERSION"
  curl -fsSL -o "$T/gradle.zip.sha256" \
    "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip.sha256"
  published="$(tr -d '[:space:]' < "$T/gradle.zip.sha256")"
  if [ "$published" != "$GRADLE_SHA256" ]; then
    echo "FATAL: Gradle upstream checksum file disagrees with the pinned value" >&2
    exit 1
  fi
  unzip -q -o "$T/gradle.zip" -d "$T"
else
  echo "== reusing Gradle $GRADLE_VERSION"
fi

echo "toolchain ready: $("$T/jdk/bin/java" -version 2>&1 | head -1), Gradle $GRADLE_VERSION, SDK 35"
