#!/usr/bin/env python3
"""Pixel-level metrics shared by the raster-precision tools.

Dependencies: numpy + Pillow only, so the tools run inside the same environment
as the bundled `editppt` runtime without adding anything to `cli/pyproject.toml`.

Everything here works on source-pixel coordinates so that measurements line up
with the manifest's `box_px` contract.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------- #
# loading and colour
# --------------------------------------------------------------------------- #


def load_rgb(path: str | Path) -> np.ndarray:
    """Load an image as an HxWx3 uint8 array, honouring EXIF rotation."""
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def to_gray(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 luma as float64 in 0..255."""
    values = rgb.astype(np.float64)
    return 0.299 * values[..., 0] + 0.587 * values[..., 1] + 0.114 * values[..., 2]


# --------------------------------------------------------------------------- #
# binarisation
# --------------------------------------------------------------------------- #


def otsu_threshold(gray: np.ndarray, bins: int = 256) -> float:
    """Otsu's threshold for a grayscale array."""
    flat = np.clip(gray, 0, 255).astype(np.uint8).ravel()
    histogram = np.bincount(flat, minlength=bins).astype(np.float64)
    total = histogram.sum()
    if total == 0:
        return 128.0
    levels = np.arange(bins, dtype=np.float64)
    weight_background = np.cumsum(histogram)
    weight_foreground = total - weight_background
    cumulative_mean = np.cumsum(histogram * levels)
    total_mean = cumulative_mean[-1]
    valid = (weight_background > 0) & (weight_foreground > 0)
    if not valid.any():
        return 128.0
    mean_background = np.divide(cumulative_mean, weight_background, out=np.zeros_like(cumulative_mean), where=weight_background > 0)
    mean_foreground = np.divide(
        total_mean - cumulative_mean, weight_foreground, out=np.zeros_like(cumulative_mean), where=weight_foreground > 0
    )
    variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
    variance[~valid] = -1.0
    return float(np.argmax(variance))


def ink_mask(gray: np.ndarray, threshold: float | None = None, invert: bool | None = None) -> tuple[np.ndarray, float, bool]:
    """Return (mask, threshold, inverted) where mask marks ink pixels.

    Ink is normally the dark side of the threshold. When the crop is mostly dark
    (light text on a dark panel) the polarity is flipped, and `inverted` reports
    that so callers can sample text colour from the right pixels.
    """
    if threshold is None:
        threshold = otsu_threshold(gray)
    dark = gray < threshold
    fraction = float(dark.mean()) if dark.size else 0.0
    if invert is None:
        invert = fraction > 0.5
    mask = ~dark if invert else dark
    return mask, float(threshold), bool(invert)


