# Figure specification

`figure_spec.json` is the scientific source of truth shared by image generation, editable reconstruction, and validation. It is not a loose summary.

## Required shape

```json
{
  "schema_version": 1,
  "figure_id": "method-overview",
  "figure_type": "architecture",
  "title": "",
  "venue_profile": "cvpr",
  "canvas": {
    "aspect_ratio": "16:9",
    "orientation": "landscape",
    "reading_direction": "left-to-right"
  },
  "scientific_message": "One sentence stating what the figure must communicate.",
  "groups": [
    {"id": "encoder", "label": "Encoder", "description": "..."}
  ],
  "modules": [
    {
      "id": "visual_encoder",
      "label": "Visual Encoder",
      "kind": "encoder",
      "group": "encoder",
      "description": "Encodes video frames into temporal visual features.",
      "visual_hint": "stacked feature maps"
    }
  ],
  "edges": [
    {
      "id": "video-to-encoder",
      "from": "video_input",
      "to": "visual_encoder",
      "label": "",
      "direction": "forward",
      "style": "primary",
      "meaning": "video feature extraction"
    }
  ],
  "formulas": [
    {"id": "loss", "latex": "\\mathcal{L}=...", "placement": "footer"}
  ],
  "exact_text": ["Video Input", "Visual Encoder"],
  "style": {
    "tone": "clean publication-ready vector diagram",
    "palette": ["#4457A6", "#5CA8A8", "#E6B566", "#F5F6F8"],
    "background": "white",
    "line_style": "clean orthogonal connectors",
    "typography": "sans-serif, concise labels",
    "density": "moderate"
  },
  "reconstruction": {
    "mode": "reference-guided-hybrid",
    "min_font_pt": 10.0,
    "min_micro_font_pt": 8.0,
    "max_micro_text_fraction": 0.25,
    "min_raster_dpi": 300,
    "prefer_vector_formulas": true,
    "prefer_vector_simple_icons": true
  },
  "forbidden": ["invented modules", "decorative arrows without semantics"],
  "assumptions": []
}
```

## Figure types

- `architecture`: model components, tensors, feature flows, training/inference branches.
- `workflow`: ordered experimental, data, or algorithmic procedure.
- `conceptual`: mechanism, hypothesis, comparison, or explanatory scientific concept.
- `multimodal`: parallel modalities, alignment, fusion, shared spaces.
- `training-inference`: explicitly separated optimization and deployment paths.

## Scientific invariants

IDs must be unique. Every edge endpoint must reference an existing module or group boundary. Repeated modules remain separate unless the user explicitly says weights are shared. Do not convert an undirected relationship into a directed arrow. Do not add residual, attention, normalization, loss, or supervision paths merely because they are common in the field.

`exact_text` contains every claim-bearing label that must appear as editable text in the final PPTX. Use short visible labels; keep long explanations in `description` for prompt context rather than forcing paragraphs into the figure.

Formulas preserve the user's LaTeX exactly unless a syntax-only repair is required. Record any repair in `assumptions`.

`reconstruction` controls the editable deliverable, not the GPT reference image. `reference-guided-hybrid` keeps the generated image as the composition and style target while routing each final object to native PowerPoint, SVG, or high-resolution raster according to [hybrid-reconstruction.md](hybrid-reconstruction.md). Text marked as micro-annotation may use `min_micro_font_pt`; keep its share below `max_micro_text_fraction` so the exception cannot hide an unreadable figure.

## TeX and TikZ inputs

Treat node labels, math, groups, and edge definitions as evidence. TikZ coordinates are layout hints, not scientific semantics. Preserve directed edges and branch structure even if the original layout is poor. Ignore document-level commands unrelated to the figure. Do not execute shell escape or arbitrary input files.
