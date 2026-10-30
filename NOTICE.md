# NOTICE — upstream references, licences and reused code

## This repository

Continuity is licensed **GPL-3.0-only**. The choice follows the prompt's combined-work rule: it is
compatible with the GPL-2.0-or-later/3.0 dual-licensed KDE Connect sources that informed the
feature design, and with the GPL-3.0 Linux Link/Vortex references.

**No source code was copied or vendored from any reference project.** The research pack in
`docs/research/` records what was read at which commit; the implementation here is original and
uses only the libraries listed below. No proprietary (Shrey113 Android-Dex) or unlicensed
(Use-As-Server) code, assets or binaries are included.

## Upstream projects that informed the design

| Project | URL | Licence (verified in the research pack) | What informed this work |
|---|---|---|---|
| Linux Link | https://github.com/ArvinKavaskov/linux-link | GPL-3.0 | Pinned-certificate identity, honest reconnect states, Hyprland second-screen approach (not used) |
| Vortex | https://github.com/zoir-dev/vortex | GPL-3.0 | Emoji-SAS pairing, content-shelf and live-item UX, Universal Control caveats |
| KDE Connect (desktop) | https://github.com/KDE/kdeconnect-kde | GPL-2.0-only OR GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL | Plugin taxonomy (notifications, share, find, presenter, digitizer, virtualmonitor). `remotecommands` deliberately **not** ported. |
| KDE Connect (Android) | https://github.com/KDE/kdeconnect-android | GPL-2.0-only OR GPL-3.0-only | Android permission/foreground-service patterns |
| Sefirah / Sefirah-Android | https://github.com/shrimqy/Sefirah(-Android) | GPL-3.0 | Android 15 sensitive-notification redaction notes (Windows-first desktop; not a Linux parity source) |
| LinLink | https://github.com/THARUN-BART/linlink | MIT | Call-audio claims treated as unverified |
| Use-As-Server | https://github.com/manjeetdeswal/Use-As-Server | **no LICENSE file** | Feature checklist only. Its `chmod 666 /dev/uinput` advice is explicitly rejected. |
| Shevery | https://github.com/HmnDev-Tech/shevery | Apache-2.0 | Module format reviewed; **not** used as a dependency |
| scrcpy | https://github.com/Genymobile/scrcpy | Apache-2.0 | DeX/Workspace path (`--new-display`, `--start-app`, `--flex-display`), invoked as an external binary |
| LocalSend | https://github.com/localsend/localsend | Apache-2.0 | Transfer UX comparison only (protocol not reused) |
| Misael-art android-dex | https://github.com/Misael-art/android-dex | MIT | Daemon/allowlisted-toolkit boundary and capability-probing ideas |
| Shrey113 Android-Dex | https://github.com/Shrey113/Android-Dex | **proprietary** | Feature/UX reference only; nothing copied or redistributed |
| RQuickShare | https://github.com/Martichou/rquickshare | GPL-3.0 | Optional Quick Share interop investigated; not integrated |
| Android Developers docs | https://developer.android.com | — | Desktop windowing, notification, clipboard and foreground-service rules |

Exact inspected commits: `docs/research/REPO_SHAS.tsv`. The research pack's own reports are
reproduced unmodified in `docs/research/`.

## Libraries used at runtime

| Library | Licence | Used by |
|---|---|---|
| cryptography | Apache-2.0 OR BSD-3-Clause | daemon identity, signatures, SAS |
| zeroconf (python-zeroconf) | LGPL-2.1 | daemon mDNS discovery |
| qrcode | BSD-3-Clause | pairing QR generation |
| dbus-next | MIT | optional D-Bus export (installed; see limitations) |
| AndroidX / Jetpack Compose / Material 3 | Apache-2.0 | Android app |
| Bouncy Castle (bcpkix-jdk18on) | MIT | Android certificate generation |
| Kotlin stdlib / kotlinx-coroutines | Apache-2.0 | Android app |
| PySide6 (development only) | LGPL-3.0 | headless QML verification on the build host only |

## Design references

`design/tokens.json` implements the Catppuccin Mocha and Latte palettes (MIT). The token names and
palette are used as product colours; `design/ui-concept.html` is the supplied visual reference.

## Attribution in the Android APK

The APK bundles AndroidX, Compose, Kotlin and Bouncy Castle. Their licence texts are included by the
build in `META-INF/` where the artifacts provide them; the debug APK is **debug-signed** and is not a
production release artifact.