def dilate(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    """Binary dilation by a 4-connected square, used as a registration tolerance.

    A one-pixel placement difference between a source raster and a resampled
    render can otherwise read as "half the strokes vanished", which buries the
    real defects in noise.
    """
    result = mask.astype(bool).copy()
    for _ in range(max(0, int(radius))):
        expanded = result.copy()
        expanded[1:, :] |= result[:-1, :]
        expanded[:-1, :] |= result[1:, :]
        expanded[:, 1:] |= result[:, :-1]
        expanded[:, :-1] |= result[:, 1:]
        result = expanded
    return result


def dominant_band(mask: np.ndarray, center_row: int | None = None) -> tuple[int, int] | None:
    """Vertical band of contiguous ink rows that belongs to the line being measured.

    In dense text a crop margin can catch a neighbouring line's ascenders or
    descenders. The band containing the box centre is the line under measurement;
    falling back to the band with the most ink keeps single-band crops working.
    """
    rows = mask.any(axis=1)
    if not rows.any():
        return None
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(rows):
        if value and start is None:
            start = index
        elif not value and start is not None:
            bands.append((start, index - 1))
            start = None
    if start is not None:
        bands.append((start, len(rows) - 1))
    if not bands:
        return None
    if center_row is not None:
        for band in bands:
            if band[0] <= center_row <= band[1]:
                return band
    return max(bands, key=lambda band: int(mask[band[0] : band[1] + 1].sum()))


def ink_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Tight integer (left, top, width, height) of the True pixels, or None."""
    if mask.size == 0 or not mask.any():
        return None
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    top, bottom = int(rows[0]), int(rows[-1])
    left, right = int(cols[0]), int(cols[-1])
    return left, top, right - left + 1, bottom - top + 1


def crop_mask(mask: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    left, top, width, height = (int(value) for value in box)
    return mask[top : top + height, left : left + width]


def ink_color_hex(rgb: np.ndarray, mask: np.ndarray, mask_box: tuple[int, int, int, int] | None = None) -> str:
    """Median colour of the darkest ink pixels in a region.

    Using the darkest cluster instead of the mean keeps anti-aliased edge pixels
    (which blend towards the background) from washing the text colour out.
    """
    region = rgb if mask_box is None else rgb[mask_box[1] : mask_box[1] + mask_box[3], mask_box[0] : mask_box[0] + mask_box[2]]
    selected = mask if mask_box is None else crop_mask(mask, mask_box)
    if region.size == 0 or not selected.any():
        return "#000000"
    pixels = region[selected].astype(np.float64)
    luma = 0.299 * pixels[:, 0] + 0.587 * pixels[:, 1] + 0.114 * pixels[:, 2]
    cutoff = np.percentile(luma, 25)
    core = pixels[luma <= cutoff]
    if core.size == 0:
        core = pixels
    median = np.median(core, axis=0)
    return "#{:02X}{:02X}{:02X}".format(*(int(round(max(0.0, min(255.0, channel)))) for channel in median))


# --------------------------------------------------------------------------- #
# filters and SSIM
# --------------------------------------------------------------------------- #


def gaussian_kernel(size: int = 11, sigma: float = 1.5) -> np.ndarray:
    if size % 2 == 0:
        raise ValueError("gaussian kernel size must be odd")
    offsets = np.arange(size, dtype=np.float64) - (size - 1) / 2
    kernel = np.exp(-(offsets**2) / (2 * sigma**2))
    return kernel / kernel.sum()


def _separate_filter(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable 1-D filtering along both axes using stride tricks."""
    radius = len(kernel) // 2
    padded = np.pad(values, ((radius, radius), (0, 0)), mode="reflect")
    windows = np.lib.stride_tricks.sliding_window_view(padded, len(kernel), axis=0)
    filtered = windows @ kernel
    padded = np.pad(filtered, ((0, 0), (radius, radius)), mode="reflect")
    windows = np.lib.stride_tricks.sliding_window_view(padded, len(kernel), axis=1)
    return windows @ kernel


def ssim(reference: np.ndarray, rendered: np.ndarray, kernel: np.ndarray | None = None) -> tuple[float, np.ndarray]:
    """Structural similarity with an 11x11 Gaussian window (Wang et al.)."""
    if reference.shape != rendered.shape:
        raise ValueError(f"shape mismatch: {reference.shape} vs {rendered.shape}")
    kernel = gaussian_kernel() if kernel is None else kernel
    left = reference.astype(np.float64)
    right = rendered.astype(np.float64)
    mu_left = _separate_filter(left, kernel)
    mu_right = _separate_filter(right, kernel)
    mu_left_sq = mu_left**2
    mu_right_sq = mu_right**2
    mu_product = mu_left * mu_right
    sigma_left_sq = _separate_filter(left * left, kernel) - mu_left_sq
    sigma_right_sq = _separate_filter(right * right, kernel) - mu_right_sq
    sigma_product = _separate_filter(left * right, kernel) - mu_product
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    numerator = (2 * mu_product + c1) * (2 * sigma_product + c2)
    denominator = (mu_left_sq + mu_right_sq + c1) * (sigma_left_sq + sigma_right_sq + c2)
    score_map = numerator / denominator
    return float(score_map.mean()), score_map


def tile_grid(score_map: np.ndarray, tile: int) -> np.ndarray:
    """Mean of each `tile` x `tile` block, cropped to whole blocks."""
    height, width = score_map.shape
    rows = max(1, height // tile)
    cols = max(1, width // tile)
    trimmed = score_map[: rows * tile, : cols * tile]
    return trimmed.reshape(rows, tile, cols, tile).mean(axis=(1, 3))


def boxes_from_tiles(tile_scores: np.ndarray, tile: int, threshold: float) -> list[dict]:
    """Connected groups of tiles below `threshold` as pixel boxes."""
    return boxes_from_bad_grid(tile_scores < threshold, tile, tile_scores)


def tile_sums(mask: np.ndarray, tile: int) -> np.ndarray:
    """Sum of True pixels per `tile` x `tile` block, cropped to whole blocks."""
    height, width = mask.shape
    rows = max(1, height // tile)
    cols = max(1, width // tile)
    trimmed = mask[: rows * tile, : cols * tile].astype(np.int64)
    return trimmed.reshape(rows, tile, cols, tile).sum(axis=(1, 3))


def boxes_from_bad_grid(bad: np.ndarray, tile: int, severity: np.ndarray) -> list[dict]:
    """Connected groups of flagged tiles as pixel boxes, ranked by severity."""
    if not bad.any():
        return []
    rows, cols = bad.shape
    seen = np.zeros_like(bad, dtype=bool)
    boxes: list[dict] = []
    for start_row in range(rows):
        for start_col in range(cols):
            if not bad[start_row, start_col] or seen[start_row, start_col]:
                continue
            stack = [(start_row, start_col)]
            seen[start_row, start_col] = True
            group: list[tuple[int, int]] = []
            while stack:
                row, col = stack.pop()
                group.append((row, col))
                for delta_row, delta_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    next_row, next_col = row + delta_row, col + delta_col
                    if 0 <= next_row < rows and 0 <= next_col < cols and bad[next_row, next_col] and not seen[next_row, next_col]:
                        seen[next_row, next_col] = True
                        stack.append((next_row, next_col))
            group_rows = [item[0] for item in group]
            group_cols = [item[1] for item in group]
            scores = [float(severity[row, col]) for row, col in group]
            boxes.append(
                {
                    "box_px": [
                        min(group_cols) * tile,
                        min(group_rows) * tile,
                        (max(group_cols) - min(group_cols) + 1) * tile,
                        (max(group_rows) - min(group_rows) + 1) * tile,
                    ],
                    "tiles": len(group),
                    "min_severity": round(min(scores), 4),
                    "mean_severity": round(float(np.mean(scores)), 4),
                }
            )
    boxes.sort(key=lambda item: (item["min_severity"], -item["tiles"]))
    return boxes


def overlap_ratio(box_a: list[int] | tuple[int, int, int, int], box_b: list[int] | tuple[int, int, int, int]) -> float:
    """Intersection over the smaller box's area."""
    left = max(box_a[0], box_b[0])
    top = max(box_a[1], box_b[1])
    right = min(box_a[0] + box_a[2], box_b[0] + box_b[2])
    bottom = min(box_a[1] + box_a[3], box_b[1] + box_b[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    smaller = min(box_a[2] * box_a[3], box_b[2] * box_b[3])
    return float(intersection / smaller) if smaller else 0.0


# --------------------------------------------------------------------------- #
# ink comparison
# --------------------------------------------------------------------------- #


def align_ink_iou(mask_a: np.ndarray, mask_b: np.ndarray, max_shift: int = 3) -> tuple[float, tuple[int, int]]:
    """IoU of two ink masks after aligning their ink bounding boxes.

    Small shifts are searched so that a one-or-two pixel offset does not read as
    a coverage failure. Coordinates are cropped-mask pixels, not image pixels.
    """
    box_a = ink_bbox(mask_a)
    box_b = ink_bbox(mask_b)
    if box_a is None or box_b is None:
        return 0.0, (0, 0)
    tight_a = crop_mask(mask_a, box_a)
    tight_b = crop_mask(mask_b, box_b)
    height = max(tight_a.shape[0], tight_b.shape[0]) + 2 * max_shift
    width = max(tight_a.shape[1], tight_b.shape[1]) + 2 * max_shift
    canvas_a = np.zeros((height, width), dtype=bool)
    canvas_b = np.zeros((height, width), dtype=bool)
    canvas_a[max_shift : max_shift + tight_a.shape[0], max_shift : max_shift + tight_a.shape[1]] = tight_a
    best_iou = 0.0
    best_shift = (0, 0)
    for delta_y in range(-max_shift, max_shift + 1):
        for delta_x in range(-max_shift, max_shift + 1):
            canvas_b[:] = False
            top = max_shift + delta_y
            left = max_shift + delta_x
            if top < 0 or left < 0 or top + tight_b.shape[0] > height or left + tight_b.shape[1] > width:
                continue
            canvas_b[top : top + tight_b.shape[0], left : left + tight_b.shape[1]] = tight_b
            union = np.logical_or(canvas_a, canvas_b).sum()
            if union == 0:
                continue
            iou = float(np.logical_and(canvas_a, canvas_b).sum() / union)
            if iou > best_iou:
                best_iou = iou
                best_shift = (delta_x, delta_y)
    return best_iou, best_shift


def content_alignment(reference_mask: np.ndarray, rendered_mask: np.ndarray) -> dict:
    """Compare the overall ink extents of two masks (catches scale/padding drift)."""
    box_reference = ink_bbox(reference_mask)
    box_rendered = ink_bbox(rendered_mask)
    if box_reference is None or box_rendered is None:
        return {
            "reference_ink_box": list(box_reference) if box_reference else None,
            "rendered_ink_box": list(box_rendered) if box_rendered else None,
            "offset_px": None,
            "scale_ratio": None,
            "comparable": False,
        }
    offset_x = box_rendered[0] - box_reference[0]
    offset_y = box_rendered[1] - box_reference[1]
    scale_width = box_rendered[2] / box_reference[2] if box_reference[2] else 1.0
    scale_height = box_rendered[3] / box_reference[3] if box_reference[3] else 1.0
    return {
        "reference_ink_box": list(box_reference),
        "rendered_ink_box": list(box_rendered),
        "offset_px": [int(offset_x), int(offset_y)],
        "scale_ratio": [round(scale_width, 4), round(scale_height, 4)],
        "comparable": True,
    }


def resize_mask(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resize of a boolean mask to (width, height)."""
    image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(size, Image.Resampling.NEAREST)
    return np.asarray(image) > 127


def normalized_pair(reference_path: str | Path, rendered_path: str | Path, size: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    """Load both images as crops of a common size.

    When the rendered image has a different aspect ratio it is stretched; the
    caller reports that as a problem rather than hiding it.
    """
    reference = Image.open(reference_path).convert("RGB")
    with Image.open(rendered_path) as rendered_image:
        rendered = rendered_image.convert("RGB")
    width, height = reference.size if size is None else size
    if reference.size != (width, height):
        reference = reference.resize((width, height), Image.Resampling.LANCZOS)
    if rendered.size != (width, height):
        rendered = rendered.resize((width, height), Image.Resampling.LANCZOS)
    return (
        np.asarray(reference, dtype=np.uint8),
        np.asarray(rendered, dtype=np.uint8),
        (width, height),
    )
