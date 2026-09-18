# Third-party notices

This repository's own code is MIT licensed (see [LICENSE](LICENSE)). It also redistributes
third-party code, listed below. The full license text of each component is kept next to the
vendored code so that it travels with any copy of the skill.

## image-to-editable-ppt

- **Upstream:** https://github.com/ningzimu/image-to-editable-ppt-skill (path `skills/image-to-editable-ppt`)
- **Pinned commit:** `b7be494e31a0ed56ef98716891db5474606b8cdf` (2026-09-16)
- **License:** MIT — Copyright (c) 2026 ningzimu
- **License text:** [`skills/research-figure-drawer/cli/LICENSE`](skills/research-figure-drawer/cli/LICENSE)
- **Integrity manifest:** [`skills/research-figure-drawer/cli/VENDOR.json`](skills/research-figure-drawer/cli/VENDOR.json)

Vendored into `skills/research-figure-drawer/` so that the figure skill can rebuild editable
PowerPoint files without requiring a second installed skill:

| Vendored path | Upstream path |
|---|---|
| `cli/` | `skills/image-to-editable-ppt/cli/` |
| `prompts/page-worker.md` | `skills/image-to-editable-ppt/prompts/page-worker.md` |
| `scripts/build-page-worker-prompt.py` | `skills/image-to-editable-ppt/scripts/build-page-worker-prompt.py` |
| `references/cli-helper.md` | `skills/image-to-editable-ppt/references/cli-helper.md` |
| `references/manifest-schema.md` | `skills/image-to-editable-ppt/references/manifest-schema.md` |
| `references/page-decision-tree.md` | `skills/image-to-editable-ppt/references/page-decision-tree.md` |
| `references/reconstruction-contract.md` | `skills/image-to-editable-ppt/SKILL.md` (body only, with a provenance header) |

The MIT license requires that the copyright notice and permission notice be included in all
copies or substantial portions of the software; that is why `cli/LICENSE` is committed here and
why every vendored file is listed in `cli/VENDOR.json` with a hash. Imported files are otherwise
unmodified: local integration rules live in `skills/research-figure-drawer/SKILL.md`,
`references/hybrid-reconstruction.md`, and `references/installation.md`, not in the vendored copies.
