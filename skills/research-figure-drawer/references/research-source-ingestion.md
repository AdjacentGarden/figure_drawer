# Research-source ingestion for image-first figures

Use this workflow when the user supplies a paper, implementation, dataset, or
local paths to those sources and wants a new method/mechanism figure.

## External-generation authorization

The GPT image stage sends a curated prompt to an external image service. Record
whether the user has authorized that transmission for this run. Authorization
for one paper does not automatically cover unrelated projects.

If authorized, inspect the supplied local sources before image generation. The
image model cannot open a local path such as `/data/project/model.py`; a path by
itself is not useful evidence. Read the relevant material locally, summarize it
into `figure_spec.json`, and include the path and hash only as provenance.

## Evidence precedence

Use this order when sources disagree:

1. The paper's stated method and equations define the scientific claim.
2. The implementation clarifies module nesting, repeated stages, tensor flow,
   configuration-controlled branches, and the names actually used in code.
3. Dataset metadata clarifies modalities, sample organization, label types,
   temporal/spatial structure, and suitable input/output visual motifs.

Do not silently rewrite the paper around accidental implementation details.
Record disagreements and omit uncertain details from the generated figure until
they are resolved.

## What to inspect

- Paper: title, abstract, method, equations, architecture descriptions, figure
  captions, training/inference distinctions, and terminology.
- Code: model definitions, forward paths, heads, memory/state updates, loss
  wiring, key configuration files, and dataset adapters. Ignore vendored
  dependencies, caches, checkpoints, build products, and secrets.
- Dataset: schema, split metadata, modality names, annotations, representative
  dimensions, and a few non-sensitive examples. Do not place an entire dataset,
  binary samples, checkpoints, or credentials into the prompt.

For a directory, first inventory it and then read only files relevant to the
figure. Never recursively paste a repository or dataset into the image prompt.

## `source_evidence` entries

Add a `source_evidence` array to `figure_spec.json`:

```json
[
  {
    "role": "paper",
    "path": "/path/to/paper.pdf",
    "sha256": "...",
    "summary": "The method builds a three-level temporal pyramid and applies one HMI block per level."
  },
  {
    "role": "code",
    "path": "/path/to/libs/modeling/video_net.py",
    "sha256": "...",
    "summary": "The forward path confirms short-buffer attention followed by selective state recurrence."
  },
  {
    "role": "dataset",
    "path": "/path/to/dataset/annotations",
    "sha256": "...",
    "summary": "Samples contain streaming video features, text queries, and temporal start/end annotations."
  }
]
```

Summaries must state figure-relevant facts, not generic descriptions. The prompt
builder passes these entries to GPT image generation as supporting evidence;
the modules, edges, formulas, and exact labels in the rest of the spec remain
the hard constraints.

## Mandatory image-first gate

For research-source authoring, do not build the final WPS geometry directly
from the paper or code. The required sequence is:

```text
paper + code + dataset evidence
  -> curated figure_spec.json
  -> GPT-generated reference PNG
  -> scientific review against the spec
  -> reference-guided editable WPS/PPT reconstruction
  -> WPS reopen render and editability audit
```

Regenerate or edit the reference when its topology is wrong. Do not compensate
for a scientifically wrong reference by silently producing a different final
PPT. The accepted reference is the visual contract for reconstruction, while
the spec remains the scientific contract.
