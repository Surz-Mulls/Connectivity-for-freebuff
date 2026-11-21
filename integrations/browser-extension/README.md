# Browser tab handoff (Chromium/Vivaldi and Firefox/Zen, MV3)

"Send this tab to phone" — real handoff, not a share sheet: the desktop sends the exact URL, the
phone shows a notification with that URL and opens it only when you tap.

## How it works

```
extension → runtime.sendNativeMessage("dev.continuity.handoff", {url})
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

The installer writes the shared host wrapper and two kinds of native-messaging manifest:

| Browser family | Manifest directory | Allow-list |
|---|---|---|
| Chrome, Chromium, Vivaldi, Brave | `~/.config/<vendor>/NativeMessagingHosts/` | `allowed_origins` with the key-derived Chromium ID `pocpmobopjgeddenbhlieogenkjfldjn` |
| Firefox, Zen | `~/.mozilla/native-messaging-hosts/` | `allowed_extensions` with the declared Gecko ID `dev.continuity.handoff@continuity.local` |

Chromium's key-derived ID is not reused for Firefox. `manifest.json` pins both the Chromium public
key and `browser_specific_settings.gecko.id`; the installer reads each value rather than guessing.

### Chromium / Vivaldi

1. Open `chrome://extensions` (or `vivaldi://extensions`), enable Developer mode, and choose
   **Load unpacked** → this directory.
2. The native-messaging manifests already allow the printed ID. Reload the extension after
   reinstalling the host. Until the ID matches, Chrome refuses the connection — intentionally.

### Firefox / Zen

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **This Firefox** → **Load Temporary Add-on…**.
3. Select `integrations/browser-extension/manifest.json`.

The temporary add-on disappears when the browser restarts; repeat the steps after a restart. The
native host registration is persistent until `uninstall.sh`.

**MV3 caveat:** this manifest targets Chromium's MV3 service worker. Firefox/Zen's MV3
implementation may use an event page rather than `background.service_worker`; loading and native
messaging are therefore **implemented-unverified** in Firefox/Zen. If the background worker does
not start, the host cannot receive a URL even though the native-messaging manifest is correct.

## Status

- Extension + native host: **implemented-unverified** (no browser session or phone on the build
  host). The installer and both manifest shapes are covered by a JVM-free Python test; the browser
  runtime is not.
- URL validation is enforced three times: popup/worker, native host, daemon (`validate_url`), and
  the Android side refuses anything that is not `http(s)`.
- The receiving phone never auto-opens: it posts a notification with the URL.

## Uninstall

```bash
integrations/browser-extension/uninstall.sh
```

Removes all Chromium-family manifests, the Firefox/Zen manifest, and the host helper. Remove the
unpacked/temporary extension from the browser separately.
