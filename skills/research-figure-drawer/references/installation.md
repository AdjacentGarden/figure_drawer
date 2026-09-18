# Installation

This skill is self-contained. It vendors the `editppt` reconstruction runtime at
`<skill-root>/cli` (MIT, from [image-to-editable-ppt](https://github.com/ningzimu/image-to-editable-ppt-skill),
pinned in `cli/VENDOR.json`), so installing this one skill is enough. Do not install the
standalone `image-to-editable-ppt` skill as well; a second copy would let the two halves drift apart.

## Codex / GPT desktop clients with skill support

Install this repository's skill globally, then restart the client so skill discovery refreshes:

```bash
npx -y skills@latest add AdjacentGarden/figure_drawer \
  --skill research-figure-drawer \
  --agent codex \
  --global
```

## Bundled runtime

The runtime's Python dependencies are declared in `cli/pyproject.toml`
(PyMuPDF, Pillow, openai, PyYAML, numpy, requests). Check everything at once:

```bash
python3 scripts/check_environment.py --strict
```

The check reports the bundled runtime, the `editppt` command it resolved, the Python
dependencies that are missing, and whether every vendored file still matches the hash
recorded in `cli/VENDOR.json`.

Then pick one of two ways to run it:

```bash
# 1. install the bundled package (gives you the `editppt` command)
python3 -m pip install -e <skill-root>/cli

# 2. or run it straight from the checkout, with no install step
python3 scripts/run_editppt.py --help
```

Both paths drive the same code. If `editppt --help` still fails after installing, run
`editppt setup` and `editppt doctor`, and read the vendored
[cli-helper.md](cli-helper.md) Pre-Run Check for `pipx`/`uv` alternatives.

## Image generation and authentication

The default workflow calls the GPT/Codex client's built-in `image_gen.imagegen` tool. It uses the account already signed in to the client and does not require `OPENAI_API_KEY`. Availability and usage limits follow the user's client plan and workspace permissions.

Exact `gpt-image-2` API selection is an optional fallback, not the default. It uses `editppt image generate --model gpt-image-2`, which may require supported Codex OAuth or a configured OpenAI-compatible API credential. Never commit API keys to this repository or a figure run directory.

PaddleOCR-VL is optional but recommended by the bundled runtime for more accurate text box and font-size hints. OCR authentication is separate from reference-image generation.

## Updating the vendored runtime

Vendored files are byte-for-byte upstream and must not be edited in place. To move to a newer
upstream commit, re-copy the files listed in `cli/VENDOR.json`, refresh that manifest, and run
`python3 -m unittest discover -s tests -v`; `tests/test_vendored_integrity.py` fails on any
undocumented drift. Attribution requirements are summarised in the repository's
`THIRD_PARTY_NOTICES.md`.

## Invocation

Explicit:

```text
$research-figure-drawer Turn this TikZ architecture into a publication-ready editable PowerPoint figure.
```

Automatic invocation is enabled for requests that clearly ask to turn scientific TeX, a method description, or an architecture workflow into an editable paper figure.
