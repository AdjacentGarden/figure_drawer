# Scientific visual design

Use this reference while authoring the GPT Image prompt and evaluating the reference image.

## Publication profile

Default to a compact, print-friendly figure suitable for CVPR, NeurIPS, ICLR, ICML, ACL, or EMNLP:

- white or near-white background;
- restrained palette with one primary, one secondary, and one accent color;
- clear left-to-right or bottom-to-top reading order;
- strong grouping through whitespace and subtle region fills;
- short labels, consistent typography, and generous internal padding;
- semantic icons or tensor motifs only when they help identify modality or operation;
- connectors attached to module boundaries with unambiguous arrowheads;
- no gratuitous gradients, glassmorphism, UI chrome, heavy shadows, or poster-like decoration.

## Structure before decoration

The image must communicate hierarchy, flow, and scientific novelty at normal paper scale. Use containers for stages, not for every individual word. Use alternate shapes deliberately: tensor stacks for features, grids for sampling, small operator nodes for arithmetic, ribbons for sequences, paired lanes for modalities, and subtle braces for repeated blocks.

Avoid diagrams made only of identical rounded rectangles. Also avoid excessive pictograms that obscure the computational structure.

## Connector rules

- Every arrow has a semantic meaning recorded in the spec.
- Prefer orthogonal or gently routed connectors.
- Avoid arrow/text crossings and edges passing through nodes.
- Distinguish primary flow, conditioning/guidance, residual/skip, and supervision using a small consistent style vocabulary.
- Do not create loose line fragments or unexplained arrowheads.

## Text and formulas

Image models may produce imperfect text. The prompt still requests exact short labels, while `figure_spec.json` remains authoritative for reconstruction. Prefer at most two text levels plus optional group headings. Do not ask the image model to typeset long paragraphs or dense derivations.

Large or claim-bearing formulas are reconstructed later from LaTeX. In the reference image, reserve a clean formula region and keep surrounding structure accurate.

## Regeneration criteria

Regenerate for semantic failures, missing modules, wrong directionality, unreadable topology, major overlaps, or a composition that cannot be reconstructed cleanly. Accept minor texture, shadow, or icon-detail differences that do not affect scientific meaning or editability.
