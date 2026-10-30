# Baseline: KDE Connect phone→laptop remote input (prompt §0.4)

## Status: **BLOCKED — not reproduced in this environment**

The brief asks for this to be reproduced *before* designing our input path. That is impossible from
this build host: it has no Arch/Hyprland session, no GPU, no `kdeconnect` installation and no access
to the Mi 12. No command below was run here, and no result is claimed. What follows is the exact
reproducible procedure plus the evidence template to fill in on the real machines.

## Prerequisites

* Laptop: Arch Linux, Hyprland session, stock KDE Connect (`kdeconnect` + `kdeconnect-cli`).
* Phone: Xiaomi Mi 12, Android 15 / HyperOS, KDE Connect installed and paired.
* Both on the same LAN. Do **not** change any debugging/developer setting for this baseline.

## Procedure (run on the laptop unless stated)

```bash
# 1. Discovery
kdeconnect-cli -l --id-name-only
kdeconnect-cli -d <device-id> --list-plugins

# 2. Enable remote input on both sides
kdeconnect-cli -d <device-id> --enable-plugin remoteinput
# On the phone: KDE Connect → device → Plugins → Remote input = on

# 3. Capture daemon logs while sending a test pointer event from the phone
journalctl --user -u kdeconnectd -f > /tmp/kdeconnect-remoteinput.log &
# ...use the phone's remote-input screen for ~20 s...
kill %1
```

```bash
# 4. Which Wayland input mechanism did it try?
grep -iE 'portal|libei|uinput|x11|xwayland|remoteinput|fakeinput' /tmp/kdeconnect-remoteinput.log
echo "session: $XDG_SESSION_TYPE / desktop: $XDG_CURRENT_DESKTOP / wayland: $WAYLAND_DISPLAY"
command -v ydotool wtype wl-copy hyprctl; ls -l /dev/uinput; systemctl --user status xdg-desktop-portal-hyprland
```

Optional (only if the portals are the suspect): `busctl --user introspect org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop | grep -i input`
and check whether `RemoteDesktop` / `InputCapture` are advertised by
`xdg-desktop-portal-hyprland`.

## Evidence template

| Field | Value |
|---|---|
| `kdeconnect-cli -l --id-name-only` | _to fill_ |
| Remote-input plugin enabled (phone / laptop) | _to fill_ |
| Device id used | _to fill_ |
| `journalctl` excerpt around the test | _to fill_ |
| Mechanism attempted (portal/libei, uinput, X11/XWayland) | _to fill_ |
| Portal interfaces advertised | _to fill_ |
| `/dev/uinput` group and permissions | _to fill_ |
| Result (pointer moves? click works?) | _to fill_ |

## Hypothesis (not a diagnosis)

The pack's hypothesis is the Wayland input-injection path on Hyprland. It stays a hypothesis until
the table above is filled in.

## Consequence for this implementation

Our input-adjacent features are designed so they do **not** depend on that mechanism:

* DeX Workspace input goes through **scrcpy** (`--new-display`, keyboard/mouse injection), which is
  an independent, documented path and requires explicit ADB authorization.
* Desktop→phone control is *not* implemented in this build; nothing pretends it works.
* Universal Control is listed as blocked in `docs/feature-matrix.md` pending the portal evidence and
  an on-device test.

**needs_user:** run the procedure above on the laptop + phone, paste the table (and a redacted log
excerpt) into this file, and re-run diagnostics. Until then this stays blocked.
