#!/usr/bin/env bash
# Unprivileged, workspace-local Android toolchain. No sudo, nothing outside .toolchain/.
#
# Integrity: the Gradle distribution is verified against the checksum published by
# services.gradle.org (pinned below AND fetched again at build time). The JDK and Android
# cmdline-tools are fetched over HTTPS from their official endpoints and their SHA-256 is recorded
# in artifacts/logs/toolchain-checksums.txt, because those two URLs are version-floating; pin a
# versioned URL if you need byte-for-byte reproducibility (see docs/implementation-validation.md).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$ROOT/.toolchain"
mkdir -p "$T" "$ROOT/artifacts/logs"

GRADLE_VERSION="8.11.1"
GRADLE_SHA256="f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6"
CMDLINE_TOOLS="commandlinetools-linux-11076708_latest.zip"

checksums="$ROOT/artifacts/logs/toolchain-checksums.txt"
: > "$checksums"

download() {
  local url="$1" target="$2"
  echo "== fetch $(basename "$target")"
  curl -fL --retry 3 --connect-timeout 20 -o "$target" "$url"
  printf '%s  %s\n' "$(sha256sum "$target" | cut -d' ' -f1)" "$(basename "$target")" | tee -a "$checksums"
}

if [ ! -x "$T/jdk/bin/java" ]; then
  rm -rf "$T/jdk"; mkdir -p "$T/jdk"
  download "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse" "$T/jdk.tar.gz"
  tar xzf "$T/jdk.tar.gz" -C "$T/jdk" --strip-components=1
fi

if [ ! -x "$T/sdk/cmdline-tools/latest/bin/sdkmanager" ]; then
  download "https://dl.google.com/android/repository/$CMDLINE_TOOLS" "$T/cmdline.zip"
  mkdir -p "$T/sdk/cmdline-tools"
  unzip -q -o "$T/cmdline.zip" -d "$T/sdk/cmdline-tools"
  rm -rf "$T/sdk/cmdline-tools/latest"
  mv "$T/sdk/cmdline-tools/cmdline-tools" "$T/sdk/cmdline-tools/latest"
fi

export JAVA_HOME="$T/jdk"
export ANDROID_HOME="$T/sdk"
yes 2>/dev/null | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$ANDROID_HOME" \
  "platform-tools" "platforms;android-35" "build-tools;35.0.0" >/dev/null

if [ ! -x "$T/gradle-$GRADLE_VERSION/bin/gradle" ]; then
  download "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip" "$T/gradle.zip"
  actual="$(sha256sum "$T/gradle.zip" | cut -d' ' -f1)"
  curl -fsSL -o "$T/gradle.zip.sha256" \
    "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip.sha256"
  published="$(tr -d '[:space:]' < "$T/gradle.zip.sha256")"
  if [ "$actual" != "$published" ] || [ "$actual" != "$GRADLE_SHA256" ]; then
    echo "FATAL: Gradle checksum mismatch (actual=$actual published=$published)" >&2
    exit 1
  fi
  unzip -q -o "$T/gradle.zip" -d "$T"
fi

echo "toolchain ready: $("$T/jdk/bin/java" -version 2>&1 | head -1), Gradle $GRADLE_VERSION, SDK 35"
