"""Burned-in camera overlays of D-Fire ('CameraNNNN' label top-left, date stamp bottom-right).

Measured on 4 587 sampled images (overlay_probe.py): 45 % of fire-only images carry one against 12 % of background and
5 % of smoke-only images, and 60 % of dark images carry one. The box camera adds none, so the cue is a shortcut.
  mask_overlay   neutralises the regions (evaluation: does the score drop? training: remove the cue)
  paste_overlay  draws a synthetic overlay (training: make the cue independent of the class)
Regions are relative, read off 1280x720 frames (assumption, see overlay_probe.py).
"""
import cv2
import numpy as np

# x0, x1, y0, y1 as fractions of the image. *_DET = the stamp boxes read off 1280x720 frames (used to detect and to paste);
# the masks are a little larger so that no character is left.
LABEL_DET = (0.045, 0.16, 0.08, 0.115)
DATE_DET = (0.81, 0.99, 0.88, 0.915)
LABEL = (0.03, 0.18, 0.065, 0.13)
DATE = (0.75, 1.0, 0.86, 0.94)
STRIP = (0.0, 0.30, 0.0, 0.035)        # small text line at the very top-left on some cameras
REGIONS = (LABEL, DATE, STRIP)


def _box(img, reg):
    h, w = img.shape[:2]
    return int(reg[0] * w), int(reg[1] * w), int(reg[2] * h), int(reg[3] * h)


def mask_overlay(img, regions=REGIONS):
    """Fills every region with the mean colour of a thin ring around it. Returns a copy."""
    out = img.copy()
    for reg in regions:
        x0, x1, y0, y1 = _box(img, reg)
        if x1 <= x0 or y1 <= y0:
            continue
        pad = max(2, (y1 - y0) // 4)
        X0, X1, Y0, Y1 = max(x0 - pad, 0), min(x1 + pad, img.shape[1]), max(y0 - pad, 0), min(y1 + pad, img.shape[0])
        ring = img[Y0:Y1, X0:X1].astype(np.float32).copy()
        inner = np.zeros(ring.shape[:2], bool); inner[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = True
        fill = ring[~inner].mean(0) if (~inner).any() else np.array([114, 114, 114], np.float32)
        out[y0:y1, x0:x1] = fill.astype(np.uint8)
    return out


def _stamp(out, reg, txt):
    x0, x1, y0, y1 = _box(out, reg)
    cv2.rectangle(out, (x0, y0), (x1, y1), (0, 0, 0), -1)
    font = cv2.FONT_HERSHEY_SIMPLEX
    sc = (y1 - y0) / 26.0
    while sc > 0.2:
        (tw, th), _ = cv2.getTextSize(txt, font, sc, max(1, int(round(sc * 1.4))))
        if tw <= (x1 - x0) - 6 and th <= (y1 - y0) - 4:
            break
        sc -= 0.03
    cv2.putText(out, txt, (x0 + 3, y1 - max(2, (y1 - y0) // 5)), font, sc, (255, 255, 255), max(1, int(round(sc * 1.4))), cv2.LINE_AA)


def paste_overlay(img, rng, label=True, date=True):
    """Draws a black box with white text like the D-Fire stamps. Returns a copy."""
    out = img.copy()
    if label:
        _stamp(out, LABEL_DET, f"Camera{int(rng.integers(1, 6)):04d}")
    if date:
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        _stamp(out, DATE_DET, f"{int(rng.integers(1, 29)):02d}.{months[int(rng.integers(0, 12))]} 20{int(rng.integers(19, 22))} {int(rng.integers(0, 24)):02d}:{int(rng.integers(0, 60)):02d}:{int(rng.integers(0, 60)):02d}")
    return out
