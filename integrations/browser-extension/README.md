# Browser tab handoff (Chromium/Vivaldi, MV3)

"Send this tab to phone" — real handoff, not a share sheet: the desktop sends the exact URL, the
phone shows a notification with that URL and opens it only when you tap.

## How it works

```
extension → chrome.runtime.sendNativeMessage("dev.continuity.handoff", {url})
          → native host (python, http(s)-only validation, no shell)
          → continuityctl handoff <fingerprint> <url>
          → daemon → phone (handoff.url, receiver confirmation)
```

The native host is a small Python script; it is **not** an installer or updater, has no network
access of its own and cannot execute arbitrary commands.

## Install

```bash
integrations/browser-extension/install.sh
```

Then load the unpacked extension from this directory (`chrome://extensions` → Developer mode →
Load unpacked) and put the printed extension ID into the generated host manifest (step 2 of the
script output). Until the ID matches, Chrome refuses the native messaging connection — that is
intentional.

## Status

- Extension + host: **implemented-unverified** (no browser session or phone on the build host).
- URL validation is enforced three times: popup/worker, native host, daemon (`validate_url`), and
  the Android side refuses anything that is not `http(s)`.
- The receiving phone never auto-opens: it posts a notification with the URL.

## Uninstall

```bash
integrations/browser-extension/uninstall.sh
```
