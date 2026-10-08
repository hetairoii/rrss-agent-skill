"""
common.py - utilidades compartidas por los scripts de ig-curador.

Nada aquí toca la red. Todo corre en tu máquina sobre tus archivos.
"""

import json
import math
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"
USER_DIR = Path(os.environ.get("RRSS_HOME", Path.home() / ".claude" / "rrss"))

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp"}


# --------------------------------------------------------------------- json

def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        if default is not None:
            return default
        sys.exit(f"error: no existe {p}")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_config(name):
    return load_json(CONFIG_DIR / name)


# --------------------------------------------------------------- geometría

def parse_ratio(r):
    """'4:5' -> 0.8 ; 0.8 -> 0.8"""
    if isinstance(r, (int, float)):
        return float(r)
    a, b = str(r).split(":")
    return float(a) / float(b)


def crop_box(w, h, ratio, focal=(0.5, 0.5)):
    """Ventana de recorte más grande con proporción `ratio` (ancho/alto),
    centrada lo más posible en `focal` (x, y en 0-1). Devuelve (x0, y0, x1, y1)."""
    src = w / h
    if src > ratio:            # sobra ancho
        cw, ch = h * ratio, h
    else:                      # sobra alto
        cw, ch = w, w / ratio
    fx, fy = focal
    x0 = min(max(fx * w - cw / 2, 0), w - cw)
    y0 = min(max(fy * h - ch / 2, 0), h - ch)
    return (x0, y0, x0 + cw, y0 + ch)


def crop_loss(w, h, ratio):
    """Fracción de la imagen que se pierde al recortar a `ratio`."""
    x0, y0, x1, y1 = crop_box(w, h, ratio)
    return 1.0 - ((x1 - x0) * (y1 - y0)) / (w * h)


def faces_cut(faces, box, w, h, tolerance=0.15):
    """Cuántas caras quedan cortadas por la ventana de recorte.
    `faces` en coordenadas normalizadas [x, y, fw, fh]."""
    x0, y0, x1, y1 = box
    cut = 0
    for fx, fy, fw, fh in faces:
        ax0, ay0 = fx * w, fy * h
        ax1, ay1 = (fx + fw) * w, (fy + fh) * h
        ix = max(0, min(ax1, x1) - max(ax0, x0))
        iy = max(0, min(ay1, y1) - max(ay0, y0))
        area = (ax1 - ax0) * (ay1 - ay0)
        if area > 0 and (ix * iy) / area < 1 - tolerance:
            cut += 1
    return cut


def ratio_label(w, h):
    r = w / h
    known = {"9:16": 9 / 16, "3:4": 3 / 4, "4:5": 4 / 5, "1:1": 1.0,
             "5:4": 5 / 4, "4:3": 4 / 3, "3:2": 3 / 2, "16:9": 16 / 9, "2:3": 2 / 3}
    best = min(known.items(), key=lambda kv: abs(math.log(r / kv[1])))
    return best[0] if abs(math.log(r / best[1])) < 0.04 else f"{r:.2f}:1"


def orientation(w, h):
    r = w / h
    if r < 0.9:
        return "vertical"
    if r > 1.1:
        return "horizontal"
    return "cuadrada"


# ------------------------------------------------------------ similitud

def hamming_hex(a, b):
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def hist_intersection(a, b):
    if not a or not b:
        return 0.0
    return sum(min(x, y) for x, y in zip(a, b))


def similarity(a, b):
    """0 = nada que ver, 1 = la misma foto. Mezcla estructura (dHash) y color."""
    if a.get("grupo") and a.get("grupo") == b.get("grupo"):
        return 1.0
    shot = max((a.get("escena") or {}).get(b.get("id"), 0.0),
               (b.get("escena") or {}).get(a.get("id"), 0.0))
    h = hamming_hex(a.get("dhash"), b.get("dhash"))
    s_struct = max(0.0, 1.0 - h / 26.0)
    s_color = hist_intersection(a.get("hist"), b.get("hist"))
    return max(shot, 0.6 * s_struct + 0.4 * s_color)


# ------------------------------------------------------------- varios

def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def slug(text, n=40):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^\w\s-]", "", t.lower())
    t = re.sub(r"[\s_-]+", "-", t).strip("-")
    return t[:n].strip("-") or "publicacion"


def bar(v, width=20):
    v = clamp(v)
    full = int(round(v / 100 * width))
    return "#" * full + "." * (width - full)


def fmt_time(t):
    t = float(t)
    return f"{int(t // 60)}:{t % 60:04.1f}"
