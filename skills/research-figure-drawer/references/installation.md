# Installation

This skill depends on `image-to-editable-ppt` and its `editppt` CLI.

## Codex / GPT desktop clients with skill support

Install both repositories globally, then restart the client so skill discovery refreshes:

```bash
npx -y skills@latest add AdjacentGarden/figure_drawer \
  --skill research-figure-drawer \
  --agent codex \
  --global

npx -y skills@latest add ningzimu/image-to-editable-ppt-skill \
  --skill image-to-editable-ppt \
  --agent codex \
  --global
```

The dependency's current installation instructions govern installation of its bundled CLI. If `editppt --help` is unavailable after skill installation, follow the dependency skill's pre-run setup, typically:

```bash
pipx install --force --editable <image-to-editable-ppt-skill-root>/cli
editppt doctor
```

## Image generation and authentication

The default workflow calls the GPT/Codex client's built-in `image_gen.imagegen` tool. It uses the account already signed in to the client and does not require `OPENAI_API_KEY`. Availability and usage limits follow the user's client plan and workspace permissions.

Exact `gpt-image-2` API selection is an optional fallback, not the default. It uses `editppt image generate --model gpt-image-2`, which may require supported Codex OAuth or a configured OpenAI-compatible API credential. Never commit API keys to this repository or a figure run directory.

PaddleOCR-VL is optional but recommended by the dependency skill for more accurate text box and font-size hints. OCR authentication is separate from reference-image generation.

## Invocation

Explicit:

```text
$research-figure-drawer Turn this TikZ architecture into a publication-ready editable PowerPoint figure.
```

Automatic invocation is enabled for requests that clearly ask to turn scientific TeX, a method description, or an architecture workflow into an editable paper figure.
