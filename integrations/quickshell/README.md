# Quickshell status panel (unverified)

`ContinuityPanel.qml` shows live daemon state (device, battery, active transfer, privacy mode) and
offers three safe actions: privacy-mode toggle, ring phone, push clipboard. It is a **client**: it
shells out to `continuityctl status --json` / `continuityctl …`, the same allowlisted IPC surface the
CLI and Qt UI use. No state is duplicated and no privileged action is exposed.

## Status

**Unverified on a live Quickshell.** The build host has no Hyprland/Quickshell session, so the QML
has not been executed; the earlier research pack also found no reference project with Quickshell
integration. Expect to adjust import names/API details to your installed Quickshell version
(`quickshell --version`) before trusting it.

## Install (reversible, one line)

1. Copy this directory somewhere stable, e.g. `~/.config/quickshell/continuity/`.
2. Add **one** line to your own shell config:

   ```qml
   import "continuity/ContinuityPanel.qml" as ContinuityPanel
   ContinuityPanel {}
   ```

3. Make sure `continuityctl` is on `PATH` for the shell process (install the daemon venv's bin dir,
   or symlink `continuityctl` into `~/.local/bin`).

No script in this repository edits `~/.config/quickshell`. To remove it, delete the directory and the
line you added.

## Why polling instead of D-Bus

Quickshell's documented I/O primitive is `Process`; a QML client cannot open the Unix socket
directly. Polling `continuityctl status --json` every 2 s is simple, bounded and cannot drift from the
daemon's state. If you prefer push updates, `continuityctl events` streams JSON lines and can be
wrapped in the same `Process` component.

## Test checklist (D02 in docs/batch-test-matrix.md)

- [ ] Panel appears and shows "No device connected" with the daemon stopped.
- [ ] Start the daemon → device name/state appear within 2 s.
- [ ] Ring the phone from the panel → phone rings and stops by itself.
- [ ] Toggle privacy → `continuityctl status` reflects it immediately.
- [ ] Kill the daemon → panel reports "daemon not running" instead of stale data.
