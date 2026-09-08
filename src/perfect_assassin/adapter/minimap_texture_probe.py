"""Offline masked texture correlation. Similarity is not location confidence.

No actor coordinate, floor selection, camera inference, or execution authority.
The caller must supply an observed ROI/mask and enumerate competing references.
"""

import numpy as np


def _correlate(image, kernel):
    shape = tuple(a + b - 1 for a, b in zip(image.shape, kernel.shape))
    result = np.fft.irfft2(
        np.fft.rfft2(image, s=shape) * np.fft.rfft2(kernel[::-1, ::-1], s=shape),
        s=shape,
    )
    h, w = kernel.shape
    return result[h - 1 : image.shape[0], w - 1 : image.shape[1]]


def masked_texture_match(image, template, support, valid_pixels):
    """Best fully contained masked ZNCC match, with bounded 2D input arrays.

    Image/template intensities are [0,1]. All reference support must lie in
    valid_pixels; no partial-clipping match or black-background-only match.
    Small/constant references yield explicit non-evidence, never a score of 1.
    """
    image, template = np.asarray(image), np.asarray(template)
    support, valid = np.asarray(support), np.asarray(valid_pixels)
    if (
        image.ndim != 2
        or template.ndim != 2
        or support.shape != template.shape
        or valid.shape != image.shape
        or support.dtype != bool
        or valid.dtype != bool
        or any(not 1 <= n <= 512 for n in (*image.shape, *template.shape))
    ):
        raise ValueError("invalid bounded image/template/mask dimensions or types")
    for array in (image, template):
        if not np.issubdtype(array.dtype, np.number) or np.iscomplexobj(array):
            raise ValueError("invalid intensity type")
        if not np.isfinite(array).all() or np.any((array < 0) | (array > 1)):
            raise ValueError("intensities must be finite and in [0,1]")
    count = int(support.sum())
    unknown = {"status": "INSUFFICIENT_TEXTURE", "similarity": None,
               "offset_xy": None, "support_pixels": count}
    if count < 64 or any(a > b for a, b in zip(template.shape, image.shape)):
        return unknown
    centered = (template - template[support].mean()) * support
    energy = float(np.sum(centered ** 2))
    if energy / count < 1e-5:
        return unknown
    totals = _correlate(image, support)
    squares = _correlate(image ** 2, support)
    variance = np.maximum(0, squares - totals ** 2 / count)
    contained = _correlate(valid.astype(float), support) >= count - 1e-5
    eligible = contained & (variance / count >= 1e-5)
    if not eligible.any():
        return {**unknown, "status": "NO_VALID_PLACEMENT"}
    numerator = _correlate(image, centered)
    scores = np.full(variance.shape, -np.inf)
    scores[eligible] = np.clip(
        numerator[eligible] / np.sqrt(variance[eligible] * energy), -1, 1
    )
    y, x = np.unravel_index(np.argmax(scores), scores.shape)
    return {"status": "CANDIDATE_ONLY", "similarity": float(scores[y, x]),
            "offset_xy": [int(x), int(y)], "support_pixels": count}
