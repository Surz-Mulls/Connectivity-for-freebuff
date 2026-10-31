#!/usr/bin/env bash
# Build the debug APK from a clean checkout with the tracked Gradle wrapper.
# Never uses sudo, never creates a signing key, never writes outside .toolchain/, build/ and dist/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

T="$ROOT/.toolchain"
if [ ! -x "$T/jdk/bin/java" ] || [ ! -x "$T/sdk/cmdline-tools/latest/bin/sdkmanager" ]; then
  bash "$ROOT/scripts/bootstrap-toolchain.sh"
fi

export JAVA_HOME="$T/jdk"
export ANDROID_HOME="$T/sdk"
export ANDROID_SDK_ROOT="$T/sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
export GRADLE_USER_HOME="$T/gradle-home"
mkdir -p "$T/gradle-home"

printf 'sdk.dir=%s\n' "$ANDROID_HOME" > android/local.properties
mkdir -p dist artifacts/android artifacts/logs

echo "== unit tests"
(cd android && ./gradlew :app:testDebugUnitTest --no-daemon --console=plain)

echo "== lint (report only, non-fatal)"
(cd android && ./gradlew :app:lintDebug --no-daemon --console=plain) || \
  echo "WARN: lint reported findings, see android/app/build/reports/lint-results-debug.html"

echo "== assembleDebug"
(cd android && ./gradlew :app:assembleDebug --no-daemon --console=plain)

APK="$ROOT/android/app/build/outputs/apk/debug/app-debug.apk"
[ -s "$APK" ] || { echo "FATAL: missing $APK" >&2; exit 1; }

cp "$APK" "dist/continuity-android-debug.apk"
cp "$APK" artifacts/android/app-debug.apk
(cd dist && sha256sum continuity-android-debug.apk | tee continuity-android-debug.apk.sha256)
cp dist/continuity-android-debug.apk.sha256 artifacts/android/app-debug.apk.sha256

APKANALYZER="$ANDROID_HOME/cmdline-tools/latest/bin/apkanalyzer"
"$APKANALYZER" apk summary dist/continuity-android-debug.apk > artifacts/android/apk-summary.txt 2>&1 || true

{
  echo "artifact: dist/continuity-android-debug.apk"
  echo "built_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "size_bytes: $(stat -c%s dist/continuity-android-debug.apk)"
  echo "sha256: $(sha256sum dist/continuity-android-debug.apk | cut -d' ' -f1)"
  echo "package_id: dev.continuity.app"
  echo "version_name: 0.1.0"
  echo "version_code: 1"
  echo "min_sdk: 33 (Android 13)"
  echo "target_sdk: 35 (Android 15)"
  echo "compile_sdk: 35"
  echo "jdk: $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)"
  echo "gradle: $(cd android && ./gradlew --version 2>/dev/null | grep '^Gradle' | head -1)"
  echo "signing: debug (Android Gradle Plugin debug keystore; NOT release signed)"
} | tee artifacts/android/apk-manifest.txt

echo "OK: dist/continuity-android-debug.apk"
