# Continuity pack (v5)

Everything for the Arch (Hyprland/Quickshell) + Android 15 (Mi 12) "Apple-like Continuity + DeX workspace" project.

| File | What it is |
|---|---|
| `MASTER_AGENT_PROMPT_v5.md` | The prompt to give your agent. Your v4 with verified facts, corrections, new features, monitoring protocol, Quickshell contract, Android 15 notes (Sections 0, 4A, 4B, 18, 19 are new). |
| `VERIFICATION_REPORT.md` | Every repo in the prompt checked against a real clone: licence, stack, what is true, what was wrong, what is still unverified. |
| `FEATURE_GAP_ANALYSIS.md` | Apple Continuity (incl. macOS 26) vs. the prompt, with sources, and what v5 adds. |
| `REPO_SHAS.tsv` | The exact upstream commits that were read. |
| `scripts/clone-research.sh` | Re-creates those clones at those commits (tested on two repos). |
| `design/tokens.json` | Canonical design tokens (Catppuccin Mocha + Latte). |
| `design/ui-concept.html` | Open in a browser: concept screens for the Quickshell popup, desktop app and Android. Concept only. |

## How to use

1. Unzip into your project's parent folder, or tell the agent where the pack is.
2. Give the agent `MASTER_AGENT_PROMPT_v5.md` as its instructions and say: "The pack is in `<path>`; copy `design/` and the research files into the project as Section 0.1 says."
3. Run `scripts/clone-research.sh` first if the agent has no network access to GitHub from its sandbox.

## What to watch while it runs

- `STATUS.json` and `PROGRESS.md` in the project root (Section 0.2 of the prompt). `state: waiting-user` means it needs something from you; the exact steps are in `needs_user`.
- `git log --oneline`: one commit per module, status in the message.
- It must stop and ask before anything in Section 0.3 (sudo, pacman, modprobe, udev/firewall rules, `adb install/pair/tcpip`, debug settings, pushing).

## Honest limits of this pack

Nothing was built or run: it was produced from reading cloned source and web documentation, with no phone, no Hyprland session and no Android SDK in the sandbox. Items marked "verify" in the prompt are exactly the ones that need your device or the official Android docs.
