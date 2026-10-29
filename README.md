# Continuity — Freebuff Implementation Handoff v6

This bundle separates the research handoff from the implementation task.

- `MASTER_AGENT_PROMPT_v6.md` is the current prompt for Freebuff.
- `PATCH_NOTES_CLAUDE.md` summarizes the v4 → v5 research patches documented by Claude.
- `research/FEATURE_GAP_ANALYSIS.md` contains the Apple-parity feature-gap review.
- `research/VERIFICATION_REPORT.md` contains repository/licence/stack findings and important caveats.
- `research/REPO_SHAS.tsv` records the inspected source revisions.
- `design/tokens.json` is the proposed canonical design-token source.
- `design/ui-concept.html` is a visual concept for the final UI polish phase, not a working application.
- `scripts/clone-research.sh` reproduces the reference research clones as described by the research pack.

## Role split

Claude's work here was research; its note that no builds or device tests were run is intentional and must not be treated as a failed implementation attempt. Freebuff is the builder. It must inspect the actual application repository/workspace, run the first real build early, implement the specified product, test what the environment permits and export real artifacts. This bundle is research and design material, not the application source code.

## Recommended use

1. Give Freebuff `MASTER_AGENT_PROMPT_v6.md` and this full ZIP.
2. Point Freebuff to the actual target product repository/workspace.
3. Tell it: “Use the supplied research pack and patch notes; do not repeat the entire research phase. Start by inspecting the real project and running the first baseline build, save the full logs, then implement the complete specification. Do not claim device/runtime tests without evidence.”
