# Published-paper benchmark protocol

Use this protocol after every material reconstruction change before claiming that fidelity improved. Choose the acceptance mode before building; a pixel-identity benchmark and a reference-guided perceptual benchmark answer different questions.

## Admissible samples

The paper must be publicly published at the target venue and its source provenance must be recorded. Keep these cases separate:

1. **Deterministic TeX**: the supplied TeX contains complete TikZ/PGF/PGFPlots geometry. The published crop is withheld from generation and used only as the gold comparison.
2. **Referenced image**: the TeX contains `\includegraphics`. Exact reconstruction requires the referenced original image as reconstruction input; without it the sample is semantic-only.
3. **Description only**: prose, equations, captions, or module names do not determine a unique published layout. Evaluate scientific correctness and design quality, never pixel identity.
4. **Reference-guided reconstruction**: the published figure is openly used as a visual reference. This tests image-to-editable-PPT reconstruction, not unseen TeX-to-figure generation. Keep this case labeled and scored separately from deterministic TeX.

Do not select an underdetermined sample and then use the hidden gold image during generation. That is leakage, not a TeX-to-figure benchmark.

## Required artifacts

Store source TeX and classification; publication URL, venue, year, title, figure number, and hash; withheld `gold-original.png`; reference and provenance; editable PPTX; WPS first-open and reopened exports; three visual comparisons; editability audit; and five reviewer verdict JSON files.

## Automatic gates

The final visual comparison always uses the WPS **reopened** export. In `pixel-identical` mode, run `compare_renders.py --strict-identical`: WPS provenance, no font substitutions, no skipped low-confidence text, no missing ink/repair targets, and strict geometry/colour thresholds are mandatory. In `perceptual-95-blind` mode, run the same comparison as a diagnostic, preserving SSIM, local repair targets and content alignment without treating an arbitrary SSIM value as a 95% human-similarity score. Fix conspicuous defects such as clipping, unreadable text, broken arrows and scientific errors before blind review.

Editability is a separate hard gate. Audit the actual PPTX package, not only the manifest. Reject a page-sized raster, tiled rasters that together reproduce the full page, or a single vector-picture object presented as object-level native editability. Report each object as native text/shape/path/table, vector picture, or raster asset.

## Five-reviewer blind gate

Prepare the same randomly ordered A/B pair for five independent reviewers. Do not reveal which side is the published original, how the reconstruction was made, or other reviewers' judgments. Reviewers must inspect at full size and must not read file metadata or code. For `pixel-identical`, each reviewer returns `identical`, confidence and localized differences. Any `identical: false` fails that round.

For `perceptual-95-blind`, each reviewer instead returns:

```json
{
  "reviewer_id": "reviewer-1",
  "similarity_0_100": 96,
  "reliably_distinguishable": false,
  "original_guess": "uncertain",
  "confidence_0_1": 0.5,
  "specific_visual_cues": []
}
```

Run `scripts/evaluate_perceptual_benchmark.py` on five distinct reviewer JSON files. Perceptual parity passes only if **every** reviewer scores overall similarity at least 95/100 and reports that they cannot reliably distinguish the origin. A wrong but confident original guess is not by itself evidence of indistinguishability if the reviewer identifies obvious differences. Preserve all raw judgments, including low scores and disagreements.

Repair concrete regions, regenerate the WPS round-trip render, rerun scientific/editability gates, and ask all five reviewers to judge the new pair. Previous approvals do not carry over. Only claim success for the **declared mode and evaluated figures** when its automatic, scientific, package, editability, and five-of-five blind gates pass in the same final round. Otherwise deliver the best valid result and explicitly report the unmet gate. Passing on one figure never proves generalization to another figure family.
